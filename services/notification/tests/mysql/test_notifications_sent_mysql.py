"""Migration 0001 do notification contra MySQL real: DDL físico, GRANT sem DELETE e REVOKE"""

import asyncio
import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pymysql
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, func, select

from notification_service.adapters.sqlalchemy_repo import SqlAlchemyNotificationRepository
from notification_service.config import get_settings
from notification_service.domain import NotificationStatus, StoredNotification
from notification_service.models import NotificationRecord
from veriditi_common.db import Database

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


def _runtime_database() -> Database:
    url = URL.create(
        "mysql+aiomysql",
        username=RUNTIME,
        password=RUNTIME_PASSWORD,
        host=HOST,
        port=PORT,
        database=DB,
        query={"charset": "utf8mb4"},
    )
    return Database(url.render_as_string(hide_password=False))


async def _count(db: Database) -> int:
    async with db.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(NotificationRecord))
    return int(count or 0)


def test_concurrent_reservations_store_one_row(migrated: Config) -> None:
    # Síncrono com asyncio.run: a fixture migrated já usa o asyncio.run do env.py
    created_at = datetime.now(UTC)

    async def scenario() -> tuple[list[int | None], int]:
        db = _runtime_database()
        repo = SqlAlchemyNotificationRepository(db.session_factory)
        try:
            results = await asyncio.gather(
                *(repo.add("welcome:7", "welcome", created_at=created_at) for _ in range(5))
            )
            count = await _count(db)
        finally:
            await db.dispose()
        return list(results), count

    results, count = asyncio.run(scenario())

    assert sum(isinstance(result, int) for result in results) == 1
    assert results.count(None) == 4
    assert count == 1


def test_reservations_waiting_on_a_rolled_back_insert_survive_the_deadlock(
    migrated: Config,
) -> None:
    # As repetições esperam o lock da 1ª reserva; quando ela desfaz, o InnoDB escolhe vítimas 1213
    async def scenario() -> tuple[list[int | None], int]:
        db = _runtime_database()
        repo = SqlAlchemyNotificationRepository(db.session_factory)
        first = _connect()
        first.autocommit(False)
        try:
            with first.cursor() as cur:
                cur.execute(
                    "INSERT INTO notifications_sent (idempotency_key, template) "
                    "VALUES ('welcome:8', 'welcome')"
                )
            tasks = [
                asyncio.create_task(repo.add("welcome:8", "welcome", created_at=datetime.now(UTC)))
                for _ in range(3)
            ]
            await asyncio.sleep(1.0)
            first.rollback()
            results = await asyncio.gather(*tasks)
            count = await _count(db)
        finally:
            first.close()
            await db.dispose()
        return list(results), count

    results, count = asyncio.run(scenario())

    assert sum(isinstance(result, int) for result in results) == 1
    assert results.count(None) == 2
    assert count == 1


def test_roundtrip_and_conditional_update(migrated: Config) -> None:
    brt = timezone(timedelta(hours=-3))
    created_at = datetime(2026, 11, 12, 9, 0, 0, 123456, tzinfo=brt)
    sent_at = datetime(2026, 11, 12, 15, 0, 3, 654321, tzinfo=UTC)
    mid = "<fixed-1@veriditi.app>"

    async def scenario() -> tuple[list[bool], StoredNotification | None, list[int | None]]:
        db = _runtime_database()
        repo = SqlAlchemyNotificationRepository(db.session_factory)
        try:
            notification_id = await repo.add("Key", "welcome", created_at=created_at)
            assert notification_id is not None
            outcomes = [
                await repo.mark_sent(notification_id, attempts=1, message_id=mid, sent_at=sent_at),
                await repo.mark_sent(notification_id, attempts=2, message_id=mid, sent_at=sent_at),
                await repo.mark_failed(notification_id, attempts=3),
            ]
            stored = await repo.get("Key")
            # ascii_bin: a caixa diferencia a chave
            others = [
                await repo.add("key", "welcome", created_at=created_at),
                await repo.add("Key", "welcome", created_at=created_at),
            ]
        finally:
            await db.dispose()
        return outcomes, stored, others

    outcomes, stored, others = asyncio.run(scenario())

    assert outcomes == [True, False, False]
    assert stored is not None
    assert stored.status is NotificationStatus.SENT
    assert (stored.attempts, stored.message_id) == (1, mid)
    assert stored.created_at == datetime(2026, 11, 12, 12, 0, 0, 123456, tzinfo=UTC)
    assert stored.created_at.tzinfo is UTC
    assert stored.sent_at == sent_at
    assert stored.sent_at is not None and stored.sent_at.tzinfo is UTC
    assert isinstance(others[0], int)
    assert others[1] is None
