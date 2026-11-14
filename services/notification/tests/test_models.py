from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from notification_service.domain import NotificationStatus
from notification_service.models import IDEMPOTENCY_KEY_UNIQUE, Base, NotificationRecord
from veriditi_common.db import Database
from veriditi_common.db_types import utcnow


def test_metadata_only_has_notifications_sent() -> None:
    assert set(Base.metadata.tables) == {"notifications_sent"}


@pytest.mark.parametrize(
    "fragment",
    [
        "id BIGINT NOT NULL AUTO_INCREMENT",
        "idempotency_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL",
        "template VARCHAR(64) NOT NULL",
        "status ENUM('pending','sent','failed') NOT NULL DEFAULT 'pending'",
        "attempts TINYINT NOT NULL DEFAULT 0",
        "message_id VARCHAR(255),",
        "created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)",
        "sent_at DATETIME(6),",
        "CONSTRAINT uq_notifications_sent_idempotency_key UNIQUE (idempotency_key)",
        "CONSTRAINT ck_notifications_sent_attempts_non_negative CHECK (attempts >= 0)",
        "CONSTRAINT ck_notifications_sent_sent_requires_sent_at "
        "CHECK (status <> 'sent' OR sent_at IS NOT NULL)",
    ],
)
def test_mysql_ddl_matches_contract(fragment: str) -> None:
    ddl = str(CreateTable(NotificationRecord.__table__).compile(dialect=mysql.dialect()))

    assert fragment in ddl


def test_mysql_enum_has_no_extra_check() -> None:
    ddl = str(CreateTable(NotificationRecord.__table__).compile(dialect=mysql.dialect()))

    assert "ck_notifications_sent_status" not in ddl


def test_constraints_follow_naming_convention_without_indexes() -> None:
    table = NotificationRecord.__table__

    assert {c.name for c in table.constraints} == {
        "pk_notifications_sent",
        IDEMPOTENCY_KEY_UNIQUE,
        "ck_notifications_sent_attempts_non_negative",
        "ck_notifications_sent_sent_requires_sent_at",
        # Só no SQLite: no MySQL o ENUM nativo dispensa o CHECK
        "ck_notifications_sent_status",
    }
    assert table.indexes == set()


async def test_server_defaults_on_sqlite(db: Database) -> None:
    before = utcnow() - timedelta(seconds=1)
    async with db.session_factory() as session:
        record = NotificationRecord(idempotency_key="welcome:1", template="welcome")
        session.add(record)
        await session.commit()
        await session.refresh(record)

    assert record.status is NotificationStatus.PENDING
    assert record.attempts == 0
    assert record.message_id is None
    assert record.sent_at is None
    assert record.created_at.tzinfo is UTC
    assert before <= record.created_at <= utcnow() + timedelta(seconds=1)


async def test_sent_requires_sent_at(db: Database) -> None:
    async with db.session_factory() as session:
        record = NotificationRecord(idempotency_key="welcome:1", template="welcome")
        session.add(record)
        await session.commit()

        with pytest.raises(IntegrityError, match="sent_requires_sent_at"):
            await session.execute(update(NotificationRecord).values(status=NotificationStatus.SENT))
        await session.rollback()

        await session.execute(
            update(NotificationRecord).values(
                status=NotificationStatus.SENT, sent_at=datetime(2026, 11, 12, tzinfo=UTC)
            )
        )
        await session.commit()


async def test_attempts_cannot_be_negative(db: Database) -> None:
    async with db.session_factory() as session:
        session.add(
            NotificationRecord(idempotency_key="welcome:1", template="welcome", attempts=-1)
        )
        with pytest.raises(IntegrityError, match="attempts_non_negative"):
            await session.commit()
