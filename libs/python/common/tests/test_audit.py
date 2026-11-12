import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from structlog.contextvars import bound_contextvars
from structlog.testing import capture_logs

from veriditi_common.audit import (
    AuditEvent,
    AuditLoggerDep,
    AuditOutcome,
    HttpAuditLogger,
    InMemoryAuditLogger,
    get_audit_logger,
)
from veriditi_common.errors import AppError, install_error_handlers
from veriditi_common.middleware import REQUEST_ID_HEADER, RequestContextMiddleware

JsonLogs = Callable[[], list[dict[str, Any]]]
TOKEN = "test-internal-token-0123456789"
BASE_URL = "http://monitoring.test"
EVENTS_URL = f"{BASE_URL}/internal/events"
RID = "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"


def _event(**overrides: Any) -> AuditEvent:
    values: dict[str, Any] = {
        "service": "auth",
        "action": "auth.user.registered",
        "outcome": "success",
    }
    values.update(overrides)
    return AuditEvent(**values)


def test_defaults_are_uuid4_and_utc_now() -> None:
    event = _event()

    assert event.event_id.version == 4
    assert event.occurred_at.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - event.occurred_at) < timedelta(seconds=1)
    assert event.metadata == {}


def test_occurred_at_must_be_aware_and_becomes_utc() -> None:
    with pytest.raises(ValidationError):
        _event(occurred_at=datetime(2026, 1, 1, 9, 0))

    bahia = datetime(2026, 1, 1, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert _event(occurred_at=bahia).occurred_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert _event(occurred_at=bahia).occurred_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("action", ["auth.user.registered", "auth.session.login_failed"])
def test_valid_actions(action: str) -> None:
    assert _event(action=action).action == action


@pytest.mark.parametrize(
    ("service", "action"),
    [
        ("auth", "auth.user"),
        ("auth", "Auth.user.registered"),
        ("auth", "auth..x"),
        ("auth", "auth.user." + "x" * 71),
        ("auth", "notification.email.sent"),
    ],
)
def test_invalid_actions(service: str, action: str) -> None:
    with pytest.raises(ValidationError):
        _event(service=service, action=action)


@pytest.mark.parametrize(
    "overrides",
    [
        {"service": "a" * 41, "action": "a" * 41 + ".x.y"},
        {"service": "api-gw", "action": "api_gw.x.y"},
        {"service": "Auth", "action": "auth.x.y"},
        {"resource_type": "r" * 41},
        {"resource_id": "r" * 65},
        {"actor_id": 0},
        {"actor_id": 2**63},
        {"outcome": "ok"},
        {"extra": 1},
        {"metadata": {"x": object()}},
        {"actor_ip": "999.1.1.1"},
        {"actor_ip": "fe80::1%" + "a" * 80},
    ],
)
def test_constraints_from_ddl(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _event(**overrides)


@pytest.mark.parametrize("ip", ["203.0.113.5", "2001:db8::1"])
def test_actor_ip_accepts_ipv4_and_ipv6(ip: str) -> None:
    assert _event(actor_ip=ip).model_dump(mode="json")["actor_ip"] == ip


def test_json_dump_and_round_trip() -> None:
    event = _event(
        actor_id=42,
        actor_ip="203.0.113.5",
        request_id=RID,
        resource_type="user",
        resource_id="42",
        outcome=AuditOutcome.FAILURE,
        metadata={"reason": "x", "n": [1, 2]},
    )

    dump = event.model_dump(mode="json")

    assert set(dump) == {
        "event_id",
        "occurred_at",
        "service",
        "action",
        "outcome",
        "actor_id",
        "actor_ip",
        "request_id",
        "resource_type",
        "resource_id",
        "metadata",
    }
    assert dump["actor_ip"] == "203.0.113.5"
    assert dump["outcome"] == "failure"
    assert dump["request_id"] == RID
    assert datetime.fromisoformat(dump["occurred_at"]) == event.occurred_at
    assert AuditEvent.model_validate(dump) == event


async def test_in_memory_logger_records() -> None:
    audit = InMemoryAuditLogger()

    await audit.record(_event())
    await audit.record(_event(action="auth.session.login_failed", outcome="failure"))

    assert audit.actions() == ["auth.user.registered", "auth.session.login_failed"]


@pytest.mark.parametrize("base_url", [BASE_URL, BASE_URL + "/"])
async def test_http_logger_posts_event(base_url: str) -> None:
    event = _event(request_id=RID)
    async with httpx.AsyncClient() as client, respx.mock() as mock:
        route = mock.post(EVENTS_URL).respond(202)
        await HttpAuditLogger(client, base_url, SecretStr(TOKEN)).record(event)

    request = route.calls.last.request
    assert json.loads(request.content) == event.model_dump(mode="json")
    assert request.headers["X-Internal-Token"] == TOKEN
    assert request.headers[REQUEST_ID_HEADER] == RID
    assert request.extensions["timeout"]["read"] == 2.0


async def test_http_logger_uses_request_id_from_context() -> None:
    async with httpx.AsyncClient() as client, respx.mock() as mock:
        route = mock.post(EVENTS_URL).respond(202)
        with bound_contextvars(request_id=RID):
            await HttpAuditLogger(client, BASE_URL, SecretStr(TOKEN)).record(_event())

    assert route.calls.last.request.headers[REQUEST_ID_HEADER] == RID


FAILURES: list[tuple[str, Any]] = [
    ("ConnectError", httpx.ConnectError("recusado")),
    ("ReadTimeout", httpx.ReadTimeout("lento")),
    ("HTTPStatusError", httpx.Response(500)),
    ("HTTPStatusError", httpx.Response(422)),
]


@pytest.mark.parametrize(("error_type", "outcome"), FAILURES)
async def test_http_logger_never_raises_and_logs_fallback(error_type: str, outcome: Any) -> None:
    event = _event()
    async with httpx.AsyncClient() as client, respx.mock() as mock:
        route = mock.post(EVENTS_URL)
        if isinstance(outcome, httpx.Response):
            route.mock(return_value=outcome)
        else:
            route.mock(side_effect=outcome)
        with capture_logs() as logs:
            await HttpAuditLogger(client, BASE_URL, SecretStr(TOKEN)).record(event)

    [entry] = logs
    assert entry["event"] == "audit_delivery_failed"
    assert entry["log_level"] == "error"
    assert entry["audit_fallback"] is True
    assert entry["error_type"] == error_type
    assert entry["audit_event"]["event_id"] == str(event.event_id)
    if isinstance(outcome, httpx.Response):
        assert entry["status_code"] == outcome.status_code
    assert TOKEN not in json.dumps(logs, default=str)


async def test_http_logger_with_closed_client_does_not_raise() -> None:
    client = httpx.AsyncClient()
    await client.aclose()

    with capture_logs() as logs:
        await HttpAuditLogger(client, BASE_URL, SecretStr(TOKEN)).record(_event())

    assert logs[0]["error_type"] == "RuntimeError"


async def test_fallback_json_output_has_no_token(json_logs: JsonLogs) -> None:
    async with httpx.AsyncClient() as client, respx.mock() as mock:
        mock.post(EVENTS_URL).mock(side_effect=httpx.ConnectError("recusado"))
        await HttpAuditLogger(client, BASE_URL, SecretStr(TOKEN)).record(_event())

    [line] = [e for e in json_logs() if e["event"] == "audit_delivery_failed"]
    assert line["audit_fallback"] is True
    assert TOKEN not in json.dumps(json_logs())


async def test_request_succeeds_when_monitoring_is_down(json_logs: JsonLogs) -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/x", status_code=201)
    async def create(audit: AuditLoggerDep) -> dict[str, str]:
        await audit.record(_event())
        return {"ok": "1"}

    app.add_middleware(RequestContextMiddleware)

    async with httpx.AsyncClient() as http, respx.mock() as mock:
        mock.post(EVENTS_URL).mock(side_effect=httpx.ConnectError("recusado"))
        app.state.audit_logger = HttpAuditLogger(http, BASE_URL, SecretStr(TOKEN))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            resp = await client.post("/x")

    assert resp.status_code == 201
    [line] = [e for e in json_logs() if e["event"] == "audit_delivery_failed"]
    assert line["audit_fallback"] is True
    assert line["level"] == "error"
    assert line["request_id"] == resp.headers[REQUEST_ID_HEADER]


def test_get_audit_logger_requires_app_state() -> None:
    request = Request({"type": "http", "app": FastAPI()})

    with pytest.raises(RuntimeError, match="audit_logger"):
        get_audit_logger(request)


def test_event_id_is_uuid() -> None:
    assert isinstance(_event().event_id, uuid.UUID)


def _audited_app(audit: InMemoryAuditLogger) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    app.state.audit_logger = audit

    @app.post("/ok")
    async def ok(audit: AuditLoggerDep) -> dict[str, str]:
        await audit.record(_event())
        return {"ok": "1"}

    @app.post("/login")
    async def login(audit: AuditLoggerDep) -> None:
        await audit.record(_event(action="auth.session.login_failed", outcome="failure"))
        raise AppError(401, "invalid_credentials", "E-mail ou senha incorretos.")

    @app.post("/boom")
    async def boom(audit: AuditLoggerDep) -> None:
        await audit.record(_event(action="auth.session.login_failed", outcome="failure"))
        raise RuntimeError("explodiu")

    app.add_middleware(RequestContextMiddleware)
    return app


@pytest.mark.parametrize(("path", "status"), [("/ok", 200), ("/login", 401), ("/boom", 500)])
async def test_event_is_delivered_exactly_once_even_on_error(path: str, status: int) -> None:
    audit = InMemoryAuditLogger()
    app = _audited_app(audit)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(path)

    assert resp.status_code == status
    assert len(audit.events) == 1


def test_validation_error_does_not_repeat_metadata() -> None:
    with pytest.raises(ValidationError) as caught:
        _event(action="notification.x.y", metadata={"password": "hunter2"})

    assert "hunter2" not in str(caught.value)


async def test_unserializable_metadata_does_not_raise() -> None:
    event = _event()
    event.metadata["x"] = object()

    async with httpx.AsyncClient() as client, respx.mock(assert_all_called=False) as mock:
        route = mock.post(EVENTS_URL).respond(202)
        with capture_logs() as logs:
            await HttpAuditLogger(client, BASE_URL, SecretStr(TOKEN)).record(event)

    assert not route.called
    [entry] = logs
    assert entry["error_type"] == "PydanticSerializationError"
    assert entry["audit_event"]["event_id"] == str(event.event_id)
    assert entry["audit_event"]["metadata"]["x"].startswith("<object")
