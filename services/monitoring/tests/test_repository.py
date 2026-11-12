import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pymysql.err
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from structlog.testing import capture_logs

from monitoring_service.adapters.memory_repo import InMemoryAuditEventRepository
from monitoring_service.adapters.sqlalchemy_repo import (
    SqlAlchemyAuditEventRepository,
    is_duplicate_event_id,
)
from monitoring_service.domain import AuditEventFilter, StoredAuditEvent
from monitoring_service.models import AuditEventRecord
from monitoring_service.ports import AuditEventRepository
from veriditi_common.audit import AuditEvent, AuditOutcome
from veriditi_common.db import Database

BRT = timezone(timedelta(hours=-3))


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


async def _search(
    repo: AuditEventRepository,
    filters: AuditEventFilter | None = None,
    *,
    after_id: int | None = None,
    limit: int = 50,
) -> list[StoredAuditEvent]:
    return await repo.search(filters or AuditEventFilter(), after_id=after_id, limit=limit)


async def test_roundtrip_keeps_microseconds_utc_and_empty_metadata(
    repo: AuditEventRepository, received_at: datetime
) -> None:
    occurred = datetime(2026, 11, 12, 9, 0, 0, 123456, tzinfo=BRT)
    event = _event(occurred_at=occurred, actor_id=42, actor_ip="203.0.113.7", request_id=uuid4())
    await repo.add(event, received_at=received_at)

    [stored] = await _search(repo)

    assert stored.id == 1
    assert stored.event_id == event.event_id
    assert stored.occurred_at == datetime(2026, 11, 12, 12, 0, 0, 123456, tzinfo=UTC)
    assert stored.occurred_at.tzinfo is UTC
    assert stored.received_at == received_at
    assert stored.outcome is AuditOutcome.SUCCESS
    assert (stored.actor_id, stored.actor_ip) == (42, "203.0.113.7")
    assert stored.request_id == event.request_id
    assert stored.metadata == {}


async def test_get_finds_by_event_id(repo: AuditEventRepository, received_at: datetime) -> None:
    event = _event(metadata={"plan": "pro"})
    await repo.add(event, received_at=received_at)

    stored = await repo.get(event.event_id)

    assert stored is not None
    assert (stored.event_id, stored.metadata) == (event.event_id, {"plan": "pro"})
    assert await repo.get(uuid4()) is None


async def _seed(repo: AuditEventRepository, received_at: datetime) -> None:
    hour = timedelta(hours=1)
    base = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
    for occurred, actor_id, action in [
        (base, 1, "auth.user.registered"),
        (base + hour, 2, "auth.user.registered"),
        (base + 2 * hour, 1, "auth.user.logged_in"),
        # Fora de ordem: a ordem do resultado é a do id, não a de occurred_at
        (base - hour, 1, "auth.user.logged_in"),
    ]:
        event = _event(occurred_at=occurred, actor_id=actor_id, action=action)
        await repo.add(event, received_at=received_at)


@pytest.mark.parametrize(
    ("filters", "after_id", "limit", "expected_ids"),
    [
        (AuditEventFilter(), None, 50, [1, 2, 3, 4]),
        (AuditEventFilter(actor_id=1), None, 50, [1, 3, 4]),
        (AuditEventFilter(action="auth.user.logged_in"), None, 50, [3, 4]),
        (
            AuditEventFilter(
                occurred_from=datetime(2026, 11, 12, 12, 0, tzinfo=UTC),
                occurred_to=datetime(2026, 11, 12, 14, 0, tzinfo=UTC),
            ),
            None,
            50,
            [1, 2],
        ),
        (
            AuditEventFilter(occurred_from=datetime(2026, 11, 12, 10, 0, tzinfo=BRT)),
            None,
            50,
            [2, 3],
        ),
        (AuditEventFilter(actor_id=1, action="auth.user.logged_in"), None, 50, [3, 4]),
        (AuditEventFilter(), 2, 50, [3, 4]),
        (AuditEventFilter(), None, 2, [1, 2]),
        (AuditEventFilter(actor_id=99), None, 50, []),
    ],
    ids=[
        "all",
        "actor",
        "action",
        "from-inclusive-to-exclusive",
        "from-offset",
        "combined",
        "after_id",
        "limit",
        "none",
    ],
)
async def test_search(
    repo: AuditEventRepository,
    received_at: datetime,
    filters: AuditEventFilter,
    after_id: int | None,
    limit: int,
    expected_ids: list[int],
) -> None:
    await _seed(repo, received_at)

    found = await _search(repo, filters, after_id=after_id, limit=limit)

    assert [row.id for row in found] == expected_ids


async def test_sqlite_roundtrip_keeps_microseconds_in_utc(
    db: Database, received_at: datetime
) -> None:
    occurred = datetime(2026, 11, 12, 9, 0, 0, 123456, tzinfo=BRT)
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


class _ScriptedSession:
    """Cada commit consome o próximo resultado: None é sucesso, exceção é levantada"""

    def __init__(self, *outcomes: Exception | None) -> None:
        self.outcomes = list(outcomes)
        self.added = 0
        self.rollbacks = 0

    def add(self, record: object) -> None:
        self.added += 1

    async def commit(self) -> None:
        if (outcome := self.outcomes.pop(0)) is not None:
            raise outcome

    async def rollback(self) -> None:
        self.rollbacks += 1


def _operational(errno: int) -> OperationalError:
    return OperationalError("INSERT ...", {}, pymysql.err.OperationalError(errno, "x"))


DUPLICATE = _integrity_error(
    pymysql.err.IntegrityError(
        1062, "Duplicate entry 'x' for key 'audit_events.uq_audit_events_event_id'"
    )
)


@pytest.mark.parametrize(
    ("second", "expected"),
    [(None, True), (DUPLICATE, False)],
    ids=["retry-inserts", "retry-finds-duplicate"],
)
@pytest.mark.parametrize("errno", [1213, 1205], ids=["deadlock", "lock-wait-timeout"])
async def test_deadlock_is_retried_once(
    received_at: datetime, errno: int, second: Exception | None, expected: bool
) -> None:
    session = _ScriptedSession(_operational(errno), second)
    repo = SqlAlchemyAuditEventRepository(session)  # type: ignore[arg-type]

    with capture_logs() as logs:
        assert await repo.add(_event(), received_at=received_at) is expected

    assert session.added == 2
    assert session.rollbacks == (1 if second is None else 2)
    assert [line["event"] for line in logs] == ["audit_insert_retried"]
    assert logs[0]["db_errno"] == errno


async def test_second_deadlock_is_raised(received_at: datetime) -> None:
    session = _ScriptedSession(_operational(1213), _operational(1213))
    repo = SqlAlchemyAuditEventRepository(session)  # type: ignore[arg-type]

    with pytest.raises(OperationalError):
        await repo.add(_event(), received_at=received_at)

    assert (session.added, session.rollbacks) == (2, 2)


async def test_other_operational_errors_are_not_retried(received_at: datetime) -> None:
    session = _ScriptedSession(_operational(2013))
    repo = SqlAlchemyAuditEventRepository(session)  # type: ignore[arg-type]

    with pytest.raises(OperationalError):
        await repo.add(_event(), received_at=received_at)

    assert (session.added, session.rollbacks) == (1, 1)
