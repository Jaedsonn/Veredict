"""Testes unitários dos módulos de [S1-04] em `veriditi_common`."""

import uuid
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from veriditi_common.audit import (
    AuditEvent,
    AuditOutcome,
    HttpAuditLogger,
    InMemoryAuditLogger,
    sanitize_metadata,
)
from veriditi_common.logging import configure_logging, get_logger
from veriditi_common.middleware import (
    RequestContext,
    RequestContextMiddleware,
    get_request_context,
)
from veriditi_common.notifications import (
    HttpNotifier,
    InMemoryNotifier,
    NotificationRequest,
)
from veriditi_common.security import (
    AuthenticatedUser,
    get_current_user,
    require_internal_token,
)
from veriditi_common.settings import ServiceSettings


class _TestAppSettings(ServiceSettings):
    service_name: str = "auth"
    db_user: str = "auth_svc"
    internal_api_token: SecretStr = SecretStr("expected-internal-token")


def test_configure_logging_and_get_logger() -> None:
    configure_logging("auth")
    log = get_logger("test")
    assert log is not None


def test_audit_event_strips_sensitive_metadata() -> None:
    cleaned = sanitize_metadata(
        {
            "email": "alice@example.com",
            "password": "secret-password",
            "raw_code": "123456",
            "nested": {"refresh_token": "tok", "reason": "wrong_password"},
        }
    )
    assert cleaned is not None
    assert cleaned["email"] == "alice@example.com"
    assert "password" not in cleaned
    assert "raw_code" not in cleaned
    assert "refresh_token" not in cleaned["nested"]
    assert cleaned["nested"]["reason"] == "wrong_password"

    event = AuditEvent(
        service="auth",
        action="auth.session.login_failed",
        outcome=AuditOutcome.FAILURE,
        metadata={"password": "leaked", "reason": "wrong_password"},
    )
    assert event.metadata == {"reason": "wrong_password"}


async def test_in_memory_and_http_audit_logger_resilience() -> None:
    mem = InMemoryAuditLogger()
    event = AuditEvent(
        service="auth",
        action="auth.user.registered",
        actor_id=1,
        outcome=AuditOutcome.SUCCESS,
        metadata={"email": "alice@example.com"},
    )
    await mem.record(event)
    assert len(mem.events) == 1
    assert len(mem.find("auth.user.registered")) == 1

    received_payloads: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Internal-Token"] == "secret-token"
        received_payloads.append(request.content)
        return httpx.Response(202, json={"status": "accepted"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        http_logger = HttpAuditLogger(
            client=client, base_url="http://monitoring:8000", token="secret-token"
        )
        await http_logger.record(event)
    assert len(received_payloads) == 1

    def failing_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("monitoring down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)) as client:
        resilient_logger = HttpAuditLogger(
            client=client, base_url="http://monitoring:8000", token="secret-token"
        )
        # Não deve propagar exceção (ADR-008: degradação graciosa para stdout)
        await resilient_logger.record(event)


async def test_in_memory_and_http_notifier_resilience() -> None:
    mem = InMemoryNotifier()
    req = NotificationRequest(
        template="email_verification",
        to="alice@example.com",
        data={"code": "123456"},
        idempotency_key="email_verification:1",
    )
    await mem.send(req)
    assert len(mem.sent) == 1
    assert len(mem.find_by_template("email_verification")) == 1

    def failing_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)) as client:
        http_notifier = HttpNotifier(
            client=client, base_url="http://notification:8000", token="secret-token"
        )
        await http_notifier.send(req)


async def test_request_context_middleware_and_security_dependencies() -> None:
    app = FastAPI()
    app.state.settings = _TestAppSettings()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ctx")
    async def read_ctx(
        ctx: Annotated[RequestContext, Depends(get_request_context)],
    ) -> dict[str, str | None]:
        return {
            "request_id": ctx.request_id,
            "actor_ip": ctx.actor_ip,
            "user_agent": ctx.user_agent,
        }

    @app.get("/protected", dependencies=[Depends(require_internal_token)])
    async def read_protected(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> dict[str, int | str | None]:
        return {"user_id": user.id, "email": user.email}

    req_uuid = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/ctx",
            headers={
                "X-Request-Id": req_uuid,
                "X-Forwarded-For": "203.0.113.9, 10.0.0.1",
                "User-Agent": "VeriditiTest/1.0",
            },
        )
        assert r.status_code == 200
        assert r.headers["X-Request-ID"] == req_uuid
        body = r.json()
        assert body["request_id"] == req_uuid
        assert body["actor_ip"] == "203.0.113.9"
        assert body["user_agent"] == "VeriditiTest/1.0"

        # Sem X-Internal-Token -> 401
        r_no_token = await client.get("/protected", headers={"X-User-Id": "42"})
        assert r_no_token.status_code == 401

        # Com X-Internal-Token válido mas sem X-User-Id -> 401
        r_no_user = await client.get(
            "/protected", headers={"X-Internal-Token": "expected-internal-token"}
        )
        assert r_no_user.status_code == 401

        # Com ambos válidos -> 200
        r_ok = await client.get(
            "/protected",
            headers={
                "X-Internal-Token": "expected-internal-token",
                "X-User-Id": "42",
                "X-User-Email": "alice@example.com",
            },
        )
        assert r_ok.status_code == 200
        assert r_ok.json() == {"user_id": 42, "email": "alice@example.com"}
