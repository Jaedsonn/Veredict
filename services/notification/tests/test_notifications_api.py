import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from structlog.testing import capture_logs

from notification_service.adapters.memory_repo import InMemoryNotificationRepository
from notification_service.adapters.memory_sender import FailingEmailSender, InMemoryEmailSender
from notification_service.adapters.smtp_sender import build_message
from notification_service.domain import NotificationStatus, StoredNotification
from notification_service.models import NotificationRecord
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import HttpNotifier, NotificationRequest
from veriditi_common.security import INTERNAL_TOKEN_HEADER

URL = "/internal/notifications"
TO = "joao@exemplo.com"
KEY = "email_verification:42"
FIXED = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "idempotency_key": KEY,
        "template": "email_verification",
        "to": TO,
        "data": {"name": "João", "code": "042137", "expires_in_minutes": 15},
    }
    body.update(overrides)
    return body


async def _rows(db: Database) -> list[NotificationRecord]:
    async with db.session_factory() as session:
        return list(
            await session.scalars(select(NotificationRecord).order_by(NotificationRecord.id))
        )


async def _count(db: Database) -> int:
    async with db.session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(NotificationRecord)) or 0)


async def test_happy_path_accepts_then_sends(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: Database,
    sender: InMemoryEmailSender,
    audit: InMemoryAuditLogger,
) -> None:
    request_id = str(uuid.uuid4())

    resp = await client.post(
        URL, json=_body(), headers={**auth_headers, "X-Request-ID": request_id}
    )

    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    [email] = sender.sent
    assert (email.to, email.message_id) == (TO, "<fixed-1@veriditi.app>")
    [row] = await _rows(db)
    assert (row.status, row.attempts, row.message_id) == (
        NotificationStatus.SENT,
        1,
        "<fixed-1@veriditi.app>",
    )
    [event] = audit.events
    assert event.action == "notification.email.sent"
    assert event.resource_id == str(row.id)
    assert str(event.request_id) == request_id


async def test_auth_payload_with_tab_in_name_is_accepted_and_sent(
    client: AsyncClient, auth_headers: dict[str, str], sender: InMemoryEmailSender
) -> None:
    # Exatamente o que o auth envia: ele só apara o nome e limita a 120 caracteres
    data = {"name": "Ana\tSilva\r\nSouza", "code": "042137", "expires_in_minutes": 15}

    resp = await client.post(URL, json=_body(data=data), headers=auth_headers)

    assert resp.status_code == 202
    [email] = sender.sent
    assert "Olá, Ana Silva Souza!" in email.text
    raw = bytes(build_message(email, sender="Veriditi <no-reply@veriditi.app>", date=FIXED))
    headers, _, body = raw.partition(b"\n\n")
    assert b"Ana" not in headers
    assert b"\r" not in raw
    assert b"\t" not in body


@pytest.mark.parametrize("name", ["", " \t\r\n "], ids=["empty", "only-whitespace"])
async def test_blank_name_is_accepted_and_greets_without_it(
    client: AsyncClient, auth_headers: dict[str, str], sender: InMemoryEmailSender, name: str
) -> None:
    data = {"name": name, "code": "042137", "expires_in_minutes": 15}

    resp = await client.post(URL, json=_body(data=data), headers=auth_headers)

    assert resp.status_code == 202
    [email] = sender.sent
    assert email.text.startswith("Olá!\n")
    assert ">Olá!</p>" in email.html


async def test_missing_name_is_still_422(
    client: AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    data = {"code": "042137", "expires_in_minutes": 15}

    resp = await client.post(URL, json=_body(data=data), headers=auth_headers)

    assert resp.status_code == 422
    assert [error["loc"] for error in resp.json()["detail"]] == [["body", "data", "name"]]
    assert await _count(db) == 0


async def test_email_goes_out_after_the_response(
    client: AsyncClient, auth_headers: dict[str, str], json_logs: Any
) -> None:
    await client.post(URL, json=_body(), headers=auth_headers)

    events = [line["event"] for line in json_logs()]
    assert events.index("request_finished") < events.index("notification_email_sent")


async def test_repeated_key_is_accepted_but_sent_once(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: Database,
    sender: InMemoryEmailSender,
    audit: InMemoryAuditLogger,
) -> None:
    responses = [await client.post(URL, json=_body(), headers=auth_headers) for _ in range(3)]

    assert [(r.status_code, r.json()) for r in responses] == [(202, {"status": "accepted"})] * 3
    assert len(sender.sent) == 1
    assert await _count(db) == 1
    assert audit.actions() == ["notification.email.sent"]


@pytest.mark.parametrize("token", [None, "token-errado-0123456789"], ids=["missing", "wrong"])
@pytest.mark.parametrize("body", [_body(), {"template": 1}], ids=["valid", "invalid"])
async def test_token_is_checked_before_the_body(
    client: AsyncClient, db: Database, token: str | None, body: dict[str, Any]
) -> None:
    headers = {INTERNAL_TOKEN_HEADER: token} if token else {}

    resp = await client.post(URL, json=body, headers=headers)

    assert resp.status_code == 401
    assert resp.json() == {"detail": {"code": "unauthorized", "message": "Não autenticado."}}
    assert await _count(db) == 0


async def test_unknown_template_lists_valid_names(
    client: AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    resp = await client.post(URL, json=_body(template="password_reset"), headers=auth_headers)

    assert resp.status_code == 422
    assert resp.json() == {
        "detail": [
            {
                "type": "unknown_template",
                "loc": ["body", "template"],
                "msg": "Template desconhecido. Válidos: email_verification, welcome",
            }
        ]
    }
    assert await _count(db) == 0


async def test_missing_data_fields_point_into_body_data(
    client: AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    resp = await client.post(URL, json=_body(data={"name": "Ana"}), headers=auth_headers)

    assert resp.status_code == 422
    assert resp.json() == {
        "detail": [
            {"type": "missing", "loc": ["body", "data", "code"], "msg": "Field required"},
            {
                "type": "missing",
                "loc": ["body", "data", "expires_in_minutes"],
                "msg": "Field required",
            },
        ]
    }
    assert await _count(db) == 0


async def test_invalid_code_is_not_echoed(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    data = {"name": "João", "code": "12a456", "expires_in_minutes": 15}

    resp = await client.post(URL, json=_body(data=data), headers=auth_headers)

    assert resp.status_code == 422
    [error] = resp.json()["detail"]
    assert (error["type"], error["loc"]) == ("string_pattern_mismatch", ["body", "data", "code"])
    assert "12a456" not in resp.text


async def test_invalid_address_is_not_echoed(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.post(URL, json=_body(to="nao-e-email"), headers=auth_headers)

    assert resp.status_code == 422
    assert [error["loc"] for error in resp.json()["detail"]] == [["body", "to"]]
    assert "nao-e-email" not in resp.text


@pytest.mark.parametrize(
    "overrides",
    [{"idempotency_key": "chave com espaço"}, {"extra": 1}, {"template": "../welcome"}],
    ids=["key-with-space", "extra-field", "path-traversal"],
)
async def test_envelope_validation(
    client: AsyncClient, auth_headers: dict[str, str], db: Database, overrides: dict[str, Any]
) -> None:
    resp = await client.post(URL, json=_body(**overrides), headers=auth_headers)

    assert resp.status_code == 422
    assert await _count(db) == 0


async def test_body_over_16_kib_is_413(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    body = _body(data={"name": "x" * (17 * 1024)})

    resp = await client.post(URL, json=body, headers=auth_headers)

    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "payload_too_large"


@pytest.mark.parametrize("method", ["GET", "DELETE"])
async def test_only_post_is_routed(
    client: AsyncClient, auth_headers: dict[str, str], method: str
) -> None:
    resp = await client.request(method, URL, headers=auth_headers)

    assert resp.status_code == 405


async def test_smtp_down_still_accepts_and_ends_failed(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: Database,
    audit: InMemoryAuditLogger,
    sleep: Any,
) -> None:
    app.state.email_sender = FailingEmailSender(fail_times=99)

    resp = await client.post(URL, json=_body(), headers=auth_headers)

    assert resp.status_code == 202
    [row] = await _rows(db)
    assert (row.status, row.attempts, row.message_id) == (NotificationStatus.FAILED, 3, None)
    assert audit.actions() == ["notification.email.failed"]
    assert sleep.delays == [1.0, 2.0]


class _BrokenRepository(InMemoryNotificationRepository):
    async def add(self, idempotency_key: str, template: str, **kwargs: Any) -> int | None:
        raise ConnectionError("banco fora")

    async def get(self, idempotency_key: str) -> StoredNotification | None:
        raise AssertionError("não deveria consultar")


async def test_database_down_is_500_without_email(
    app: FastAPI, client: AsyncClient, auth_headers: dict[str, str], sender: InMemoryEmailSender
) -> None:
    app.state.notifications = _BrokenRepository()

    resp = await client.post(URL, json=_body(), headers=auth_headers)

    assert resp.status_code == 500
    assert resp.json()["detail"]["code"] == "internal_error"
    assert sender.sent == []


async def test_real_producer_contract(
    app: FastAPI, token: str, sender: InMemoryEmailSender
) -> None:
    request = NotificationRequest(
        idempotency_key="welcome:7", template="welcome", to=TO, data={"name": "Ana"}
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        with capture_logs() as logs:
            await HttpNotifier(http, "http://test", SecretStr(token)).send(request)

    [email] = sender.sent
    assert (email.to, email.subject) == (TO, "Bem-vindo(a) ao Veriditi")
    assert "notification_delivery_failed" not in [line["event"] for line in logs]


async def test_producer_with_wrong_token_logs_401_without_raising(
    app: FastAPI, sender: InMemoryEmailSender
) -> None:
    request = NotificationRequest(
        idempotency_key="welcome:7", template="welcome", to=TO, data={"name": "Ana"}
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        with capture_logs() as logs:
            await HttpNotifier(http, "http://test", SecretStr("token-errado-0123456789")).send(
                request
            )

    [line] = [line for line in logs if line["event"] == "notification_delivery_failed"]
    assert line["status_code"] == 401
    assert sender.sent == []
