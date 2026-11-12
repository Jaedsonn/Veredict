"""Migration 0001 do monitoring contra MySQL real: DDL físico, GRANT append-only e REVOKE"""

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pymysql
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, func, select

from monitoring_service.adapters.sqlalchemy_repo import SqlAlchemyAuditEventRepository
from monitoring_service.config import get_settings
from monitoring_service.models import AuditEventRecord
from veriditi_common.audit import AuditEvent, AuditOutcome
from veriditi_common.db import Database

pytestmark = pytest.mark.mysql

ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"
HOST = os.environ.get("CONTRACT_DB_HOST", "127.0.0.1")
PORT = int(os.environ.get("CONTRACT_DB_PORT", "3317"))
MIGRATOR_PASSWORD = os.environ.get("DB_MIGRATOR_PASSWORD", "m")
WRITER = "veriditi_logs_writer"
WRITER_PASSWORD = os.environ.get("LOGS_DB_PASSWORD", "l")
LOGS_DB = "veriditi_logs"
TABLE_ACCESS_DENIED = 1142

INSERT_EVENT = (
    "INSERT INTO audit_events (event_id, occurred_at, service, action, outcome) "
    "VALUES ('8d0b3f0e-6a51-4c1e-9a43-2f4f7f1c9b11', '2026-11-12 12:00:00.123456', "
    "'auth', 'auth.user.registered', 'success')"
)


def _connect(database: str | None = LOGS_DB) -> pymysql.Connection:
    return pymysql.connect(
        host=HOST,
        port=PORT,
        user=WRITER,
        password=WRITER_PASSWORD,
        database=database,
        autocommit=True,
    )


def _writer_grants() -> str:
    # Sem database: depois do REVOKE o writer não conecta ao veriditi_logs (1044)
    with _connect(database=None) as conn, conn.cursor() as cur:
        cur.execute("SHOW GRANTS")
        return "\n".join(row[0] for row in cur.fetchall())


@pytest.fixture
def migrated(monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
    # Síncrono de propósito: o env.py chama asyncio.run e não pode rodar dentro de um loop
    for key, value in {
        "DB_HOST": HOST,
        "DB_PORT": str(PORT),
        "DB_NAME": LOGS_DB,
        "DB_USER": WRITER,
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


@pytest.mark.parametrize(
    "fragment",
    [
        "`id` bigint NOT NULL AUTO_INCREMENT",
        "`event_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL",
        "`occurred_at` datetime(6) NOT NULL",
        "`received_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)",
        "`outcome` enum('success','failure') NOT NULL",
        "`actor_id` bigint DEFAULT NULL",
        "`actor_ip` varchar(45) DEFAULT NULL",
        "`request_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL",
        "`metadata` json DEFAULT NULL",
        "UNIQUE KEY `uq_audit_events_event_id`",
        "KEY `ix_audit_events_actor_id_occurred_at` (`actor_id`,`occurred_at`)",
        "KEY `ix_audit_events_action_occurred_at` (`action`,`occurred_at`)",
        "ENGINE=InnoDB",
    ],
)
def test_audit_events_has_contract_ddl(migrated: Config, fragment: str) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SHOW CREATE TABLE audit_events")
        ddl = cur.fetchone()[1]  # type: ignore[index]

    assert fragment in ddl
    assert "hash" not in ddl


def test_writer_can_only_append(migrated: Config) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(INSERT_EVENT)
        cur.execute("SELECT action FROM audit_events")
        assert cur.fetchone() == ("auth.user.registered",)

        for statement in (
            "UPDATE audit_events SET action = 'auth.user.tampered'",
            "DELETE FROM audit_events",
            "TRUNCATE audit_events",
            "ALTER TABLE audit_events ADD COLUMN x INT",
        ):
            with pytest.raises(pymysql.err.OperationalError) as exc:
                cur.execute(statement)
            assert exc.value.args[0] == TABLE_ACCESS_DENIED, statement

    grants = _writer_grants()
    assert "GRANT SELECT, INSERT ON `veriditi_logs`.`audit_events`" in grants
    assert "UPDATE" not in grants
    assert "DELETE" not in grants


def test_downgrade_revokes_table_grant(migrated: Config) -> None:
    assert "`veriditi_logs`.`audit_events`" in _writer_grants()

    command.downgrade(migrated, "base")

    assert "`audit_events`" not in _writer_grants()
    command.upgrade(migrated, "head")


def _writer_database() -> Database:
    url = URL.create(
        "mysql+aiomysql",
        username=WRITER,
        password=WRITER_PASSWORD,
        host=HOST,
        port=PORT,
        database=LOGS_DB,
        query={"charset": "utf8mb4"},
    )
    return Database(url.render_as_string(hide_password=False))


def _event(**overrides: object) -> AuditEvent:
    values: dict[str, object] = {
        "service": "auth",
        "action": "auth.user.registered",
        "outcome": AuditOutcome.SUCCESS,
        "request_id": None,
    }
    values.update(overrides)
    return AuditEvent(**values)  # type: ignore[arg-type]


def test_concurrent_resends_store_one_row(migrated: Config) -> None:
    # Síncrono com asyncio.run: a fixture migrated já usa o asyncio.run do env.py
    event = _event()
    received_at = datetime.now(UTC)

    async def scenario() -> tuple[list[bool], int]:
        db = _writer_database()

        async def add() -> bool:
            async with db.session_factory() as session:
                repo = SqlAlchemyAuditEventRepository(session)
                return await repo.add(event, received_at=received_at)

        try:
            results = await asyncio.gather(*(add() for _ in range(5)))
            async with db.session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(AuditEventRecord))
        finally:
            await db.dispose()
        return sorted(results), int(count or 0)

    results, count = asyncio.run(scenario())

    assert results == [False, False, False, False, True]
    assert count == 1


def test_roundtrip_keeps_microseconds_in_utc(migrated: Config) -> None:
    occurred = datetime(2026, 11, 12, 9, 0, 0, 123456, tzinfo=timezone(timedelta(hours=-3)))
    received_at = datetime(2026, 11, 12, 15, 0, 0, 654321, tzinfo=UTC)
    event = _event(occurred_at=occurred)

    async def scenario() -> AuditEventRecord | None:
        db = _writer_database()
        try:
            async with db.session_factory() as session:
                await SqlAlchemyAuditEventRepository(session).add(event, received_at=received_at)
            async with db.session_factory() as session:
                return await session.scalar(select(AuditEventRecord))
        finally:
            await db.dispose()

    record = asyncio.run(scenario())

    assert record is not None
    assert record.occurred_at == datetime(2026, 11, 12, 12, 0, 0, 123456, tzinfo=UTC)
    assert record.occurred_at.tzinfo is UTC
    assert record.received_at == received_at
    assert record.event_id == event.event_id
