import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import AsyncClient

from gateway_service.adapters.reverse_proxy import build_http_client
from gateway_service.config import Settings
from gateway_service.main import create_app
from gateway_service.routes import ROUTES

from .conftest import (
    AUTH,
    CLIENT_IP,
    EMAIL,
    TOKEN,
    USER_ID,
    ClientFactory,
    FakeClock,
    JsonLogs,
    RsaKeys,
    TokenFactory,
    raw_request,
)

UNAUTHORIZED = {"detail": {"code": "unauthorized", "message": "Não autenticado."}}
NOT_FOUND = {"detail": {"code": "not_found", "message": "Recurso não encontrado."}}
PROTECTED = [("GET", "/api/me"), ("POST", "/api/me/password"), ("POST", "/api/auth/logout")]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(email: str = "ana@exemplo.com") -> dict[str, Any]:
    return {"json": {"email": email, "password": "Senha-Forte-1"}}


# 1. Roteamento: /api/<rota> chega como /<rota> no auth


@pytest.mark.parametrize(
    ("method", "path", "upstream_path", "status"),
    [
        ("POST", "/api/auth/register", "/auth/register", 201),
        ("POST", "/api/auth/verify-email", "/auth/verify-email", 200),
        ("POST", "/api/auth/verify-email/resend", "/auth/verify-email/resend", 202),
        ("POST", "/api/auth/login", "/auth/login", 200),
        ("POST", "/api/auth/refresh", "/auth/refresh", 200),
        ("POST", "/api/auth/logout", "/auth/logout", 204),
        ("GET", "/api/me", "/me", 200),
        ("PATCH", "/api/me", "/me", 200),
        ("POST", "/api/me/password", "/me/password", 204),
    ],
)
async def test_each_route_reaches_auth_without_api_prefix(
    client: AsyncClient,
    auth_mock: respx.MockRouter,
    make_token: TokenFactory,
    method: str,
    path: str,
    upstream_path: str,
    status: int,
) -> None:
    content = b"" if status == 204 else json.dumps({"ok": path}).encode()
    route = auth_mock.route(method=method, path=upstream_path).respond(status, content=content)

    resp = await client.request(method, path, headers=_bearer(make_token()), json={"x": 1})

    assert route.called
    assert resp.status_code == status
    assert resp.content == content


def test_routing_test_covers_the_whole_table() -> None:
    assert sum(len(r.methods) for r in ROUTES) == 9


@pytest.mark.parametrize("status", [400, 409, 422])
async def test_upstream_errors_are_relayed(
    client: AsyncClient, auth_mock: respx.MockRouter, status: int
) -> None:
    body = {"detail": {"code": "x", "message": "y"}}
    auth_mock.post("/auth/register").respond(status, json=body)

    resp = await client.post("/api/auth/register", json={})

    assert resp.status_code == status
    assert resp.json() == body


async def test_get_me_returns_upstream_json(
    client: AsyncClient, auth_mock: respx.MockRouter, make_token: TokenFactory
) -> None:
    profile = {"id": USER_ID, "name": "Ana", "email": EMAIL}
    auth_mock.get("/me").respond(200, json=profile)

    resp = await client.get("/api/me", headers=_bearer(make_token()))

    assert resp.status_code == 200
    assert resp.json() == profile


# 2. 404 do gateway: o upstream nunca é chamado


@pytest.mark.parametrize(
    "path",
    [
        "/api/notifications",
        "/api/events",
        "/api/internal/events",
        "/api/internal/notifications",
        "/internal/events",
        "/internal/notifications",
        "/api/monitoring/events",
        "/api/audit-events",
        "/api",
        "/docs",
        "/openapi.json",
    ],
)
async def test_unrouted_paths_are_404(
    client: AsyncClient, auth_mock: respx.MockRouter, path: str
) -> None:
    for method in ("GET", "POST"):
        resp = await client.request(method, path)

        assert resp.status_code == 404
        assert resp.json() == NOT_FOUND
    assert not auth_mock.calls


@pytest.mark.parametrize(
    "raw_path",
    [
        b"/api/me/../auth/login",
        b"/api/%2e%2e/internal/events",
        b"/api/me%2Fpassword",
        b"/api//me",
        b"/api/me/",
        b"/api/./me",
    ],
)
async def test_unsafe_raw_paths_are_404(
    app: FastAPI, auth_mock: respx.MockRouter, raw_path: bytes
) -> None:
    resp = await raw_request(app, "POST", raw_path)

    assert resp.status == 404
    assert json.loads(resp.body) == NOT_FOUND
    assert not auth_mock.calls


# 3. 405


async def test_wrong_method_is_405_with_allow(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    resp = await client.put("/api/me")

    assert resp.status_code == 405
    assert resp.headers["Allow"] == "GET, PATCH"
    assert resp.json()["detail"]["code"] == "method_not_allowed"
    assert not auth_mock.calls


# 4. 401 nas rotas protegidas


def _tampered(token: str) -> str:
    header, payload, signature = token.split(".")
    middle = len(payload) // 2
    flipped = "A" if payload[middle] != "A" else "B"
    return f"{header}.{payload[:middle]}{flipped}{payload[middle + 1 :]}.{signature}"


def _bad_tokens(make_token: TokenFactory, keys: RsaKeys, intruder: Any) -> dict[str, str | None]:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    now = int(time.time())
    claims = {"sub": "42", "email": EMAIL, "iat": now, "exp": now + 900}
    claims |= {"iss": "veriditi-auth", "aud": "veriditi"}
    payload = b64(json.dumps(claims).encode())
    none = f"{b64(b'{"alg":"none","typ":"JWT"}')}.{payload}."
    hs_input = f"{b64(b'{"alg":"HS256","typ":"JWT"}')}.{payload}"
    mac = hmac.new(keys.public_pem.encode(), hs_input.encode(), hashlib.sha256).digest()
    return {
        "sem token": None,
        "adulterado": _tampered(make_token()),
        "expirado": make_token(iat=now - 1000, exp=now - 60),
        "iss errado": make_token(iss="outro"),
        "aud errado": make_token(aud="outro"),
        "outra chave": make_token(key=intruder),
        "alg none": none,
        "hs256 com a pública": f"{hs_input}.{b64(mac)}",
        "lixo": "abc.def.ghi",
    }


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_protected_routes_reject_bad_tokens(
    client: AsyncClient,
    auth_mock: respx.MockRouter,
    make_token: TokenFactory,
    rsa_keys: RsaKeys,
    intruder_key: Any,
    method: str,
    path: str,
) -> None:
    for name, token in _bad_tokens(make_token, rsa_keys, intruder_key).items():
        headers = _bearer(token) if token else {}

        resp = await client.request(method, path, headers=headers)

        assert resp.status_code == 401, name
        assert resp.json() == UNAUTHORIZED, name
        assert resp.headers["WWW-Authenticate"] == "Bearer"
    assert not auth_mock.calls


async def test_internal_headers_do_not_replace_token(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    headers = {"X-User-Id": "1", "X-User-Email": "a@x", "X-Internal-Token": TOKEN}

    resp = await client.get("/api/me", headers=headers)

    assert resp.status_code == 401
    assert not auth_mock.calls


# 5. Anti-spoofing ponta a ponta


async def test_forged_headers_are_replaced_on_protected_route(
    client: AsyncClient, auth_mock: respx.MockRouter, make_token: TokenFactory
) -> None:
    route = auth_mock.get("/me").respond(200, json={})
    forged_rid = str(uuid.uuid4())
    headers = {
        **_bearer(make_token()),
        "X-User-Id": "1",
        "X-User-Email": "admin@x",
        "X-Session-Id": str(uuid.uuid4()),
        "X-Internal-Token": "errado",
        "X-Refresh-Token": "r",
        "X-Request-ID": forged_rid,
        "X-Forwarded-For": "6.6.6.6",
        "Forwarded": "for=6.6.6.6",
        "X-Real-IP": "6.6.6.6",
        "Cookie": "a=1",
    }

    resp = await client.get("/api/me", headers=headers)

    sent = route.calls.last.request.headers
    assert sent["x-user-id"] == str(USER_ID)
    assert sent["x-user-email"] == EMAIL
    assert "x-session-id" not in sent
    assert sent["x-internal-token"] == TOKEN
    assert "x-refresh-token" not in sent
    assert sent["x-request-id"] != forged_rid
    assert sent["x-request-id"] == resp.headers["X-Request-ID"]
    assert sent["x-forwarded-for"] == CLIENT_IP
    for name in ("forwarded", "x-real-ip", "authorization", "cookie"):
        assert name not in sent


async def test_session_id_comes_from_sid_claim(
    client: AsyncClient, auth_mock: respx.MockRouter, make_token: TokenFactory
) -> None:
    sid = str(uuid.uuid4())
    route = auth_mock.post("/me/password").respond(204)

    headers = {**_bearer(make_token(sid=sid)), "X-Session-Id": str(uuid.uuid4())}

    await client.post("/api/me/password", headers=headers, json={})

    assert route.calls.last.request.headers.get_list("x-session-id") == [sid]


async def test_forged_user_id_is_dropped_on_public_route(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    route = auth_mock.post("/auth/refresh").respond(200, json={})

    await client.post(
        "/api/auth/refresh", headers={"X-User-Id": "1", "X-User-Email": "a@x"}, json={}
    )

    sent = route.calls.last.request.headers
    assert "x-user-id" not in sent
    assert "x-user-email" not in sent
    assert sent["x-internal-token"] == TOKEN


# 6. X-Forwarded-For só de proxy confiável


@pytest.mark.parametrize(
    ("peer", "expected"), [("10.0.0.5", "198.51.100.9"), (CLIENT_IP, CLIENT_IP)]
)
async def test_forwarded_for_from_trusted_proxy_only(
    client_from: ClientFactory, auth_mock: respx.MockRouter, peer: str, expected: str
) -> None:
    route = auth_mock.post("/auth/refresh").respond(200, json={})

    async with client_from(peer) as client:
        await client.post("/api/auth/refresh", headers={"X-Forwarded-For": "198.51.100.9"}, json={})

    assert route.calls.last.request.headers["x-forwarded-for"] == expected


# 7. Rate limit


async def test_login_rate_limit_by_ip_and_email(
    client: AsyncClient,
    client_from: ClientFactory,
    auth_mock: respx.MockRouter,
    fake_clock: FakeClock,
) -> None:
    route = auth_mock.post("/auth/login").respond(
        401, json={"detail": {"code": "invalid_credentials"}}
    )
    variants = [
        "ana@exemplo.com",
        "ANA@exemplo.com",
        " ana@exemplo.com ",
        "Ana@Exemplo.Com",
        "ana@exemplo.com",
    ]

    statuses = [(await client.post("/api/auth/login", **_login(e))).status_code for e in variants]
    sixth = await client.post("/api/auth/login", **_login())

    assert statuses == [401] * 5
    assert sixth.status_code == 429
    assert sixth.headers["Retry-After"] == "12"
    assert sixth.json() == {
        "detail": {
            "code": "rate_limited",
            "message": "Muitas tentativas. Tente novamente em 12 segundos.",
            "retry_after": 12,
        }
    }
    assert route.call_count == 5

    assert (await client.post("/api/auth/login", **_login("bia@exemplo.com"))).status_code == 401
    async with client_from("198.51.100.20") as other:
        assert (await other.post("/api/auth/login", **_login())).status_code == 401

    fake_clock.advance(12)
    assert (await client.post("/api/auth/login", **_login())).status_code == 401


async def test_register_rate_limit(client: AsyncClient, auth_mock: respx.MockRouter) -> None:
    auth_mock.post("/auth/register").respond(201, json={})

    statuses = [(await client.post("/api/auth/register", json={})).status_code for _ in range(11)]

    assert statuses == [201] * 10 + [429]


async def test_register_429_has_retry_after_six(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    auth_mock.post("/auth/register").respond(201, json={})
    for _ in range(10):
        await client.post("/api/auth/register", json={})

    resp = await client.post("/api/auth/register", json={})

    assert resp.headers["Retry-After"] == "6"
    assert resp.json()["detail"]["retry_after"] == 6


async def test_resend_has_its_own_bucket(client: AsyncClient, auth_mock: respx.MockRouter) -> None:
    auth_mock.post("/auth/register").respond(201, json={})
    auth_mock.post("/auth/verify-email/resend").respond(202, json={})
    for _ in range(10):
        await client.post("/api/auth/register", json={})

    statuses = [
        (await client.post("/api/auth/verify-email/resend", json={})).status_code for _ in range(11)
    ]

    assert statuses == [202] * 10 + [429]


async def test_unlimited_routes_are_not_limited(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    auth_mock.post("/auth/refresh").respond(200, json={})

    statuses = {(await client.post("/api/auth/refresh", json={})).status_code for _ in range(30)}

    assert statuses == {200}


async def test_login_body_over_16_kib_is_413(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    route = auth_mock.post("/auth/login").respond(200, json={})
    body = json.dumps({"email": "a@x.com", "password": "x" * 17_000})

    resp = await client.post(
        "/api/auth/login", content=body, headers={"Content-Type": "application/json"}
    )

    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "payload_too_large"
    assert not route.called


async def test_login_body_is_forwarded_intact(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    route = auth_mock.post("/auth/login").respond(200, json={})
    body = b'{"email": "ana@exemplo.com", "password": "Senha-Forte-1"}'

    await client.post("/api/auth/login", content=body, headers={"Content-Type": "application/json"})

    assert route.calls.last.request.content == body
    assert route.calls.last.request.headers["content-type"] == "application/json"


# 8. Upstream fora do ar


async def test_upstream_down_is_503_and_gateway_recovers(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    route = auth_mock.post("/auth/refresh")
    route.side_effect = httpx.ConnectError("recusado")

    resp = await client.post("/api/auth/refresh", json={})

    assert resp.status_code == 503
    assert resp.json() == {
        "detail": {
            "code": "upstream_unavailable",
            "message": "Serviço de autenticação indisponível.",
            "service": "auth",
        }
    }
    assert "X-Request-ID" in resp.headers
    assert (await client.get("/health/live")).status_code == 200

    route.side_effect = None
    route.return_value = httpx.Response(200, json={"access_token": "x"})
    assert (await client.post("/api/auth/refresh", json={})).status_code == 200


# 9. Timeout


async def test_upstream_timeout_is_504(client: AsyncClient, auth_mock: respx.MockRouter) -> None:
    auth_mock.post("/auth/refresh").mock(side_effect=httpx.ReadTimeout("lento"))

    resp = await client.post("/api/auth/refresh", json={})

    assert resp.status_code == 504
    assert resp.json() == {
        "detail": {
            "code": "upstream_timeout",
            "message": "O serviço de autenticação demorou para responder. Tente novamente.",
            "service": "auth",
        }
    }


def test_real_client_uses_configured_timeout() -> None:
    assert build_http_client(5.0).timeout == httpx.Timeout(5.0)


async def test_settings_timeout_reaches_the_client(app: FastAPI) -> None:
    assert app.state.http.timeout == httpx.Timeout(5.0)


# 10. 502 quando o upstream recusa o token interno


async def test_internal_token_rejection_is_502(
    client: AsyncClient, auth_mock: respx.MockRouter, make_token: TokenFactory, json_logs: JsonLogs
) -> None:
    auth_mock.get("/me").respond(401, json=UNAUTHORIZED)

    resp = await client.get("/api/me", headers=_bearer(make_token()))

    assert resp.status_code == 502
    assert resp.json() == {
        "detail": {
            "code": "upstream_auth_failed",
            "message": "Falha na comunicação interna com o serviço de autenticação. "
            "Tente novamente em instantes.",
            "service": "auth",
        }
    }
    assert [e for e in json_logs() if e["event"] == "upstream_internal_auth_rejected"]


async def test_invalid_credentials_401_is_relayed(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    body = {"detail": {"code": "invalid_credentials", "message": "E-mail ou senha incorretos."}}
    auth_mock.post("/auth/login").respond(401, json=body)

    resp = await client.post("/api/auth/login", **_login())

    assert resp.status_code == 401
    assert resp.json() == body


# 11. Limite de corpo


async def test_declared_body_over_limit_is_413(
    client: AsyncClient, auth_mock: respx.MockRouter, make_token: TokenFactory
) -> None:
    route = auth_mock.post("/me/password").respond(204)

    resp = await client.post(
        "/api/me/password", headers=_bearer(make_token()), content=b"x" * (1024 * 1024 + 1)
    )

    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "payload_too_large"
    assert not route.called


async def test_chunked_body_over_limit_is_413(
    client: AsyncClient, auth_mock: respx.MockRouter, make_token: TokenFactory
) -> None:
    async def chunks() -> Any:
        for _ in range(20):
            yield b"x" * 65536

    auth_mock.post("/me/password").respond(204)

    resp = await client.post("/api/me/password", headers=_bearer(make_token()), content=chunks())

    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "payload_too_large"


async def test_body_within_limit_is_streamed(
    client: AsyncClient, auth_mock: respx.MockRouter, make_token: TokenFactory
) -> None:
    route = auth_mock.post("/me/password").respond(204)
    body = b"y" * (900 * 1024)

    resp = await client.post("/api/me/password", headers=_bearer(make_token()), content=body)

    assert resp.status_code == 204
    assert route.calls.last.request.content == body
    assert route.calls.last.request.headers["content-length"] == str(len(body))


async def test_non_ascii_query_is_400(app: FastAPI, auth_mock: respx.MockRouter) -> None:
    status: dict[str, Any] = {}

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
        elif message["type"] == "http.response.body":
            status["body"] = status.get("body", b"") + message.get("body", b"")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/auth/refresh",
        "raw_path": b"/api/auth/refresh",
        "root_path": "",
        "query_string": "q=é".encode(),
        "headers": [(b"host", b"gateway.test")],
        "client": (CLIENT_IP, 1),
        "server": ("gateway.test", 80),
    }
    await app(scope, receive, send)

    assert status["code"] == 400
    assert json.loads(status["body"])["detail"]["code"] == "invalid_request"
    assert not auth_mock.calls


# 12. Log de acesso


async def test_access_log_has_route_upstream_and_user(
    client: AsyncClient, auth_mock: respx.MockRouter, make_token: TokenFactory, json_logs: JsonLogs
) -> None:
    auth_mock.get("/me").respond(200, json={"id": USER_ID})
    auth_mock.post("/auth/login").respond(200, json={"access_token": "x"})
    token = make_token()

    me = await client.get("/api/me", headers=_bearer(token))
    await client.post("/api/auth/login", json={"email": EMAIL, "password": "Senha-Secreta-9"})

    access = [e for e in json_logs() if e["event"] == "request_finished"]
    me_line, login_line = access
    assert me_line["method"] == "GET"
    assert me_line["path"] == "/api/me"
    assert me_line["route"] == "/api/me"
    assert me_line["upstream"] == "auth"
    assert me_line["status_code"] == 200
    assert isinstance(me_line["duration_ms"], float)
    assert me_line["request_id"] == me.headers["X-Request-ID"]
    assert me_line["user_id"] == USER_ID
    assert login_line["route"] == "/api/auth/login"
    assert "user_id" not in login_line

    everything = json.dumps(json_logs())
    for secret in (token, EMAIL, "Senha-Secreta-9", CLIENT_IP, TOKEN):
        assert secret not in everything


async def test_rejections_are_logged_with_reason(
    client: AsyncClient,
    auth_mock: respx.MockRouter,
    make_token: TokenFactory,
    json_logs: JsonLogs,
) -> None:
    auth_mock.post("/auth/login").respond(401, json={})
    auth_mock.post("/auth/refresh").mock(side_effect=httpx.ConnectError("recusado"))
    now = int(time.time())

    await client.get("/api/me", headers=_bearer(make_token(iat=now - 1000, exp=now - 60)))
    for _ in range(6):
        await client.post("/api/auth/login", **_login())
    await client.post("/api/auth/refresh", json={})

    logs = json_logs()
    [jwt_line] = [e for e in logs if e["event"] == "jwt_rejected"]
    [rate_line] = [e for e in logs if e["event"] == "rate_limited"]
    [down_line] = [e for e in logs if e["event"] == "upstream_unavailable"]
    assert jwt_line["reason"] == "expired"
    assert rate_line["policy"] == "login"
    assert rate_line["retry_after"] == 12
    assert down_line["error_type"] == "ConnectError"
    assert down_line["upstream"] == "auth"
    assert "recusado" not in json.dumps(logs)


async def test_unauthorized_access_log_has_route_without_user(
    client: AsyncClient, json_logs: JsonLogs
) -> None:
    await client.get("/api/me")

    [line] = [e for e in json_logs() if e["event"] == "request_finished"]
    assert line["status_code"] == 401
    assert line["route"] == "/api/me"
    assert "user_id" not in line


# Detalhes do contrato com a web


async def test_cookies_from_upstream_are_relayed_but_not_kept(
    client: AsyncClient, auth_mock: respx.MockRouter, app: FastAPI
) -> None:
    route = auth_mock.post("/auth/refresh").respond(
        200, headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")], json={}
    )

    resp = await client.post("/api/auth/refresh", json={})
    await client.post("/api/auth/refresh", json={})

    assert resp.headers.get_list("set-cookie") == ["a=1", "b=2"]
    assert "cookie" not in route.calls.last.request.headers
    assert len(app.state.http.cookies.jar) == 0


async def test_upstream_user_agent_is_never_httpx(
    client_from: ClientFactory, auth_mock: respx.MockRouter
) -> None:
    route = auth_mock.post("/auth/refresh").respond(200, json={})

    async with client_from(CLIENT_IP) as client:
        client.headers.pop("user-agent")
        await client.post("/api/auth/refresh", json={})
        await client.post("/api/auth/refresh", json={}, headers={"User-Agent": "Mozilla/5.0"})

    first, second = route.calls
    assert "user-agent" not in first.request.headers
    assert second.request.headers["user-agent"] == "Mozilla/5.0"


async def test_injected_client_belongs_to_caller(settings: Settings) -> None:
    http = httpx.AsyncClient(base_url=AUTH)
    app = create_app(settings, http)
    async with app.router.lifespan_context(app):
        assert app.state.http is http

    assert not http.is_closed
    await http.aclose()


async def test_client_disconnect_while_reading_login_body(
    app: FastAPI, auth_mock: respx.MockRouter, json_logs: JsonLogs
) -> None:
    messages: list[dict[str, Any]] = [
        {"type": "http.request", "body": b'{"email":', "more_body": True},
        {"type": "http.disconnect"},
    ]
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/auth/login",
        "raw_path": b"/api/auth/login",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"gateway.test"), (b"transfer-encoding", b"chunked")],
        "client": (CLIENT_IP, 1),
        "server": ("gateway.test", 80),
    }
    await app(scope, receive, send)

    assert not auth_mock.calls
    events = [e["event"] for e in json_logs()]
    assert "client_disconnected" in events
    assert "unhandled_exception" not in events


async def test_lone_surrogate_email_is_not_500_and_still_limited(
    client: AsyncClient, auth_mock: respx.MockRouter, json_logs: JsonLogs
) -> None:
    route = auth_mock.post("/auth/login").respond(422, json={"detail": []})
    body = b'{"email": "a\\ud800@x.com", "password": "p"}'
    headers = {"Content-Type": "application/json"}

    statuses = [
        (await client.post("/api/auth/login", content=body, headers=headers)).status_code
        for _ in range(6)
    ]

    assert statuses == [422] * 5 + [429]
    assert route.call_count == 5
    assert route.calls.last.request.content == body
    assert "unhandled_exception" not in [e["event"] for e in json_logs()]
