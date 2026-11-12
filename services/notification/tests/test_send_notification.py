import asyncio
import json
from datetime import datetime
from typing import Any

import pytest
from structlog.testing import capture_logs

from notification_service.adapters.jinja_renderer import JinjaEmailRenderer
from notification_service.adapters.memory_repo import InMemoryNotificationRepository
from notification_service.adapters.memory_sender import FailingEmailSender, InMemoryEmailSender
from notification_service.catalog import build_registry
from notification_service.domain import (
    EmailDeliveryError,
    InvalidTemplateDataError,
    NotificationStatus,
    StoredNotification,
    UnknownTemplateError,
)
from notification_service.ports import EmailSender, MessageIdFactory
from notification_service.use_cases.send_notification import RetryPolicy, SendNotification
from veriditi_common.audit import AuditOutcome, InMemoryAuditLogger

TO = "joao@exemplo.com"
KEY = "email_verification:42"
ALWAYS = 99


class Harness:
    """Caso de uso com fakes; o scheduler segura o envio até run_all()"""

    def __init__(
        self,
        *,
        sender: EmailSender,
        scheduler: Any,
        sleep: Any,
        message_ids: MessageIdFactory,
        now: datetime,
        notifications: InMemoryNotificationRepository | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        self.notifications = notifications or InMemoryNotificationRepository()
        self.audit = InMemoryAuditLogger()
        self.scheduler = scheduler
        self.use_case = SendNotification(
            registry=build_registry(),
            renderer=JinjaEmailRenderer(web_url="http://localhost:3000"),
            notifications=self.notifications,
            sender=sender,
            audit=self.audit,
            scheduler=scheduler,
            message_ids=message_ids,
            clock=lambda: now,
            sleep=sleep,
            **({"retry": retry} if retry else {}),
        )

    def row(self) -> StoredNotification:
        [row] = self.notifications.rows
        return row


@pytest.fixture
def harness_for(scheduler: Any, sleep: Any, message_ids: MessageIdFactory, now: datetime) -> Any:
    def build(sender: EmailSender, **kwargs: Any) -> Harness:
        kwargs.setdefault("sleep", sleep)
        return Harness(
            sender=sender, scheduler=scheduler, message_ids=message_ids, now=now, **kwargs
        )

    return build


@pytest.fixture
def harness(harness_for: Any, sender: InMemoryEmailSender) -> Harness:
    return harness_for(sender)


async def test_new_key_is_reserved_and_sending_waits_for_the_scheduler(
    harness: Harness, sender: InMemoryEmailSender, make_request: Any
) -> None:
    assert await harness.use_case.execute(make_request()) is True

    row = harness.row()
    assert (row.status, row.attempts, row.idempotency_key) == (NotificationStatus.PENDING, 0, KEY)
    assert len(harness.scheduler.tasks) == 1
    assert sender.sent == []
    assert harness.audit.events == []


async def test_delivery_sends_marks_sent_and_audits_without_content(
    harness: Harness, sender: InMemoryEmailSender, make_request: Any, now: datetime
) -> None:
    await harness.use_case.execute(make_request())
    await harness.scheduler.run_all()

    [email] = sender.sent
    assert email.to == TO
    assert email.subject == "Seu código de verificação Veriditi"
    assert "042137" in email.text
    assert "042137" in email.html
    assert email.message_id == "<fixed-1@veriditi.app>"

    row = harness.row()
    assert row.status is NotificationStatus.SENT
    assert (row.attempts, row.message_id, row.sent_at) == (1, email.message_id, now)

    [event] = harness.audit.events
    assert event.action == "notification.email.sent"
    assert event.outcome is AuditOutcome.SUCCESS
    assert (event.service, event.resource_type, event.resource_id) == (
        "notification",
        "notification",
        str(row.id),
    )
    assert (event.actor_id, event.actor_ip) == (None, None)
    assert event.metadata == {
        "template": "email_verification",
        "to_masked": "j***@exemplo.com",
        "message_id": "<fixed-1@veriditi.app>",
        "attempts": 1,
        "idempotency_key": KEY,
    }
    dumped = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    for secret in ("042137", TO, "João"):
        assert secret not in dumped


@pytest.mark.parametrize("status", list(NotificationStatus))
async def test_known_key_is_not_sent_again(
    harness: Harness,
    sender: InMemoryEmailSender,
    make_request: Any,
    status: NotificationStatus,
    now: datetime,
) -> None:
    notification_id = await harness.notifications.add(KEY, "email_verification", created_at=now)
    assert notification_id is not None
    if status is NotificationStatus.SENT:
        await harness.notifications.mark_sent(
            notification_id, attempts=1, message_id="<x@y>", sent_at=now
        )
    elif status is NotificationStatus.FAILED:
        await harness.notifications.mark_failed(notification_id, attempts=3)

    with capture_logs() as logs:
        assert await harness.use_case.execute(make_request()) is False

    await harness.scheduler.run_all()
    assert harness.scheduler.tasks == []
    assert sender.sent == []
    assert harness.audit.events == []
    [line] = [line for line in logs if line["event"] == "notification_duplicate"]
    assert line["status"] == status.value
    assert line["to_masked"] == "j***@exemplo.com"


async def test_unknown_template_raises_before_reserving(
    harness: Harness, make_request: Any
) -> None:
    with pytest.raises(UnknownTemplateError):
        await harness.use_case.execute(make_request(template="password_reset"))

    assert harness.notifications.rows == []


async def test_invalid_data_raises_before_reserving(harness: Harness, make_request: Any) -> None:
    with pytest.raises(InvalidTemplateDataError):
        await harness.use_case.execute(make_request(data={"name": "Ana"}))

    assert harness.notifications.rows == []


async def test_transient_failures_are_retried_with_the_same_email(
    harness_for: Any, sleep: Any, make_request: Any
) -> None:
    sender = FailingEmailSender(fail_times=2)
    harness = harness_for(sender)

    with capture_logs() as logs:
        await harness.use_case.execute(make_request())
        await harness.scheduler.run_all()

    assert len(sender.calls) == 3
    assert sender.calls[0] is sender.calls[1] is sender.calls[2]
    assert sleep.delays == [1.0, 2.0]
    row = harness.row()
    assert (row.status, row.attempts) == (NotificationStatus.SENT, 3)
    failed = [line for line in logs if line["event"] == "notification_email_attempt_failed"]
    assert [line["attempt"] for line in failed] == [1, 2]
    assert all(line["max_attempts"] == 3 for line in failed)
    assert harness.audit.events[0].metadata["attempts"] == 3


async def test_exhausted_retries_mark_failed_and_audit(
    harness_for: Any, sleep: Any, make_request: Any
) -> None:
    sender = FailingEmailSender(fail_times=ALWAYS)
    harness = harness_for(sender)

    await harness.use_case.execute(make_request())
    await harness.scheduler.run_all()

    assert len(sender.calls) == 3
    assert sleep.delays == [1.0, 2.0]
    row = harness.row()
    assert (row.status, row.attempts, row.message_id, row.sent_at) == (
        NotificationStatus.FAILED,
        3,
        None,
        None,
    )
    [event] = harness.audit.events
    assert event.action == "notification.email.failed"
    assert event.outcome is AuditOutcome.FAILURE
    assert event.resource_id == str(row.id)
    assert event.metadata == {
        "template": "email_verification",
        "to_masked": "j***@exemplo.com",
        "attempts": 3,
        "idempotency_key": KEY,
        "error_type": "SMTPServerDisconnected",
        "smtp_code": None,
        "permanent": False,
    }


async def test_permanent_error_stops_at_once(
    harness_for: Any, sleep: Any, make_request: Any
) -> None:
    error = EmailDeliveryError("SMTPRecipientsRefused", permanent=True, smtp_code=550)
    sender = FailingEmailSender(fail_times=ALWAYS, error=error)
    harness = harness_for(sender)

    await harness.use_case.execute(make_request())
    await harness.scheduler.run_all()

    assert len(sender.calls) == 1
    assert sleep.delays == []
    assert (harness.row().status, harness.row().attempts) == (NotificationStatus.FAILED, 1)
    [event] = harness.audit.events
    assert (event.metadata["permanent"], event.metadata["smtp_code"]) == (True, 550)


async def test_unexpected_sender_error_is_transient_and_hides_its_message(
    harness_for: Any, make_request: Any
) -> None:
    sender = FailingEmailSender(fail_times=ALWAYS, error=RuntimeError(f"bug com {TO}"))
    harness = harness_for(sender)

    with capture_logs() as logs:
        await harness.use_case.execute(make_request())
        await harness.scheduler.run_all()

    assert len(sender.calls) == 3
    assert harness.row().status is NotificationStatus.FAILED
    assert harness.audit.events[0].metadata["error_type"] == "RuntimeError"
    assert TO not in repr(logs)
    assert all("exc_info" not in line for line in logs)


class _BrokenMarkSent(InMemoryNotificationRepository):
    async def mark_sent(self, notification_id: int, **kwargs: Any) -> bool:
        raise ConnectionError("banco fora")


class _AlreadyFinished(InMemoryNotificationRepository):
    async def mark_sent(self, notification_id: int, **kwargs: Any) -> bool:
        return False


async def test_status_update_failure_still_audits(
    harness_for: Any, sender: InMemoryEmailSender, make_request: Any
) -> None:
    harness = harness_for(sender, notifications=_BrokenMarkSent())

    with capture_logs() as logs:
        await harness.use_case.execute(make_request())
        await harness.scheduler.run_all()

    assert harness.audit.actions() == ["notification.email.sent"]
    [line] = [line for line in logs if line["event"] == "notification_status_update_failed"]
    assert line["error_type"] == "ConnectionError"
    assert line["notification_id"] == 1


async def test_status_conflict_is_logged_and_audited(
    harness_for: Any, sender: InMemoryEmailSender, make_request: Any
) -> None:
    harness = harness_for(sender, notifications=_AlreadyFinished())

    with capture_logs() as logs:
        await harness.use_case.execute(make_request())
        await harness.scheduler.run_all()

    assert harness.audit.actions() == ["notification.email.sent"]
    assert "notification_status_conflict" in [line["event"] for line in logs]


async def test_cancellation_during_backoff_leaves_row_pending(
    harness_for: Any, make_request: Any
) -> None:
    entered = asyncio.Event()

    async def blocking_sleep(seconds: float) -> None:
        entered.set()
        await asyncio.Event().wait()

    harness = harness_for(FailingEmailSender(fail_times=ALWAYS), sleep=blocking_sleep)

    with capture_logs() as logs:
        await harness.use_case.execute(make_request())
        task = asyncio.create_task(harness.scheduler.tasks.pop()())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert harness.row().status is NotificationStatus.PENDING
    assert harness.audit.events == []
    [line] = [line for line in logs if line["event"] == "notification_delivery_interrupted"]
    assert line["attempts"] == 1


class _BlockingMarkSent(InMemoryNotificationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()

    async def mark_sent(self, notification_id: int, **kwargs: Any) -> bool:
        self.entered.set()
        await asyncio.Event().wait()
        return True


async def test_cancellation_while_finishing_does_not_claim_delivery_was_interrupted(
    harness_for: Any, sender: InMemoryEmailSender, make_request: Any
) -> None:
    repo = _BlockingMarkSent()
    harness = harness_for(sender, notifications=repo)

    with capture_logs() as logs:
        await harness.use_case.execute(make_request())
        task = asyncio.create_task(harness.scheduler.tasks.pop()())
        await repo.entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(sender.sent) == 1
    events = [line["event"] for line in logs]
    assert "notification_delivery_interrupted" not in events
    [line] = [line for line in logs if line["event"] == "notification_finish_interrupted"]
    assert (line["delivered"], line["attempts"]) == (True, 1)


async def test_retry_policy_is_a_single_constant(
    harness_for: Any, sleep: Any, make_request: Any
) -> None:
    sender = FailingEmailSender(fail_times=ALWAYS)
    harness = harness_for(sender, retry=RetryPolicy((1.0, 2.0, 4.0)))

    await harness.use_case.execute(make_request())
    await harness.scheduler.run_all()

    assert len(sender.calls) == 4
    assert sleep.delays == [1.0, 2.0, 4.0]
    assert harness.row().attempts == 4


def test_default_policy_is_three_attempts() -> None:
    assert RetryPolicy().max_attempts == 3
    assert RetryPolicy().delays == (1.0, 2.0)


async def test_logs_never_carry_address_code_or_name(
    harness_for: Any, sender: InMemoryEmailSender, make_request: Any, json_logs: Any
) -> None:
    ok = harness_for(sender)
    await ok.use_case.execute(make_request())
    await ok.use_case.execute(make_request())
    await ok.scheduler.run_all()
    failing = harness_for(FailingEmailSender(fail_times=ALWAYS))
    await failing.use_case.execute(make_request(idempotency_key="email_verification:43"))
    await failing.scheduler.run_all()

    lines = json_logs()
    events = [line["event"] for line in lines]
    assert {
        "notification_accepted",
        "notification_duplicate",
        "notification_email_sent",
        "notification_email_attempt_failed",
        "notification_email_failed",
    } <= set(events)
    raw = json.dumps(lines, ensure_ascii=False)
    for secret in (TO, "042137", "João"):
        assert secret not in raw
    ours = [line for line in lines if line["logger"].startswith("notification_service")]
    assert all(line["to_masked"] == "j***@exemplo.com" for line in ours)
    assert {line["idempotency_key"] for line in ours} == {KEY, "email_verification:43"}
