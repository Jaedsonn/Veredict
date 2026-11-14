import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from monitoring_service.models import EVENT_ID_UNIQUE, AuditEventRecord, Base
from veriditi_common.audit import AuditOutcome
from veriditi_common.db import Database
from veriditi_common.db_types import utcnow


def test_metadata_only_has_audit_events() -> None:
    assert set(Base.metadata.tables) == {"audit_events"}


@pytest.mark.parametrize(
    "fragment",
    [
        "id BIGINT NOT NULL AUTO_INCREMENT",
        "event_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL",
        "occurred_at DATETIME(6) NOT NULL",
        "received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)",
        "outcome ENUM('success','failure') NOT NULL",
        "request_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin,",
        "metadata JSON",
        "CONSTRAINT uq_audit_events_event_id UNIQUE (event_id)",
    ],
)
def test_mysql_ddl_matches_contract(fragment: str) -> None:
    ddl = str(CreateTable(AuditEventRecord.__table__).compile(dialect=mysql.dialect()))

    assert fragment in ddl


def test_constraints_and_indexes_follow_naming_convention() -> None:
    table = AuditEventRecord.__table__

    assert {"pk_audit_events", EVENT_ID_UNIQUE} <= {c.name for c in table.constraints}
    assert {i.name for i in table.indexes} == {
        "ix_audit_events_actor_id_occurred_at",
        "ix_audit_events_action_occurred_at",
    }


async def test_received_at_defaults_to_server_clock_in_utc(db: Database) -> None:
    before = utcnow() - timedelta(seconds=1)
    async with db.session_factory() as session:
        record = AuditEventRecord(
            event_id=uuid.uuid4(),
            occurred_at=datetime(2026, 11, 12, 12, 0, tzinfo=UTC),
            service="auth",
            action="auth.user.registered",
            outcome=AuditOutcome.SUCCESS,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)

    assert record.received_at.tzinfo is UTC
    assert before <= record.received_at <= utcnow() + timedelta(seconds=1)
    assert record.metadata_ is None
