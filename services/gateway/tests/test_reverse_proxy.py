import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import Message
from structlog.testing import capture_logs

from gateway_service.adapters.reverse_proxy import (
    FORWARDED_REQUEST_HEADERS,
    SPOOFABLE_REQUEST_HEADERS,
    ReverseProxy,
    block_cookies,
    build_http_client,
    downstream_headers,
)
from gateway_service.domain import (
    Principal,
    Route,
    Upstream,
    UpstreamAuthRejectedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from gateway_service.routes import ROUTES
from gateway_service.routing import RouteTable

from .conftest import EMAIL, USER_ID

TOKEN = "test-internal-token-0123456789"
UPSTREAMS = {"auth": Upstream("auth", "http://auth.test", "autenticação")}
TABLE = RouteTable(ROUTES, UPSTREAMS)
IP = "203.0.113.7"
PRINCIPAL = Principal(user_id=USER_ID, email=EMAIL)

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


class Recorder:
    """Upstream fake: guarda o que chegou e responde com a fábrica configurada"""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.respond: Callable[[httpx.Request], httpx.Response] = lambda r: httpx.Response(200)

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


class CountingStream(httpx.AsyncByteStream):
    """Conta os pedaços puxados e registra o aclose"""

    def __init__(self, chunks: Sequence[bytes], gate: asyncio.Event | None = None) -> None:
        self.chunks = list(chunks)
        self.pulled = 0
        self.closed = False
        self.gate = gate

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if index and self.gate is not None:
                await self.gate.wait()
            self.pulled += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def upstream() -> Recorder:
    return Recorder()


@pytest.fixture
async def http(upstream: Recorder) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        block_cookies(client)
        yield client


@pytest.fixture
def proxy(http: httpx.AsyncClient) -> ReverseProxy:
    return ReverseProxy(http, UPSTREAMS, SecretStr(TOKEN))


def _request(
    method: str = "GET",
    path: str = "/api/me",
    *,
    headers: Sequence[tuple[str | bytes, str | bytes]] = (),
    query: bytes = b"",
    chunks: Sequence[bytes] | None = None,
    receive: Callable[[], Awaitable[Message]] | None = None,
) -> Request:
    pending = list(chunks if chunks is not None else [b""])

    async def default_receive() -> Message:
        if pending:
            chunk = pending.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(pending)}
        return {"type": "http.disconnect"}

    raw = [
        (
            (k if isinstance(k, bytes) else k.encode()).lower(),
            v if isinstance(v, bytes) else v.encode(),
        )
        for k, v in headers
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query,
        "headers": raw,
        "client": (IP, 50000),
        "server": ("gateway", 8000),
    }
    return Request(scope, receive or default_receive)


async def _forward(
    proxy: ReverseProxy,
    request: Request,
    *,
    principal: Principal | None = PRINCIPAL,
    client_ip: str | None = IP,
    body: bytes | None = None,
) -> Response:
    match = TABLE.match(request.method, request.url.path)
    return await proxy.forward(request, match, principal=principal, client_ip=client_ip, body=body)


async def _body(response: Response) -> bytes:
    assert isinstance(response, StreamingResponse)
    return b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[misc]


def test_allowlist_and_spoofable_are_disjoint() -> None:
    assert FORWARDED_REQUEST_HEADERS.isdisjoint(SPOOFABLE_REQUEST_HEADERS)


@pytest.mark.parametrize("name", sorted(SPOOFABLE_REQUEST_HEADERS))
async def test_spoofable_header_never_reaches_upstream(
    proxy: ReverseProxy, upstream: Recorder, name: str
) -> None:
    mixed = "".join(c.upper() if i % 2 else c for i, c in enumerate(name))

    await _forward(proxy, _request(headers=[(mixed, "forjado"), (name, "forjado2")]))

    for value in upstream.last.headers.get_list(name):
        assert "forjado" not in value


async def test_only_allowlist_and_injected_headers_arrive(
    proxy: ReverseProxy, upstream: Recorder
) -> None:
    headers = [
        ("Accept", "application/json"),
        ("Accept-Language", "pt-BR"),
        ("User-Agent", "Mozilla/5.0"),
        ("If-None-Match", '"abc"'),
        ("X-Desconhecido", "1"),
        ("Origin", "http://web.test"),
        ("Referer", "http://web.test/x"),
    ]

    await _forward(proxy, _request(headers=headers))

    sent = upstream.last.headers
    assert set(sent.keys()) == {
        "host",
        "accept",
        "accept-language",
        "user-agent",
        "if-none-match",
        "x-internal-token",
        "x-request-id",
        "accept-encoding",
        "x-forwarded-for",
        "x-user-id",
        "x-user-email",
    }
    assert sent["x-internal-token"] == TOKEN
    assert sent["x-user-id"] == str(USER_ID)
    assert sent["x-user-email"] == EMAIL
    assert sent["x-forwarded-for"] == IP
    assert sent["accept-encoding"] == "identity"
    assert sent["host"] == "auth.test"
    assert sent["user-agent"] == "Mozilla/5.0"


async def test_httpx_defaults_are_not_sent(proxy: ReverseProxy, upstream: Recorder) -> None:
    await _forward(proxy, _request(), principal=None, client_ip=None)

    sent = upstream.last.headers
    assert "user-agent" not in sent
    assert "accept" not in sent
    assert "connection" not in sent
    assert "x-forwarded-for" not in sent
    assert "x-user-id" not in sent


async def test_request_id_is_a_uuid(proxy: ReverseProxy, upstream: Recorder) -> None:
    await _forward(proxy, _request(headers=[("X-Request-ID", "forjado")]))

    assert len(upstream.last.headers["x-request-id"]) == 36


async def test_unicode_email_goes_as_utf8_bytes(proxy: ReverseProxy, upstream: Recorder) -> None:
    principal = Principal(user_id=7, email="joão@exemplo.com")

    await _forward(proxy, _request(), principal=principal)

    raw = dict(upstream.last.headers.raw)
    assert raw[b"x-user-email"] == "joão@exemplo.com".encode()


async def test_session_id_only_with_sid(proxy: ReverseProxy, upstream: Recorder) -> None:
    sid = "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"

    await _forward(proxy, _request())
    await _forward(proxy, _request(), principal=Principal(1, "a@b.c", session_id=sid))

    assert "x-session-id" not in upstream.requests[0].headers
    assert upstream.requests[1].headers["x-session-id"] == sid


async def test_extra_request_headers_of_route_are_forwarded(
    http: httpx.AsyncClient, upstream: Recorder
) -> None:
    route = Route(
        "/api/hook",
        "auth",
        "/hook",
        public=True,
        extra_request_headers=frozenset({"X-Signature", "Authorization"}),
    )
    proxy = ReverseProxy(http, UPSTREAMS, SecretStr(TOKEN))
    match = RouteTable((route,), UPSTREAMS).match("POST", "/api/hook")
    request = _request(
        "POST", "/api/hook", headers=[("X-Signature", "s"), ("Authorization", "Bearer x")]
    )

    await proxy.forward(request, match, principal=None, client_ip=IP, body=None)

    assert upstream.last.headers["x-signature"] == "s"
    assert "authorization" not in upstream.last.headers


async def test_url_drops_api_prefix_and_keeps_query(
    proxy: ReverseProxy, upstream: Recorder
) -> None:
    request = _request("POST", "/api/me/password", query=b"a=1&b=%20x&a=2")

    await _forward(proxy, request)

    url = upstream.last.url
    assert (url.scheme, url.host, url.path) == ("http", "auth.test", "/me/password")
    assert url.query == b"a=1&b=%20x&a=2"


async def test_non_ascii_query_is_400(proxy: ReverseProxy, upstream: Recorder) -> None:
    with pytest.raises(HTTPException) as exc:
        await _forward(proxy, _request(query="q=é".encode()))

    assert exc.value.status_code == 400
    assert exc.value.detail == {"code": "invalid_request", "message": "Requisição inválida."}
    assert upstream.requests == []


async def test_request_without_body(proxy: ReverseProxy, upstream: Recorder) -> None:
    await _forward(proxy, _request("POST", "/api/auth/logout", chunks=[b"ignorado"]))

    assert upstream.last.content == b""
    assert "transfer-encoding" not in upstream.last.headers


async def test_chunked_request_streams_as_chunked(proxy: ReverseProxy, upstream: Recorder) -> None:
    request = _request(
        "POST",
        "/api/me/password",
        headers=[("Transfer-Encoding", "chunked")],
        chunks=[b'{"a":', b"1}"],
    )

    await _forward(proxy, request)

    assert upstream.last.headers["transfer-encoding"] == "chunked"
    assert "content-length" not in upstream.last.headers
    assert upstream.last.content == b'{"a":1}'


async def test_content_length_is_forwarded(proxy: ReverseProxy, upstream: Recorder) -> None:
    body = b"x" * (900 * 1024)
    chunks = [body[i : i + 65536] for i in range(0, len(body), 65536)]
    request = _request(
        "POST", "/api/me/password", headers=[("Content-Length", str(len(body)))], chunks=chunks
    )

    await _forward(proxy, request)

    assert upstream.last.headers["content-length"] == str(len(body))
    assert "transfer-encoding" not in upstream.last.headers
    assert hashlib.sha256(upstream.last.content).digest() == hashlib.sha256(body).digest()


async def test_buffered_body_is_sent_as_is(proxy: ReverseProxy, upstream: Recorder) -> None:
    body = b'{"email":"ana@exemplo.com","password":"x"}'
    request = _request("POST", "/api/auth/login", headers=[("Content-Type", "application/json")])

    await _forward(proxy, request, principal=None, body=body)

    assert upstream.last.content == body
    assert upstream.last.headers["content-length"] == str(len(body))
    assert upstream.last.headers["content-type"] == "application/json"


async def test_response_is_streamed_lazily(proxy: ReverseProxy, upstream: Recorder) -> None:
    stream = CountingStream([b"a", b"b", b"c"])
    upstream.respond = lambda r: httpx.Response(200, stream=stream)

    response = await _forward(proxy, _request())
    assert isinstance(response, StreamingResponse)
    iterator = response.body_iterator.__aiter__()

    assert await iterator.__anext__() == b"a"
    assert stream.pulled == 1
    assert [chunk async for chunk in iterator] == [b"b", b"c"]
    assert stream.closed


async def test_large_response_arrives_intact(proxy: ReverseProxy, upstream: Recorder) -> None:
    payload = bytes(range(256)) * (5 * 1024 * 1024 // 256)
    chunks = [payload[i : i + 65536] for i in range(0, len(payload), 65536)]
    upstream.respond = lambda r: httpx.Response(200, stream=CountingStream(chunks))

    body = await _body(await _forward(proxy, _request()))

    assert hashlib.sha256(body).digest() == hashlib.sha256(payload).digest()


async def test_partial_consumption_then_close_releases_upstream(
    proxy: ReverseProxy, upstream: Recorder
) -> None:
    stream = CountingStream([b"a", b"b"])
    upstream.respond = lambda r: httpx.Response(200, stream=stream)
    response = await _forward(proxy, _request())
    assert isinstance(response, StreamingResponse)
    iterator: Any = response.body_iterator

    await iterator.__anext__()
    await iterator.aclose()

    assert stream.closed


async def test_cancelled_client_releases_upstream(proxy: ReverseProxy, upstream: Recorder) -> None:
    stream = CountingStream([b"a", b"b"], gate=asyncio.Event())
    upstream.respond = lambda r: httpx.Response(200, stream=stream)
    response = await _forward(proxy, _request())
    assert isinstance(response, StreamingResponse)
    first = asyncio.Event()

    async def consume() -> None:
        async for _ in response.body_iterator:
            first.set()

    task = asyncio.create_task(consume())
    await first.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert stream.closed


def test_downstream_headers_filter() -> None:
    raw = [
        (b"Content-Type", b"application/json"),
        (b"Content-Length", b"2"),
        (b"Set-Cookie", b"a=1"),
        (b"Set-Cookie", b"b=2"),
        (b"Retry-After", b"30"),
        (b"WWW-Authenticate", b"Bearer"),
        (b"Cache-Control", b"no-store"),
        (b"Connection", b"keep-alive, X-Hop"),
        (b"X-Hop", b"1"),
        (b"Keep-Alive", b"timeout=5"),
        (b"Transfer-Encoding", b"chunked"),
        (b"Server", b"uvicorn"),
        (b"Date", b"hoje"),
        (b"X-Request-ID", b"do-upstream"),
        (b"X-Internal-Token", b"vazou"),
        (b"X-User-Id", b"1"),
        (b"X-Refresh-Token", b"r"),
    ]

    assert downstream_headers(raw) == [
        (b"content-type", b"application/json"),
        (b"content-length", b"2"),
        (b"set-cookie", b"a=1"),
        (b"set-cookie", b"b=2"),
        (b"retry-after", b"30"),
        (b"www-authenticate", b"Bearer"),
        (b"cache-control", b"no-store"),
    ]


async def test_response_status_and_headers_are_relayed(
    proxy: ReverseProxy, upstream: Recorder
) -> None:
    upstream.respond = lambda r: httpx.Response(
        201,
        headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"), ("Server", "x")],
        json={"id": 1},
    )

    response = await _forward(proxy, _request("POST", "/api/auth/logout"))

    assert response.status_code == 201
    assert [v for k, v in response.raw_headers if k == b"set-cookie"] == [b"a=1", b"b=2"]
    assert b"server" not in dict(response.raw_headers)
    assert json.loads(await _body(response)) == {"id": 1}


async def test_cookies_are_never_stored_nor_resent(
    proxy: ReverseProxy, upstream: Recorder, http: httpx.AsyncClient
) -> None:
    upstream.respond = lambda r: httpx.Response(200, headers={"Set-Cookie": "sid=usuario1; Path=/"})

    await _body(await _forward(proxy, _request()))
    await _body(await _forward(proxy, _request()))

    assert len(http.cookies.jar) == 0
    assert "cookie" not in upstream.last.headers


def test_build_http_client_settings() -> None:
    client = build_http_client(5.0)

    assert client.timeout == httpx.Timeout(5.0)
    assert client.trust_env is False
    assert client.follow_redirects is False
    response = httpx.Response(
        200, headers={"Set-Cookie": "x=1"}, request=httpx.Request("GET", "http://auth.test/")
    )
    client.cookies.extract_cookies(response)
    assert len(client.cookies.jar) == 0


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ConnectError("recusado"), UpstreamUnavailableError),
        (httpx.PoolTimeout("pool"), UpstreamUnavailableError),
        (httpx.RemoteProtocolError("caiu"), UpstreamUnavailableError),
        (httpx.ReadError("caiu"), UpstreamUnavailableError),
        (httpx.ConnectTimeout("lento"), UpstreamTimeoutError),
        (httpx.ReadTimeout("lento"), UpstreamTimeoutError),
        (httpx.WriteTimeout("lento"), UpstreamTimeoutError),
    ],
)
async def test_transport_errors(
    proxy: ReverseProxy, upstream: Recorder, error: Exception, expected: type[Exception]
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error

    upstream.respond = fail

    with capture_logs() as logs, pytest.raises(expected) as exc:
        await _forward(proxy, _request())

    assert exc.value.upstream == UPSTREAMS["auth"]  # type: ignore[attr-defined]
    assert exc.value.error_type == type(error).__name__  # type: ignore[attr-defined]
    [entry] = logs
    assert entry["event"] in {"upstream_unavailable", "upstream_timeout"}
    assert entry["error_type"] == type(error).__name__
    assert "recusado" not in str(entry)


async def test_internal_token_rejection_becomes_auth_error(
    proxy: ReverseProxy, upstream: Recorder
) -> None:
    stream = CountingStream([b'{"detail":{"code":"unauthorized","message":"N\\u00e3o"}}'])
    upstream.respond = lambda r: httpx.Response(401, stream=stream)

    with capture_logs() as logs, pytest.raises(UpstreamAuthRejectedError):
        await _forward(proxy, _request())

    assert stream.closed
    assert logs[0]["event"] == "upstream_internal_auth_rejected"
    assert logs[0]["log_level"] == "error"


@pytest.mark.parametrize(
    "body",
    [
        b'{"detail":{"code":"invalid_credentials","message":"E-mail ou senha incorretos."}}',
        b"nao json",
        b'{"detail":"unauthorized"}',
        b'{"detail":{"code":"unauthorized"}' + b" " * 9000 + b"}",
    ],
)
async def test_other_401_are_relayed_byte_for_byte(
    proxy: ReverseProxy, upstream: Recorder, body: bytes
) -> None:
    chunks = [body[i : i + 1000] for i in range(0, len(body), 1000)]
    upstream.respond = lambda r: httpx.Response(
        401, headers={"WWW-Authenticate": "Bearer"}, stream=CountingStream(chunks)
    )

    response = await _forward(proxy, _request("POST", "/api/auth/login"), principal=None)

    assert response.status_code == 401
    assert (b"www-authenticate", b"Bearer") in response.raw_headers
    assert await _body(response) == body


async def test_upstream_500_is_relayed(proxy: ReverseProxy, upstream: Recorder) -> None:
    upstream.respond = lambda r: httpx.Response(500, json={"detail": {"code": "internal_error"}})

    response = await _forward(proxy, _request())

    assert response.status_code == 500
    assert json.loads(await _body(response))["detail"]["code"] == "internal_error"


async def test_client_disconnect_during_upload(proxy: ReverseProxy, upstream: Recorder) -> None:
    messages: list[Message] = [
        {"type": "http.request", "body": b"a", "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive() -> Message:
        return messages.pop(0)

    request = _request(
        "POST", "/api/me/password", headers=[("Content-Length", "10")], receive=receive
    )

    with capture_logs() as logs:
        response = await _forward(proxy, request)

    assert response.status_code == 400
    assert [e["event"] for e in logs] == ["client_disconnected"]


async def test_body_limit_error_is_not_upstream_error(
    proxy: ReverseProxy, upstream: Recorder
) -> None:
    async def receive() -> Message:
        raise HTTPException(413)

    request = _request(
        "POST", "/api/me/password", headers=[("Transfer-Encoding", "chunked")], receive=receive
    )

    with pytest.raises(HTTPException) as exc:
        await _forward(proxy, request)

    assert exc.value.status_code == 413
