import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from veriditi_common import security
from veriditi_common.errors import install_error_handlers
from veriditi_common.middleware import RequestContextMiddleware
from veriditi_common.security import (
    INTERNAL_HEADERS,
    CurrentUser,
    CurrentUserDep,
    InternalTokenDep,
    install_internal_auth,
    internal_router,
)

JsonLogs = Callable[[], list[dict[str, Any]]]
TOKEN = "test-internal-token-0123456789"
SID = "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"
UNAUTHORIZED = {"detail": {"code": "unauthorized", "message": "Não autenticado."}}


def _app(*, install: bool = True) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    if install:
        install_internal_auth(app, SecretStr(TOKEN))

    @app.get("/internal")
    async def internal(_: InternalTokenDep) -> dict[str, str]:
        return {"ok": "1"}

    @app.get("/me")
    async def me(user: CurrentUserDep) -> dict[str, Any]:
        return {"id": user.id, "email": user.email, "session_id": user.session_id}

    app.add_middleware(RequestContextMiddleware)
    return app


async def _get(
    path: str, headers: dict[str, str | bytes] | None = None, *, app: FastAPI | None = None
) -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app or _app()), base_url="http://t") as c:
        return await c.get(path, headers=headers)


def _user_headers(**overrides: str | None) -> dict[str, str | bytes]:
    headers: dict[str, str | None] = {
        "X-Internal-Token": TOKEN,
        "X-User-Id": "42",
        "X-User-Email": "a@x.com",
        "X-Session-Id": SID,
    }
    headers.update(overrides)
    return {k: v for k, v in headers.items() if v is not None}


async def test_missing_token_is_401() -> None:
    resp = await _get("/internal")

    assert resp.status_code == 401
    assert resp.json() == UNAUTHORIZED


async def test_wrong_token_of_same_length_is_401() -> None:
    resp = await _get("/internal", {"X-Internal-Token": "x" * len(TOKEN)})

    assert resp.status_code == 401


async def test_non_ascii_token_is_401_not_500() -> None:
    resp = await _get("/internal", {"X-Internal-Token": "tökén-ñão-ascii".encode()})

    assert resp.status_code == 401


async def test_right_token_passes() -> None:
    resp = await _get("/internal", {"X-Internal-Token": TOKEN})

    assert resp.status_code == 200


async def test_uses_compare_digest_over_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, object]] = []

    def spy(a: bytes, b: bytes) -> bool:
        calls.append((a, b))
        return a == b

    monkeypatch.setattr(security.hmac, "compare_digest", spy)

    await _get("/internal", {"X-Internal-Token": TOKEN})

    assert calls == [(TOKEN.encode(), TOKEN.encode())]


async def test_fails_closed_without_install() -> None:
    resp = await _get("/internal", {"X-Internal-Token": TOKEN}, app=_app(install=False))

    assert resp.status_code == 500


def test_install_rejects_empty_token() -> None:
    with pytest.raises(ValueError):
        install_internal_auth(FastAPI(), SecretStr(""))


async def test_rejection_log_does_not_contain_the_token(json_logs: JsonLogs) -> None:
    await _get("/internal", {"X-Internal-Token": "valor-enviado-errado"})
    await _get("/internal")

    rejected = [e for e in json_logs() if e["event"] == "internal_token_rejected"]
    assert [e["reason"] for e in rejected] == ["invalid", "missing"]
    assert "valor-enviado-errado" not in json.dumps(json_logs())


async def test_current_user_from_gateway_headers() -> None:
    resp = await _get("/me", _user_headers(**{"X-Session-Id": SID.upper()}))

    assert CurrentUser(**resp.json()) == CurrentUser(42, "a@x.com", SID)


async def test_session_id_is_optional() -> None:
    resp = await _get("/me", _user_headers(**{"X-Session-Id": None}))

    assert resp.json()["session_id"] is None


async def test_user_headers_without_token_are_rejected() -> None:
    resp = await _get("/me", _user_headers(**{"X-Internal-Token": None}))

    assert resp.status_code == 401


@pytest.mark.parametrize("user_id", [None, "0", "-1", "abc", "9223372036854775808", "42\n"])
async def test_invalid_user_id_is_401(user_id: str | None) -> None:
    resp = await _get("/me", _user_headers(**{"X-User-Id": user_id}))

    assert resp.status_code == 401
    assert resp.json() == UNAUTHORIZED


async def test_max_bigint_user_id_is_accepted() -> None:
    resp = await _get("/me", _user_headers(**{"X-User-Id": "9223372036854775807"}))

    assert resp.json()["id"] == 2**63 - 1


@pytest.mark.parametrize("email", [None, "a" * 250 + "@x.com"])
async def test_invalid_email_is_401(email: str | None) -> None:
    resp = await _get("/me", _user_headers(**{"X-User-Email": email}))

    assert resp.status_code == 401


async def test_invalid_session_id_is_401() -> None:
    resp = await _get("/me", _user_headers(**{"X-Session-Id": "nao-e-uuid"}))

    assert resp.status_code == 401


def test_internal_headers() -> None:
    expected = {"x-internal-token", "x-user-id", "x-user-email", "x-session-id"}

    assert expected == INTERNAL_HEADERS


async def test_internal_router_requires_token_on_every_route() -> None:
    app = FastAPI()
    install_error_handlers(app)
    install_internal_auth(app, SecretStr(TOKEN))
    router = internal_router()

    @router.post("/events", status_code=202)
    async def events() -> dict[str, str]:
        return {"ok": "1"}

    app.include_router(router)
    app.add_middleware(RequestContextMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        denied = await client.post("/internal/events")
        allowed = await client.post("/internal/events", headers={"X-Internal-Token": TOKEN})

    assert denied.status_code == 401
    assert denied.json() == UNAUTHORIZED
    assert allowed.status_code == 202
