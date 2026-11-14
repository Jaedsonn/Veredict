import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from types import TracebackType

import pymysql.err
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from structlog.testing import capture_logs

from notification_service.adapters.memory_repo import InMemoryNotificationRepository
from notification_service.adapters.sqlalchemy_repo import (
    SqlAlchemyNotificationRepository,
    is_duplicate_idempotency_key,
)
from notification_service.domain import NotificationStatus
from notification_service.models import NotificationRecord
from notification_service.ports import NotificationRepository
from veriditi_common.db import Database

BRT = timezone(timedelta(hours=-3))
CREATED_AT = datetime(2026, 11, 12, 15, 0, 0, 123456, tzinfo=UTC)
SENT_AT = datetime(2026, 11, 12, 15, 0, 3, 654321, tzinfo=UTC)
MID = "<fixed-1@veriditi.app>"


@pytest.fixture(params=["memory", "sqlite"])
async def repo(
    request: pytest.FixtureRequest, db: Database
) -> AsyncIterator[NotificationRepository]:
    """Os mesmos testes provam que o fake é fiel ao adapter SQL"""
    if request.param == "memory":
        yield InMemoryNotificationRepository()
    else:
        yield SqlAlchemyNotificationRepository(db.session_factory)


async def _add(repo: NotificationRepository, key: str = "email_verification:1") -> int:
    notification_id = await repo.add(key, "email_verification", created_at=CREATED_AT)
    assert notification_id is not None
    return notification_id


async def test_add_returns_sequential_ids_and_none_for_known_key(
    repo: NotificationRepository,
) -> None:
    assert await repo.add("welcome:1", "welcome", created_at=CREATED_AT) == 1
    assert await repo.add("welcome:2", "welcome", created_at=CREATED_AT) == 2
    assert await repo.add("welcome:1", "welcome", created_at=CREATED_AT) is None


async def test_new_reservation_is_pending(repo: NotificationRepository) -> None:
    await repo.add("welcome:1", "welcome", created_at=CREATED_AT.astimezone(BRT))

    stored = await repo.get("welcome:1")

    assert stored is not None
    assert (stored.id, stored.idempotency_key, stored.template) == (1, "welcome:1", "welcome")
    assert stored.status is NotificationStatus.PENDING
    assert (stored.attempts, stored.message_id, stored.sent_at) == (0, None, None)
    assert stored.created_at == CREATED_AT
    assert stored.created_at.tzinfo is UTC


async def test_get_unknown_key_is_none(repo: NotificationRepository) -> None:
    assert await repo.get("welcome:404") is None


async def test_key_comparison_is_case_sensitive(repo: NotificationRepository) -> None:
    assert await repo.add("Key", "welcome", created_at=CREATED_AT) == 1
    assert await repo.add("key", "welcome", created_at=CREATED_AT) == 2


async def test_mark_sent_from_pending(repo: NotificationRepository) -> None:
    notification_id = await _add(repo)

    assert await repo.mark_sent(notification_id, attempts=2, message_id=MID, sent_at=SENT_AT)

    stored = await repo.get("email_verification:1")
    assert stored is not None
    assert stored.status is NotificationStatus.SENT
    assert (stored.attempts, stored.message_id, stored.sent_at) == (2, MID, SENT_AT)
    assert stored.sent_at is not None and stored.sent_at.tzinfo is UTC


async def test_mark_failed_from_pending(repo: NotificationRepository) -> None:
    notification_id = await _add(repo)

    assert await repo.mark_failed(notification_id, attempts=3)

    stored = await repo.get("email_verification:1")
    assert stored is not None
    assert stored.status is NotificationStatus.FAILED
    assert (stored.attempts, stored.message_id, stored.sent_at) == (3, None, None)


@pytest.mark.parametrize(
    ("first", "second"),
    [("sent", "failed"), ("failed", "sent"), ("sent", "sent"), ("failed", "failed")],
)
async def test_finished_rows_never_change(
    repo: NotificationRepository, first: str, second: str
) -> None:
    notification_id = await _add(repo)

    async def finish(status: str, attempts: int) -> bool:
        if status == "sent":
            return await repo.mark_sent(
                notification_id, attempts=attempts, message_id=MID, sent_at=SENT_AT
            )
        return await repo.mark_failed(notification_id, attempts=attempts)

    assert await finish(first, 1) is True
    assert await finish(second, 3) is False

    stored = await repo.get("email_verification:1")
    assert stored is not None
    assert (stored.status.value, stored.attempts) == (first, 1)


async def test_mark_unknown_id_is_false(repo: NotificationRepository) -> None:
    assert await repo.mark_failed(99, attempts=1) is False
    assert await repo.mark_sent(99, attempts=1, message_id=MID, sent_at=SENT_AT) is False


async def test_sqlite_row_keeps_microseconds_in_utc(db: Database) -> None:
    repo = SqlAlchemyNotificationRepository(db.session_factory)
    notification_id = await _add(repo)
    await repo.mark_sent(
        notification_id, attempts=1, message_id=MID, sent_at=SENT_AT.astimezone(BRT)
    )

    async with db.session_factory() as session:
        record = await session.scalar(select(NotificationRecord))

    assert record is not None
    assert record.created_at == CREATED_AT
    assert record.sent_at == SENT_AT
    assert record.sent_at is not None and record.sent_at.tzinfo is UTC


def _integrity_error(orig: Exception) -> IntegrityError:
    return IntegrityError("INSERT INTO notifications_sent ...", {}, orig)


@pytest.mark.parametrize(
    ("orig", "expected"),
    [
        (
            pymysql.err.IntegrityError(
                1062,
                "Duplicate entry 'x' for key "
                "'notifications_sent.uq_notifications_sent_idempotency_key'",
            ),
            True,
        ),
        (
            pymysql.err.IntegrityError(
                1062, "Duplicate entry '1' for key 'notifications_sent.PRIMARY'"
            ),
            False,
        ),
        (
            pymysql.err.IntegrityError(
                3819, "Check constraint 'ck_notifications_sent_attempts_non_negative' is violated."
            ),
            False,
        ),
        (
            sqlite3.IntegrityError("UNIQUE constraint failed: notifications_sent.idempotency_key"),
            True,
        ),
        (sqlite3.IntegrityError("CHECK constraint failed: attempts_non_negative"), False),
    ],
    ids=["mysql-key", "mysql-primary", "mysql-check", "sqlite-key", "sqlite-check"],
)
def test_is_duplicate_idempotency_key(orig: Exception, expected: bool) -> None:
    assert is_duplicate_idempotency_key(_integrity_error(orig)) is expected


class _ScriptedSessions:
    """Fábrica de sessões falsas: cada commit consome o próximo resultado do roteiro"""

    def __init__(self, *outcomes: Exception | None) -> None:
        self.outcomes = list(outcomes)
        self.added = 0
        self.rollbacks = 0

    def __call__(self) -> "_ScriptedSessions":
        return self

    async def __aenter__(self) -> "_ScriptedSessions":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def add(self, record: NotificationRecord) -> None:
        self.added += 1
        record.id = self.added

    async def commit(self) -> None:
        if (outcome := self.outcomes.pop(0)) is not None:
            raise outcome

    async def rollback(self) -> None:
        self.rollbacks += 1


def _operational(errno: int) -> OperationalError:
    return OperationalError("INSERT ...", {}, pymysql.err.OperationalError(errno, "x"))


DUPLICATE = _integrity_error(
    pymysql.err.IntegrityError(
        1062,
        "Duplicate entry 'x' for key 'notifications_sent.uq_notifications_sent_idempotency_key'",
    )
)
CHECK_FAILED = _integrity_error(sqlite3.IntegrityError("CHECK constraint failed: x"))


def _scripted_repo(sessions: _ScriptedSessions) -> SqlAlchemyNotificationRepository:
    return SqlAlchemyNotificationRepository(sessions)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("second", "expected"),
    [(None, 2), (DUPLICATE, None)],
    ids=["retry-inserts", "retry-finds-duplicate"],
)
async def test_deadlock_is_retried_once(second: Exception | None, expected: int | None) -> None:
    sessions = _ScriptedSessions(_operational(1213), second)

    with capture_logs() as logs:
        result = await _scripted_repo(sessions).add("k", "welcome", created_at=CREATED_AT)

    assert result == expected
    assert sessions.added == 2
    assert sessions.rollbacks == (1 if second is None else 2)
    assert [line["event"] for line in logs] == ["notification_insert_retried"]
    assert (logs[0]["db_errno"], logs[0]["idempotency_key"]) == (1213, "k")


async def test_second_deadlock_is_raised() -> None:
    sessions = _ScriptedSessions(_operational(1213), _operational(1213))

    with pytest.raises(OperationalError):
        await _scripted_repo(sessions).add("k", "welcome", created_at=CREATED_AT)

    assert (sessions.added, sessions.rollbacks) == (2, 2)


@pytest.mark.parametrize("errno", [1205, 2013], ids=["lock-wait-timeout", "lost-connection"])
async def test_other_operational_errors_are_not_retried(errno: int) -> None:
    sessions = _ScriptedSessions(_operational(errno))

    with pytest.raises(OperationalError):
        await _scripted_repo(sessions).add("k", "welcome", created_at=CREATED_AT)

    assert (sessions.added, sessions.rollbacks) == (1, 1)


async def test_other_integrity_errors_are_raised_after_rollback() -> None:
    sessions = _ScriptedSessions(CHECK_FAILED)

    with pytest.raises(IntegrityError) as exc:
        await _scripted_repo(sessions).add("k", "welcome", created_at=CREATED_AT)

    assert exc.value is CHECK_FAILED
    assert sessions.rollbacks == 1
