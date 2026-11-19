"""Migrations do auth contra MySQL real: DDL físico, GRANTs, ENUMs e REVOKE no downgrade"""

import asyncio
import hashlib
import os
from datetime import UTC, datetime

import pymysql
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL

from auth_service.adapters.cpf_protector import AesGcmCpfProtector
from auth_service.adapters.repositories import SqlAlchemyUserRepository
from auth_service.domain.cpf import Cpf
from auth_service.domain.errors import (
    AlreadyRegisteredError,
    CpfAlreadyRegisteredError,
    EmailAlreadyRegisteredError,
    OabAlreadyRegisteredError,
)
from auth_service.domain.oab import Oab
from auth_service.models import OabKind, OabUf, UserType
from veriditi_common.db import Database

pytestmark = pytest.mark.mysql

HOST = os.environ.get("CONTRACT_DB_HOST", "127.0.0.1")
PORT = int(os.environ.get("CONTRACT_DB_PORT", "3317"))
MIGRATOR_PASSWORD = os.environ.get("DB_MIGRATOR_PASSWORD", "m")
AUTH_PASSWORD = os.environ.get("AUTH_DB_PASSWORD", "a")
TABLE_ACCESS_DENIED = 1142
DUPLICATE_ENTRY = 1062
CHECK_VIOLATED = 3819


def _connect(user: str, password: str, database: str | None = "veriditi") -> pymysql.Connection:
    return pymysql.connect(
        host=HOST, port=PORT, user=user, password=password, database=database, autocommit=True
    )


def _insert_user(
    cur: pymysql.cursors.Cursor,
    email: str,
    *,
    user_type: str = "common",
    cpf_seed: str | None = None,
    oab: tuple[str, str, str] | None = None,
) -> int:
    number, uf, kind = oab or (None, None, None)
    cur.execute(
        "INSERT INTO users (email, name, password_hash, user_type, cpf_enc, cpf_hmac, oab_number, "
        "oab_uf, oab_kind) VALUES (%s, 'Nome', '$argon2id$stub', %s, %s, %s, %s, %s, %s)",
        (
            email,
            user_type,
            b"\x01" + os.urandom(39),
            hashlib.sha256((cpf_seed or email).encode()).hexdigest(),
            number,
            uf,
            kind,
        ),
    )
    return int(cur.lastrowid)


def _auth_grants() -> str:
    # SHOW GRANTS FOR outro usuário exige SELECT em mysql.*, que o migrator não tem
    with _connect("auth_svc", AUTH_PASSWORD, database=None) as conn, conn.cursor() as cur:
        cur.execute("SHOW GRANTS")
        return "\n".join(row[0] for row in cur.fetchall())


def test_users_has_contract_ddl(migrated: Config) -> None:
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("SHOW CREATE TABLE users")
        ddl = cur.fetchone()[1]  # type: ignore[index]

    assert "`id` bigint NOT NULL AUTO_INCREMENT" in ddl
    assert "`password_hash` varchar(255) NOT NULL" in ddl
    assert "`created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)" in ddl
    assert "UNIQUE KEY `uq_users_email`" in ddl


def test_runtime_user_has_dml_without_delete(migrated: Config) -> None:
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        _insert_user(cur, "ana@example.com")
        cur.execute("UPDATE users SET name = 'Ana B' WHERE email = 'ana@example.com'")
        cur.execute("SELECT name FROM users")
        assert cur.fetchone() == ("Ana B",)

        with pytest.raises(pymysql.err.OperationalError) as exc:
            cur.execute("DELETE FROM users")

    assert exc.value.args[0] == TABLE_ACCESS_DENIED


def test_downgrade_revokes_table_grant(migrated: Config) -> None:
    assert "`veriditi`.`users`" in _auth_grants()

    command.downgrade(migrated, "base")

    assert "`users`" not in _auth_grants()
    command.upgrade(migrated, "head")


def test_password_reset_tokens_has_contract_ddl(migrated: Config) -> None:
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("SHOW CREATE TABLE password_reset_tokens")
        ddl = cur.fetchone()[1]  # type: ignore[index]

    assert "`token_hash` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL" in ddl
    assert "`expires_at` datetime(6) NOT NULL" in ddl
    assert "`consumed_at` datetime(6) DEFAULT NULL" in ddl
    assert "`requested_ip` varchar(45) DEFAULT NULL" in ddl
    assert "UNIQUE KEY `uq_password_reset_tokens_token_hash` (`token_hash`)" in ddl
    assert "KEY `ix_password_reset_tokens_user_id_consumed_at` (`user_id`,`consumed_at`)" in ddl
    assert "CONSTRAINT `fk_password_reset_tokens_user_id_users` FOREIGN KEY (`user_id`)" in ddl


def test_runtime_user_can_purge_reset_tokens(migrated: Config) -> None:
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        user_id = _insert_user(cur, "rt@example.com")
        cur.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
            "VALUES (%s, %s, UTC_TIMESTAMP(6))",
            (user_id, "a" * 64),
        )
        cur.execute("UPDATE password_reset_tokens SET consumed_at = UTC_TIMESTAMP(6)")
        cur.execute("DELETE FROM password_reset_tokens")
        cur.execute("SELECT COUNT(*) FROM password_reset_tokens")
        assert cur.fetchone() == (0,)


def test_revoke_reason_accepts_password_reset(migrated: Config) -> None:
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("SHOW COLUMNS FROM refresh_tokens LIKE 'revoke_reason'")
        column_type = cur.fetchone()[1]  # type: ignore[index]

    assert column_type == "enum('rotated','logout','reuse_detected','password_reset')"


def test_downgrade_of_0005_keeps_revoked_sessions(migrated: Config) -> None:
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        user_id = _insert_user(cur, "dg@example.com")
        cur.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, family_id, expires_at, "
            "revoked_at, revoke_reason) VALUES (%s, %s, %s, UTC_TIMESTAMP(6), "
            "UTC_TIMESTAMP(6), 'password_reset')",
            (user_id, "b" * 64, "0" * 8 + "-0000-0000-0000-" + "0" * 12),
        )

    command.downgrade(migrated, "0004")

    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("SELECT revoke_reason FROM refresh_tokens")
        assert cur.fetchone() == ("logout",)
    assert "`password_reset_tokens`" not in _auth_grants()
    # Sem CPF, a 0006 recusaria subir: limpa como o migrator, que pode apagar
    with _connect("migrator", MIGRATOR_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM refresh_tokens")
        cur.execute("DELETE FROM users")
    command.upgrade(migrated, "head")


def test_users_has_type_cpf_and_oab_ddl(migrated: Config) -> None:
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("SHOW CREATE TABLE users")
        ddl = cur.fetchone()[1]  # type: ignore[index]

    assert "`user_type` enum('common','lawyer') NOT NULL" in ddl
    assert "`cpf_enc` varbinary(64) NOT NULL" in ddl
    assert "`cpf_hmac` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL" in ddl
    assert "`oab_number` varchar(6) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL" in ddl
    assert "`oab_uf` enum('AC','AL'," in ddl and "'TO') DEFAULT NULL" in ddl
    assert "`oab_kind` enum('principal','suplementar','transitoria') DEFAULT NULL" in ddl
    assert "UNIQUE KEY `uq_users_cpf_hmac` (`cpf_hmac`)" in ddl
    assert "UNIQUE KEY `uq_users_oab_uf_oab_number` (`oab_uf`,`oab_number`)" in ddl
    assert "CONSTRAINT `ck_users_oab_matches_type` CHECK" in ddl


@pytest.mark.parametrize(
    ("user_type", "oab"),
    [
        ("lawyer", None),
        ("common", ("123", "BA", "principal")),
        ("lawyer", ("123", "BA", None)),
    ],
)
def test_check_requires_oab_iff_lawyer(
    migrated: Config, user_type: str, oab: tuple[str, str, str] | None
) -> None:
    with (
        _connect("auth_svc", AUTH_PASSWORD) as conn,
        conn.cursor() as cur,
        pytest.raises(pymysql.err.OperationalError) as exc,
    ):
        _insert_user(cur, "x@example.com", user_type=user_type, oab=oab)

    assert exc.value.args[0] == CHECK_VIOLATED


def test_cpf_hmac_and_oab_are_unique(migrated: Config) -> None:
    oab = ("123", "BA", "principal")
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        _insert_user(cur, "a@example.com", user_type="lawyer", cpf_seed="1", oab=oab)
        _insert_user(
            cur, "b@example.com", user_type="lawyer", cpf_seed="2", oab=("123", "SP", "principal")
        )
        _insert_user(cur, "c@example.com", cpf_seed="3")
        _insert_user(cur, "d@example.com", cpf_seed="4")

        with pytest.raises(pymysql.err.IntegrityError) as cpf:
            _insert_user(cur, "e@example.com", cpf_seed="1")
        with pytest.raises(pymysql.err.IntegrityError) as dup_oab:
            _insert_user(cur, "f@example.com", user_type="lawyer", cpf_seed="5", oab=oab)

    assert cpf.value.args[0] == DUPLICATE_ENTRY
    assert "uq_users_cpf_hmac" in cpf.value.args[1]
    assert dup_oab.value.args[0] == DUPLICATE_ENTRY
    assert "uq_users_oab_uf_oab_number" in dup_oab.value.args[1]


def test_upgrade_refuses_users_without_cpf(migrated: Config) -> None:
    command.downgrade(migrated, "0005")
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, name, password_hash) "
            "VALUES ('antigo@example.com', 'Antigo', '$argon2id$stub')"
        )

    with pytest.raises(RuntimeError, match=r"1 usuário\(s\) sem CPF.*make reset"):
        command.upgrade(migrated, "head")

    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("SHOW COLUMNS FROM users LIKE 'cpf_hmac'")
        assert cur.fetchone() is None


def _auth_database() -> Database:
    url = URL.create(
        "mysql+aiomysql",
        username="auth_svc",
        password=AUTH_PASSWORD,
        host=HOST,
        port=PORT,
        database="veriditi",
        query={"charset": "utf8mb4"},
    )
    return Database(url.render_as_string(hide_password=False))


def test_repository_maps_mysql_duplicates_and_stores_only_ciphertext(migrated: Config) -> None:
    # Síncrono com asyncio.run: a fixture migrated já usa o asyncio.run do env.py
    protector = AesGcmCpfProtector(encryption_key=os.urandom(32), hmac_key=os.urandom(32))
    cpf = Cpf.parse("529.982.247-25")
    oab = Oab(number="123", uf=OabUf.BA, kind=OabKind.PRINCIPAL)
    now = datetime.now(UTC)

    async def create(email: str, cpf: Cpf) -> type[AlreadyRegisteredError] | None:
        db = _auth_database()
        try:
            async with db.session_factory() as session:
                await SqlAlchemyUserRepository(session).create(
                    email=email,
                    name="Nome",
                    password_hash="$argon2id$stub",
                    user_type=UserType.LAWYER,
                    cpf_enc=protector.encrypt(cpf),
                    cpf_hmac=protector.blind_index(cpf),
                    oab=oab,
                    now=now,
                )
            return None
        except AlreadyRegisteredError as exc:
            return type(exc)
        finally:
            await db.dispose()

    other = Cpf.parse("111.444.777-35")
    assert asyncio.run(create("a@example.com", cpf)) is None
    assert asyncio.run(create("a@example.com", other)) is EmailAlreadyRegisteredError
    assert asyncio.run(create("b@example.com", cpf)) is CpfAlreadyRegisteredError
    assert asyncio.run(create("b@example.com", other)) is OabAlreadyRegisteredError

    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("SELECT cpf_enc, cpf_hmac FROM users")
        [(cpf_enc, cpf_hmac)] = cur.fetchall()

    assert isinstance(cpf_enc, bytes) and len(cpf_enc) == 40
    assert cpf.digits.encode() not in cpf_enc
    assert protector.decrypt(cpf_enc) == cpf
    assert cpf_hmac == protector.blind_index(cpf)
