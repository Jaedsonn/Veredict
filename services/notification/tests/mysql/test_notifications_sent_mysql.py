"""Migration 0001 do notification contra MySQL real: DDL físico, GRANT sem DELETE e REVOKE"""

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pymysql
import pytest
from alembic import command
from alembic.config import Config

from notification_service.config import get_settings

pytestmark = pytest.mark.mysql

ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"
HOST = os.environ.get("CONTRACT_DB_HOST", "127.0.0.1")
PORT = int(os.environ.get("CONTRACT_DB_PORT", "3317"))
MIGRATOR_PASSWORD = os.environ.get("DB_MIGRATOR_PASSWORD", "m")
RUNTIME = "notification_svc"
RUNTIME_PASSWORD = os.environ.get("NOTIFICATION_DB_PASSWORD", "n")
DB = "veriditi"
TABLE_ACCESS_DENIED = 1142
CHECK_VIOLATED = 3819
DATA_TRUNCATED = 1265

INSERT_ROW = (
    "INSERT INTO notifications_sent (idempotency_key, template) "
    "VALUES ('email_verification:1', 'email_verification')"
)


def _connect(database: str | None = DB) -> pymysql.Connection:
    return pymysql.connect(
        host=HOST,
        port=PORT,
        user=RUNTIME,
        password=RUNTIME_PASSWORD,
        database=database,
        autocommit=True,
    )


def _runtime_grants() -> str:
    # Sem database: depois do REVOKE o notification_svc não conecta ao veriditi (1044)
    with _connect(database=None) as conn, conn.cursor() as cur:
        cur.execute("SHOW GRANTS")
        return "\n".join(row[0] for row in cur.fetchall())


@pytest.fixture
def migrated(monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
    # Síncrono de propósito: o env.py chama asyncio.run e não pode rodar dentro de um loop
    for key, value in {
        "DB_HOST": HOST,
        "DB_PORT": str(PORT),
        "DB_NAME": DB,
        "DB_USER": RUNTIME,
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


def _ddl() -> str:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SHOW CREATE TABLE notifications_sent")
        return str(cur.fetchone()[1])  # type: ignore[index]


@pytest.mark.parametrize(
    "fragment",
    [
        "`id` bigint NOT NULL AUTO_INCREMENT",
        "`idempotency_key` varchar(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL",
        "`template` varchar(64) NOT NULL",
        "`status` enum('pending','sent','failed') NOT NULL DEFAULT 'pending'",
        "`attempts` tinyint NOT NULL DEFAULT '0'",
        "`message_id` varchar(255) DEFAULT NULL",
        "`created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)",
        "`sent_at` datetime(6) DEFAULT NULL",
        "PRIMARY KEY (`id`)",
        "UNIQUE KEY `uq_notifications_sent_idempotency_key` (`idempotency_key`)",
        "CONSTRAINT `ck_notifications_sent_attempts_non_negative` CHECK",
        "CONSTRAINT `ck_notifications_sent_sent_requires_sent_at` CHECK",
        "ENGINE=InnoDB",
    ],
)
def test_notifications_sent_has_contract_ddl(migrated: Config, fragment: str) -> None:
    assert fragment in _ddl()


def test_no_index_besides_pk_and_unique(migrated: Config) -> None:
    keys = re.findall(r"^\s*(?:UNIQUE |PRIMARY )?KEY .*$", _ddl(), flags=re.MULTILINE)

    assert [key.strip() for key in keys] == [
        "PRIMARY KEY (`id`),",
        "UNIQUE KEY `uq_notifications_sent_idempotency_key` (`idempotency_key`),",
    ]


def test_runtime_user_reads_inserts_and_updates_but_never_deletes(migrated: Config) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(INSERT_ROW)
        cur.execute("UPDATE notifications_sent SET status = 'failed', attempts = 3")
        cur.execute("SELECT status, attempts FROM notifications_sent")
        assert cur.fetchone() == ("failed", 3)

        for statement in (
            "DELETE FROM notifications_sent",
            "TRUNCATE notifications_sent",
            "ALTER TABLE notifications_sent ADD COLUMN x INT",
        ):
            with pytest.raises(pymysql.err.OperationalError) as exc:
                cur.execute(statement)
            assert exc.value.args[0] == TABLE_ACCESS_DENIED, statement

    grants = _runtime_grants()
    assert "GRANT SELECT, INSERT, UPDATE ON `veriditi`.`notifications_sent`" in grants
    assert "DELETE" not in grants


@pytest.mark.parametrize(
    ("statement", "errno"),
    [
        ("UPDATE notifications_sent SET attempts = -1", CHECK_VIOLATED),
        ("UPDATE notifications_sent SET status = 'sent'", CHECK_VIOLATED),
        ("UPDATE notifications_sent SET status = 'bogus'", DATA_TRUNCATED),
    ],
    ids=["negative-attempts", "sent-without-sent_at", "unknown-status"],
)
def test_checks_and_enum_refuse_invalid_rows(migrated: Config, statement: str, errno: int) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(INSERT_ROW)
        with pytest.raises(pymysql.err.MySQLError) as exc:
            cur.execute(statement)

    assert exc.value.args[0] == errno


def test_downgrade_revokes_table_grant(migrated: Config) -> None:
    assert "`veriditi`.`notifications_sent`" in _runtime_grants()

    command.downgrade(migrated, "base")

    assert "`notifications_sent`" not in _runtime_grants()
    command.upgrade(migrated, "head")
    assert "`veriditi`.`notifications_sent`" in _runtime_grants()
