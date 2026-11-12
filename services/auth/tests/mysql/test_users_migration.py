"""Migrations 0001-0004 do auth contra MySQL real: DDL físico, GRANT sem DELETE e REVOKE"""

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
    assert "`created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)" in ddl
    assert "UNIQUE KEY `uq_users_email`" in ddl


def test_runtime_user_has_dml_without_delete(migrated: Config) -> None:
    with _connect("auth_svc", AUTH_PASSWORD) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, name, password_hash) "
            "VALUES ('ana@example.com', 'Ana', '$argon2id$v=19$m=65536,t=3,p=4$test')"
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
