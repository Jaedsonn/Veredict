from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.types import Message

from veriditi_common.errors import install_error_handlers
from veriditi_common.middleware import (
    REQUEST_ID_HEADER,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
)

LIMIT = 1024
TOO_LARGE = {
    "detail": {"code": "payload_too_large", "message": "Corpo da requisição grande demais."}
}


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    @app.post("/json")
    async def json_body(payload: dict[str, str]) -> dict[str, int]:
        return {"keys": len(payload)}

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=LIMIT)
    app.add_middleware(RequestContextMiddleware)
    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as ac:
        yield ac


async def _chunks(total: int, size: int = 256) -> AsyncIterator[bytes]:
    for start in range(0, total, size):
        yield b"a" * min(size, total - start)


async def test_body_at_the_limit_passes(client: AsyncClient) -> None:
    resp = await client.post("/echo", content=b"a" * LIMIT)

    assert resp.status_code == 200
    assert resp.json() == {"size": LIMIT}


async def test_declared_length_above_limit_is_rejected_before_reading(
    client: AsyncClient,
) -> None:
    resp = await client.post("/echo", content=b"a" * (LIMIT + 1))

    assert resp.status_code == 413
    assert resp.json() == TOO_LARGE
    assert REQUEST_ID_HEADER in resp.headers


@pytest.mark.parametrize("path", ["/echo", "/json"])
async def test_stream_without_length_is_counted(client: AsyncClient, path: str) -> None:
    resp = await client.post(
        path, content=_chunks(LIMIT * 4), headers={"content-type": "application/json"}
    )

    assert "content-length" not in resp.request.headers
    assert resp.status_code == 413
    assert resp.json() == TOO_LARGE


async def test_small_stream_without_length_passes(client: AsyncClient) -> None:
    resp = await client.post("/echo", content=_chunks(LIMIT))

    assert resp.status_code == 200
    assert resp.json() == {"size": LIMIT}


async def test_get_without_body_is_not_affected(client: AsyncClient) -> None:
    assert (await client.get("/nao-existe")).status_code == 404


@pytest.mark.parametrize("declared", ["²", "¹²", "-1", "abc"])
async def test_invalid_content_length_falls_back_to_counting(declared: str) -> None:
    app = _app()
    # Headers ASGI chegam em latin-1: "²" vira o byte 0xb2
    headers = [
        (b"content-length", declared.encode("latin-1")),
        (b"content-type", b"application/json"),
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/echo",
        "raw_path": b"/echo",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("t", 80),
    }
    messages = [{"type": "http.request", "body": b"a" * (LIMIT + 1), "more_body": False}]
    sent: list[Message] = []

    async def receive() -> Message:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)

    assert sent[0]["status"] == 413
