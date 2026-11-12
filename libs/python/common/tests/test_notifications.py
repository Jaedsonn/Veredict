import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from structlog.contextvars import bound_contextvars
from structlog.testing import capture_logs

from veriditi_common.errors import install_error_handlers
from veriditi_common.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from veriditi_common.notifications import (
    HttpNotifier,
    InMemoryNotifier,
    NotificationRequest,
    NotificationTemplate,
    NotifierDep,
    get_notifier,
)

JsonLogs = Callable[[], list[dict[str, Any]]]
TOKEN = "test-internal-token-0123456789"
BASE_URL = "http://notification.test"
NOTIFICATIONS_URL = f"{BASE_URL}/internal/notifications"
RID = "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"
EMAIL = "joao@exemplo.com"
CODE = "123456"


def _request(**overrides: Any) -> NotificationRequest:
    values: dict[str, Any] = {
        "idempotency_key": "email_verification:42",
        "template": NotificationTemplate.EMAIL_VERIFICATION,
        "to": EMAIL,
        "data": {"code": CODE, "name": "João"},
    }
    values.update(overrides)
    return NotificationRequest(**values)


def test_valid_request() -> None:
    request = _request()

    assert request.template == "email_verification"
    assert request.to == EMAIL
    assert request.model_dump(mode="json") == {
        "idempotency_key": "email_verification:42",
        "template": "email_verification",
        "to": EMAIL,
        "data": {"code": CODE, "name": "João"},
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"idempotency_key": "k" * 129},
        {"idempotency_key": "chave-não-ascii"},
        {"idempotency_key": "com espaço"},
        {"idempotency_key": ""},
        {"template": "Welcome"},
        {"template": ""},
        {"template": "t" * 65},
        {"to": "nao-e-email"},
        {"to": "a" * 64 + "@" + ("d" * 60 + ".") * 4 + "com"},
        {"data": {"x": object()}},
        {"extra": 1},
    ],
)
def test_invalid_requests(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _request(**overrides)


def test_repr_hides_recipient_and_data() -> None:
    rendered = repr(_request())

    assert EMAIL not in rendered
    assert CODE not in rendered


def test_template_catalog() -> None:
    assert {t.value for t in NotificationTemplate} == {"email_verification", "welcome"}


async def test_http_notifier_posts_request() -> None:
    request = _request()
    async with httpx.AsyncClient() as client, respx.mock() as mock:
        route = mock.post(NOTIFICATIONS_URL).respond(202)
        with bound_contextvars(request_id=RID):
            await HttpNotifier(client, BASE_URL + "/", SecretStr(TOKEN)).send(request)

    sent = route.calls.last.request
    assert json.loads(sent.content) == request.model_dump(mode="json")
    assert sent.headers["X-Internal-Token"] == TOKEN
    assert sent.headers[REQUEST_ID_HEADER] == RID
    assert sent.extensions["timeout"]["read"] == 2.0


FAILURES: list[tuple[str, Any]] = [
    ("ConnectError", httpx.ConnectError("recusado")),
    ("ReadTimeout", httpx.ReadTimeout("lento")),
    ("HTTPStatusError", httpx.Response(500)),
    ("HTTPStatusError", httpx.Response(422)),
]


@pytest.mark.parametrize(("error_type", "outcome"), FAILURES)
async def test_http_notifier_never_raises_and_hides_content(
    error_type: str, outcome: Any, json_logs: JsonLogs
) -> None:
    async with httpx.AsyncClient() as client, respx.mock() as mock:
        route = mock.post(NOTIFICATIONS_URL)
        if isinstance(outcome, httpx.Response):
            route.mock(return_value=outcome)
        else:
            route.mock(side_effect=outcome)
        with capture_logs() as logs:
            await HttpNotifier(client, BASE_URL, SecretStr(TOKEN)).send(_request())
        await HttpNotifier(client, BASE_URL, SecretStr(TOKEN)).send(_request())

    [entry] = logs
    assert entry["event"] == "notification_delivery_failed"
    assert entry["log_level"] == "error"
    assert entry["notification_fallback"] is True
    assert entry["template"] == "email_verification"
    assert entry["idempotency_key"] == "email_verification:42"
    assert entry["to_masked"] == "j***@exemplo.com"
    assert entry["error_type"] == error_type
    assert "data" not in entry
    assert "to" not in entry
    if isinstance(outcome, httpx.Response):
        assert entry["status_code"] == outcome.status_code

    output = json.dumps(json_logs())
    assert "notification_delivery_failed" in output
    for secret in (CODE, EMAIL, TOKEN):
        assert secret not in output


async def test_http_notifier_with_closed_client_does_not_raise() -> None:
    client = httpx.AsyncClient()
    await client.aclose()

    with capture_logs() as logs:
        await HttpNotifier(client, BASE_URL, SecretStr(TOKEN)).send(_request())

    assert logs[0]["error_type"] == "RuntimeError"


async def test_in_memory_notifier_records() -> None:
    notifier = InMemoryNotifier()

    await notifier.send(_request())

    assert [r.template for r in notifier.sent] == ["email_verification"]


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/x", status_code=202)
    async def trigger(notifier: NotifierDep) -> dict[str, str]:
        await notifier.send(_request())
        return {"ok": "1"}

    app.add_middleware(RequestContextMiddleware)
    return app


async def test_background_notifier_sends_after_response() -> None:
    app = _app()
    app.state.notifier = InMemoryNotifier()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/x")

    assert resp.status_code == 202
    assert len(app.state.notifier.sent) == 1


async def test_request_succeeds_when_notification_is_down(json_logs: JsonLogs) -> None:
    app = _app()
    async with httpx.AsyncClient() as http, respx.mock() as mock:
        mock.post(NOTIFICATIONS_URL).mock(side_effect=httpx.ConnectError("recusado"))
        app.state.notifier = HttpNotifier(http, BASE_URL, SecretStr(TOKEN))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            resp = await client.post("/x")

    assert resp.status_code == 202
    [line] = [e for e in json_logs() if e["event"] == "notification_delivery_failed"]
    assert line["request_id"] == resp.headers[REQUEST_ID_HEADER]


def test_get_notifier_requires_app_state() -> None:
    request = Request({"type": "http", "app": FastAPI()})

    with pytest.raises(RuntimeError, match="notifier"):
        get_notifier(request, background_tasks=None)  # type: ignore[arg-type]
