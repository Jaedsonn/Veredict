import asyncio
import io
import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import BackgroundTasks, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from veriditi_common.errors import AppError, install_error_handlers
from veriditi_common.health import build_health_router
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    client_ip,
    current_request_id,
    defer,
)

JsonLogs = Callable[[], list[dict[str, Any]]]
RID = "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"


def _app(seen: dict[str, Any] | None = None) -> FastAPI:
    seen = seen if seen is not None else {}
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(build_health_router())

    @app.get("/x")
    async def x(background_tasks: BackgroundTasks) -> dict[str, str | None]:
        seen["route"] = current_request_id()
        background_tasks.add_task(lambda: seen.__setitem__("task", current_request_id()))
        return {"ok": "1"}

    @app.get("/slow-task")
    async def slow_task(background_tasks: BackgroundTasks) -> dict[str, str]:
        background_tasks.add_task(asyncio.sleep, 0.3)
        return {"ok": "1"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("explodiu")

    @app.get("/app-error")
    async def app_error() -> None:
        raise AppError(400, "invalid_code", "Código incorreto.")

    @app.get("/ip")
    async def ip(request: Request) -> dict[str, str | None]:
        return {"ip": client_ip(request)}

    app.add_middleware(RequestContextMiddleware)
    return app


async def _get(
    path: str, headers: dict[str, str] | None = None, app: FastAPI | None = None
) -> httpx.Response:
    transport = ASGITransport(app=app or _app(), client=("10.0.0.9", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_generates_uuid4_without_header() -> None:
    resp = await _get("/x")

    assert uuid.UUID(resp.headers[REQUEST_ID_HEADER]).version == 4


async def test_echoes_valid_uuid_normalized() -> None:
    resp = await _get("/x", headers={REQUEST_ID_HEADER: RID.upper()})

    assert resp.headers[REQUEST_ID_HEADER] == RID


@pytest.mark.parametrize("invalid", ["abc", "a" * 200, "nao-e-uuid"])
async def test_invalid_header_is_replaced(invalid: str) -> None:
    resp = await _get("/x", headers={REQUEST_ID_HEADER: invalid})

    rid = resp.headers[REQUEST_ID_HEADER]
    assert rid != invalid
    assert uuid.UUID(rid).version == 4


async def test_request_id_in_route_and_background_task_then_cleared() -> None:
    seen: dict[str, Any] = {}

    resp = await _get("/x", app=_app(seen))

    assert seen["route"] == seen["task"] == resp.headers[REQUEST_ID_HEADER]
    assert current_request_id() is None


async def test_access_log_has_request_fields(json_logs: JsonLogs) -> None:
    resp = await _get("/x?token=abc", headers={REQUEST_ID_HEADER: RID})

    [line] = [entry for entry in json_logs() if entry["event"] == "request_finished"]
    assert line["request_id"] == resp.headers[REQUEST_ID_HEADER] == RID
    assert line["method"] == "GET"
    assert line["path"] == "/x"
    assert line["status_code"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["level"] == "info"
    assert "abc" not in json.dumps(json_logs())


@pytest.mark.parametrize(("level", "logged"), [("INFO", False), ("DEBUG", True)])
async def test_health_access_log_only_in_debug(
    reset_logging: None, level: str, logged: bool
) -> None:
    stream = io.StringIO()
    configure_logging("svc", level=level, stream=stream)

    await _get("/health/live")

    assert ("request_finished" in stream.getvalue()) is logged


async def test_unhandled_exception_is_standard_500_with_request_id(json_logs: JsonLogs) -> None:
    resp = await _get("/boom", headers={REQUEST_ID_HEADER: RID})

    assert resp.status_code == 500
    assert resp.headers[REQUEST_ID_HEADER] == RID
    assert resp.json()["detail"]["code"] == "internal_error"
    [error] = [entry for entry in json_logs() if entry["event"] == "unhandled_exception"]
    assert error["level"] == "error"
    assert error["request_id"] == RID
    assert "exception" in error
    [access] = [entry for entry in json_logs() if entry["event"] == "request_finished"]
    assert access["status_code"] == 500


async def test_app_error_also_has_request_id() -> None:
    resp = await _get("/app-error")

    assert resp.status_code == 400
    assert REQUEST_ID_HEADER in resp.headers


async def test_non_http_scope_passes_through_unchanged() -> None:
    received: list[Scope] = []

    async def fake_app(scope: Scope, receive: Receive, send: Send) -> None:
        received.append(scope)

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        return None

    scope: Scope = {"type": "lifespan", "asgi": {"version": "3.0"}}
    await RequestContextMiddleware(fake_app)(scope, receive, send)

    assert received == [scope]
    assert received[0] is scope


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [
        ("203.0.113.5", "203.0.113.5"),
        ("203.0.113.5, 10.0.0.1", "203.0.113.5"),
        ("2001:db8::1", "2001:db8::1"),
        ("nao-e-ip", "10.0.0.9"),
        ("fe80::1%" + "a" * 80, "10.0.0.9"),
        ("fe80::1%eth0", "fe80::1%eth0"),
        (None, "10.0.0.9"),
    ],
)
async def test_client_ip(forwarded: str | None, expected: str) -> None:
    headers = {"X-Forwarded-For": forwarded} if forwarded else None

    resp = await _get("/ip", headers=headers)

    assert resp.json() == {"ip": expected}


async def test_deferred_tasks_run_after_response_even_on_error(json_logs: JsonLogs) -> None:
    order: list[str] = []
    app = FastAPI()
    install_error_handlers(app)

    async def task(name: str) -> None:
        order.append(name)

    async def failing() -> None:
        raise RuntimeError("tarefa quebrou")

    @app.get("/x")
    async def x(request: Request) -> None:
        defer(request, failing)
        defer(request, task, "depois")
        raise AppError(400, "invalid_code", "Código incorreto.")

    app.add_middleware(RequestContextMiddleware)

    async def outer(scope: Scope, receive: Receive, send: Send) -> None:
        async def spy(message: Message) -> None:
            if message["type"] == "http.response.body" and not message.get("more_body"):
                order.append("resposta")
            await send(message)

        await app(scope, receive, spy)

    async with AsyncClient(transport=ASGITransport(app=outer), base_url="http://t") as client:
        resp = await client.get("/x")

    assert resp.status_code == 400
    assert order == ["resposta", "depois"]
    [failed] = [e for e in json_logs() if e["event"] == "deferred_task_failed"]
    assert failed["request_id"] == resp.headers[REQUEST_ID_HEADER]


async def test_defer_without_middleware_fails_loudly() -> None:
    app = FastAPI()

    @app.get("/x")
    async def x(request: Request) -> None:
        defer(request, asyncio.sleep, 0)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        with pytest.raises(RuntimeError, match="RequestContextMiddleware"):
            await client.get("/x")


async def test_client_ip_ignores_client_host_that_is_not_an_ip() -> None:
    app = _app()
    transport = ASGITransport(app=app, client=("testclient", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ip")

    assert resp.json() == {"ip": None}


async def test_duration_stops_at_response_body_not_background_tasks(json_logs: JsonLogs) -> None:
    await _get("/slow-task")

    [line] = [e for e in json_logs() if e["event"] == "request_finished"]
    assert line["duration_ms"] < 300
