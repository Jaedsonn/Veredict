from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from structlog.testing import capture_logs

from monitoring_service.adapters.memory_repo import InMemoryAuditEventRepository
from monitoring_service.use_cases.ingest_event import IngestAuditEvent
from veriditi_common.audit import AuditEvent, AuditOutcome
from veriditi_common.logging import REDACTED


def _event(**overrides: Any) -> AuditEvent:
    values: dict[str, Any] = {
        "service": "auth",
        "action": "auth.user.registered",
        "outcome": AuditOutcome.SUCCESS,
        "request_id": None,
    }
    values.update(overrides)
    return AuditEvent(**values)


@pytest.fixture
def repo() -> InMemoryAuditEventRepository:
    return InMemoryAuditEventRepository()


@pytest.fixture
def ingest(repo: InMemoryAuditEventRepository, received_at: datetime) -> IngestAuditEvent:
    return IngestAuditEvent(repo, clock=lambda: received_at)


async def test_stores_server_received_at_and_producer_occurred_at(
    ingest: IngestAuditEvent, repo: InMemoryAuditEventRepository, received_at: datetime
) -> None:
    occurred = datetime(2026, 11, 12, 9, 0, 0, 123456, tzinfo=timezone(timedelta(hours=-3)))

    assert await ingest.execute(_event(occurred_at=occurred)) is True

    [row] = repo.rows
    assert row.received_at == received_at
    assert row.occurred_at == datetime(2026, 11, 12, 12, 0, 0, 123456, tzinfo=UTC)
    assert row.occurred_at != row.received_at


async def test_same_event_id_is_stored_once_and_first_write_wins(
    ingest: IngestAuditEvent, repo: InMemoryAuditEventRepository
) -> None:
    event_id = uuid4()

    assert await ingest.execute(_event(event_id=event_id)) is True
    assert await ingest.execute(_event(event_id=event_id, action="auth.user.changed")) is False

    assert [row.action for row in repo.rows] == ["auth.user.registered"]


async def test_metadata_is_redacted_recursively(
    ingest: IngestAuditEvent, repo: InMemoryAuditEventRepository
) -> None:
    metadata = {
        "password": "s3cr3t",
        "nested": {"apiKey": "k", "email_masked": "a***@example.com"},
        "attempts": [{"verification_code": "123456", "status_code": 401}],
    }

    await ingest.execute(_event(metadata=metadata))

    assert repo.rows[0].metadata == {
        "password": REDACTED,
        "nested": {"apiKey": REDACTED, "email_masked": "a***@example.com"},
        "attempts": [{"verification_code": REDACTED, "status_code": 401}],
    }


async def test_redaction_is_logged_without_the_secret(ingest: IngestAuditEvent) -> None:
    event = _event(metadata={"token": "s3cr3t-value"})

    with capture_logs() as logs:
        await ingest.execute(event)

    [warning] = [line for line in logs if line["event"] == "audit_metadata_redacted"]
    assert warning == {
        "event": "audit_metadata_redacted",
        "log_level": "warning",
        "event_id": str(event.event_id),
        "action": "auth.user.registered",
        "producer": "auth",
    }
    assert "s3cr3t-value" not in repr(logs)


async def test_clean_metadata_does_not_warn(ingest: IngestAuditEvent) -> None:
    with capture_logs() as logs:
        await ingest.execute(_event(metadata={"email_masked": "a***@example.com"}))

    assert all(line["event"] != "audit_metadata_redacted" for line in logs)


async def test_original_event_is_not_mutated(ingest: IngestAuditEvent) -> None:
    event = _event(metadata={"password": "p", "nested": {"secret": "s"}})

    await ingest.execute(event)

    assert event.metadata == {"password": "p", "nested": {"secret": "s"}}


async def test_ipv6_is_stored_normalized(
    ingest: IngestAuditEvent, repo: InMemoryAuditEventRepository
) -> None:
    await ingest.execute(_event(actor_ip="2001:0db8:0000:0000:0000:0000:0000:0001"))

    assert repo.rows[0].actor_ip == "2001:db8::1"


async def test_ingested_and_duplicate_are_logged(ingest: IngestAuditEvent) -> None:
    event = _event()
    expected = {"event_id": str(event.event_id), "action": event.action, "producer": "auth"}

    with capture_logs() as logs:
        await ingest.execute(event)
        await ingest.execute(event)

    assert [(line["event"], line["log_level"]) for line in logs] == [
        ("audit_event_ingested", "info"),
        ("audit_event_duplicate", "info"),
    ]
    for line in logs:
        assert expected.items() <= line.items()
