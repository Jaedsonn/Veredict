import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pymysql.err
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from monitoring_service.adapters.memory_repo import InMemoryAuditEventRepository
from monitoring_service.adapters.sqlalchemy_repo import (
    SqlAlchemyAuditEventRepository,
    is_duplicate_event_id,
)
from monitoring_service.models import AuditEventRecord
from monitoring_service.ports import AuditEventRepository
from veriditi_common.audit import AuditEvent, AuditOutcome
from veriditi_common.db import Database


def _event(**overrides: Any) -> AuditEvent:
    values: dict[str, Any] = {
        "service": "auth",
        "action": "auth.user.registered",
        "outcome": AuditOutcome.SUCCESS,
        "request_id": None,
    }
    values.update(overrides)
    return AuditEvent(**values)


@pytest.fixture(params=["memory", "sqlite"])
async def repo(request: pytest.FixtureRequest, db: Database) -> AsyncIterator[AuditEventRepository]:
    """Os mesmos testes provam que o fake é fiel ao adapter SQL"""
    if request.param == "memory":
        yield InMemoryAuditEventRepository()
        return
    async with db.session_factory() as session:
        yield SqlAlchemyAuditEventRepository(session)


async def test_add_returns_false_for_known_event_id(
    repo: AuditEventRepository, received_at: datetime
) -> None:
    event = _event()

    assert await repo.add(event, received_at=received_at) is True
    assert await repo.add(event, received_at=received_at) is False
    assert await repo.add(_event(), received_at=received_at) is True


async def test_sqlite_roundtrip_keeps_microseconds_in_utc(
    db: Database, received_at: datetime
) -> None:
    occurred = datetime(2026, 11, 12, 9, 0, 0, 123456, tzinfo=timezone(timedelta(hours=-3)))
    event = _event(occurred_at=occurred, actor_ip="2001:db8::1", request_id=uuid4())
    async with db.session_factory() as session:
        await SqlAlchemyAuditEventRepository(session).add(event, received_at=received_at)

    async with db.session_factory() as session:
        record = await session.scalar(select(AuditEventRecord))

    assert record is not None
    assert record.occurred_at == datetime(2026, 11, 12, 12, 0, 0, 123456, tzinfo=UTC)
    assert record.occurred_at.tzinfo is UTC
    assert record.received_at == received_at
    assert record.request_id == event.request_id
    assert record.actor_ip == "2001:db8::1"


async def test_empty_metadata_is_sql_null(db: Database, received_at: datetime) -> None:
    async with db.session_factory() as session:
        await SqlAlchemyAuditEventRepository(session).add(_event(), received_at=received_at)
        is_null = await session.scalar(text("SELECT metadata IS NULL FROM audit_events"))

    assert is_null == 1


def _integrity_error(orig: Exception) -> IntegrityError:
    return IntegrityError("INSERT INTO audit_events ...", {}, orig)


@pytest.mark.parametrize(
    ("orig", "expected"),
    [
        (
            pymysql.err.IntegrityError(
                1062, "Duplicate entry 'x' for key 'audit_events.uq_audit_events_event_id'"
            ),
            True,
        ),
        (
            pymysql.err.IntegrityError(1062, "Duplicate entry '1' for key 'audit_events.PRIMARY'"),
            False,
        ),
        (pymysql.err.IntegrityError(1048, "Column 'service' cannot be null"), False),
        (sqlite3.IntegrityError("UNIQUE constraint failed: audit_events.event_id"), True),
        (sqlite3.IntegrityError("NOT NULL constraint failed: audit_events.service"), False),
    ],
)
def test_is_duplicate_event_id(orig: Exception, expected: bool) -> None:
    assert is_duplicate_event_id(_integrity_error(orig)) is expected


class _FailingSession:
    def __init__(self, error: IntegrityError) -> None:
        self.error = error
        self.rolled_back = False

    def add(self, record: object) -> None:
        pass

    async def commit(self) -> None:
        raise self.error

    async def rollback(self) -> None:
        self.rolled_back = True


async def test_other_integrity_errors_are_raised_after_rollback(received_at: datetime) -> None:
    error = _integrity_error(sqlite3.IntegrityError("NOT NULL constraint failed: x.y"))
    session = _FailingSession(error)
    repo = SqlAlchemyAuditEventRepository(session)  # type: ignore[arg-type]

    with pytest.raises(IntegrityError) as exc:
        await repo.add(_event(), received_at=received_at)

    assert exc.value is error
    assert session.rolled_back is True
