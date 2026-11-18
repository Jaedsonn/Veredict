"""Migrations do auth contra MySQL real: DDL físico, GRANTs, ENUMs e REVOKE no downgrade"""

import os
from collections.abc import Iterator
from pathlib import Path

import pymysql
import pytest
from alembic import command
from alembic.config import Config

from auth_service.config import get_settings

pytestmark = pytest.mark.mysql

ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"
HOST = os.environ.get("CONTRACT_DB_HOST", "127.0.0.1")
PORT = int(os.environ.get("CONTRACT_DB_PORT", "3317"))
MIGRATOR_PASSWORD = os.environ.get("DB_MIGRATOR_PASSWORD", "m")
AUTH_PASSWORD = os.environ.get("AUTH_DB_PASSWORD", "a")
TABLE_ACCESS_DENIED = 1142


def _connect(user: str, password: str, database: str | None = "veriditi") -> pymysql.Connection:
    return pymysql.connect(
        host=HOST, port=PORT, user=user, password=password, database=database, autocommit=True
    )


def _auth_grants() -> str:
    # SHOW GRANTS FOR outro usuário exige SELECT em mysql.*, que o migrator não tem
    with _connect("auth_svc", AUTH_PASSWORD, database=None) as conn, conn.cursor() as cur:
        cur.execute("SHOW GRANTS")
        return "\n".join(row[0] for row in cur.fetchall())


@pytest.fixture
def migrated(monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
    # Síncrono de propósito: o env.py chama asyncio.run e não pode rodar dentro de um loop
    for key, value in {
        "DB_HOST": HOST,
        "DB_PORT": str(PORT),
        "DB_NAME": "veriditi",
        "DB_USER": "auth_svc",
        "DB_MIGRATOR_USER": "migrator",
        "DB_MIGRATOR_PASSWORD": MIGRATOR_PASSWORD,
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    yield cfg
    command.downgrade(cfg, "base")
    get_settings.cache_clear()


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
        cur.execute(
            "INSERT INTO users (email, name, password_hash) "
            "VALUES ('ana@example.com', 'Ana', '$argon2id$stub')"
        )
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
        cur.execute(
            "INSERT INTO users (email, name, password_hash) "
            "VALUES ('rt@example.com', 'Rt', '$argon2id$stub')"
        )
        user_id = cur.lastrowid
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
        cur.execute(
            "INSERT INTO users (email, name, password_hash) "
            "VALUES ('dg@example.com', 'Dg', '$argon2id$stub')"
        )
        cur.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, family_id, expires_at, "
            "revoked_at, revoke_reason) VALUES (%s, %s, %s, UTC_TIMESTAMP(6), "
            "UTC_TIMESTAMP(6), 'password_reset')",
            (cur.lastrowid, "b" * 64, "0" * 8 + "-0000-0000-0000-" + "0" * 12),
        )

    command.downgrade(migrated, "0004")

    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute("SELECT revoke_reason FROM refresh_tokens")
        assert cur.fetchone() == ("logout",)
    assert "`password_reset_tokens`" not in _auth_grants()
    command.upgrade(migrated, "head")
