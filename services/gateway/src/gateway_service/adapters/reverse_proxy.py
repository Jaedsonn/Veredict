"""Proxy reverso em streaming: allowlist de headers do cliente e headers internos injetados"""

import json
import uuid
from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from http.cookiejar import DefaultCookiePolicy
from typing import Final

import anyio
import httpx
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.background import BackgroundTask
from starlette.datastructures import Headers
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response, StreamingResponse

from gateway_service.domain import (
    Principal,
    Upstream,
    UpstreamAuthRejectedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from gateway_service.routing import RouteMatch
from veriditi_common.logging import get_logger
from veriditi_common.middleware import current_request_id
from veriditi_common.security import INTERNAL_HEADERS

# Os quatro últimos ficam prontos para o download de provas da Sprint 2
FORWARDED_REQUEST_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "accept",
        "accept-language",
        "content-type",
        "user-agent",
        "if-match",
        "if-none-match",
        "if-modified-since",
        "if-unmodified-since",
        "range",
        "if-range",
    }
)
HOP_BY_HOP_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
SPOOFABLE_REQUEST_HEADERS: Final[frozenset[str]] = INTERNAL_HEADERS | frozenset(
    {
        "x-refresh-token",
        "x-request-id",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-forwarded-port",
        "x-real-ip",
        "forwarded",
        "via",
        "authorization",
        "cookie",
        "host",
        "connection",
        "keep-alive",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "proxy-authorization",
        "proxy-connection",
        "expect",
        "accept-encoding",
    }
)
# server e date: o uvicorn do gateway põe os dele; x-request-id: o middleware reescreve
_DROPPED_RESPONSE_HEADERS: Final[frozenset[bytes]] = frozenset(
    h.encode()
    for h in HOP_BY_HOP_HEADERS
    | INTERNAL_HEADERS
    | {"server", "date", "x-request-id", "x-refresh-token"}
)
# Host e o enquadramento do corpo vêm do build_request; o resto dos defaults do httpx sai
_BUILT_HEADERS: Final = frozenset({b"host", b"content-length", b"transfer-encoding"})
_MAX_401_BODY: Final = 8 * 1024
_INTERNAL_AUTH_CODE: Final = "unauthorized"
_INVALID_REQUEST: Final = {"code": "invalid_request", "message": "Requisição inválida."}

log = get_logger(__name__)


def block_cookies(client: httpx.AsyncClient) -> None:
    """O jar do httpx reenviaria o Set-Cookie de um usuário nas requisições de outro"""
    client.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))


def build_http_client(timeout_seconds: float) -> httpx.AsyncClient:
    """trust_env=False: um HTTP_PROXY no ambiente não desvia o tráfego interno"""
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        trust_env=False,
        follow_redirects=False,
    )
    block_cookies(client)
    return client


def upstream_headers(
    client_headers: Headers,
    *,
    principal: Principal | None,
    client_ip: str | None,
    request_id: str,
    internal_token: SecretStr,
    extra: frozenset[str] = frozenset(),
) -> list[tuple[bytes, bytes]]:
    """Allowlist do cliente + headers do gateway, sempre sobrescrevendo"""
    allowed = (FORWARDED_REQUEST_HEADERS | {h.lower() for h in extra}) - SPOOFABLE_REQUEST_HEADERS
    headers = [
        (name, value)
        for name, value in client_headers.raw
        if name.decode("latin-1").lower() in allowed
    ]
    headers += [
        (b"x-internal-token", internal_token.get_secret_value().encode()),
        (b"x-request-id", request_id.encode()),
        (b"accept-encoding", b"identity"),
    ]
    if client_ip is not None:
        headers.append((b"x-forwarded-for", client_ip.encode()))
    if principal is not None:
        headers.append((b"x-user-id", str(principal.user_id).encode()))
        # Bytes UTF-8: o httpx codificaria str em ASCII e o e-mail pode ser Unicode
        headers.append((b"x-user-email", principal.email.encode()))
        if principal.session_id is not None:
            headers.append((b"x-session-id", principal.session_id.encode()))
    return headers


def downstream_headers(raw: Sequence[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """Lista e não dict, para preservar Set-Cookie repetido"""
    listed = {
        token.strip().lower().encode()
        for name, value in raw
        if name.lower() == b"connection"
        for token in value.decode("latin-1").split(",")
    }
    dropped = _DROPPED_RESPONSE_HEADERS | listed
    return [(name.lower(), value) for name, value in raw if name.lower() not in dropped]


def _declared_length(headers: Headers) -> str | None:
    value = headers.get("content-length")
    return value if value is not None and value.isascii() and value.isdigit() else None


def _has_body(headers: Headers) -> bool:
    length = _declared_length(headers)
    if length is not None:
        return int(length) > 0
    return "chunked" in headers.get("transfer-encoding", "").lower()


def _is_internal_auth_rejection(body: bytes) -> bool:
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return False
    detail = data.get("detail") if isinstance(data, dict) else None
    return isinstance(detail, dict) and detail.get("code") == _INTERNAL_AUTH_CODE


async def _raw_body(resp: httpx.Response) -> AsyncIterator[bytes]:
    """Bytes crus; um transport em memória (MockTransport, respx) já entrega o corpo lido"""
    if resp.is_stream_consumed:
        yield resp.content
        return
    async for chunk in resp.aiter_raw():
        yield chunk


async def _read_prefix(raw: AsyncIterator[bytes], limit: int) -> list[bytes]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in raw:
        chunks.append(chunk)
        size += len(chunk)
        if size >= limit:
            break
    return chunks


async def _relay(
    prefix: list[bytes], raw: AsyncIterator[bytes], resp: httpx.Response
) -> AsyncIterator[bytes]:
    try:
        for chunk in prefix:
            yield chunk
        async for chunk in raw:
            yield chunk
    finally:
        # Sem o shield, o cancelamento de um cliente que desconecta pula o aclose e vaza a conexão
        with anyio.CancelScope(shield=True):
            await resp.aclose()


class ReverseProxy:
    def __init__(
        self,
        client: httpx.AsyncClient,
        upstreams: Mapping[str, Upstream],
        internal_token: SecretStr,
    ) -> None:
        self._client = client
        self._upstreams = dict(upstreams)
        self._token = internal_token

    async def forward(
        self,
        request: Request,
        match: RouteMatch,
        *,
        principal: Principal | None,
        client_ip: str | None,
        body: bytes | None,
    ) -> Response:
        route = match.route
        upstream = self._upstreams[route.upstream]
        try:
            # Query byte a byte; o path vem da tabela, nunca do cliente
            url = httpx.URL(
                upstream.base_url + match.upstream_path,
                query=request.scope.get("query_string") or None,
            )
        except (UnicodeDecodeError, httpx.InvalidURL):
            raise HTTPException(400, detail=_INVALID_REQUEST) from None

        headers = upstream_headers(
            request.headers,
            principal=principal,
            client_ip=client_ip,
            request_id=current_request_id() or str(uuid.uuid4()),
            internal_token=self._token,
            extra=route.extra_request_headers,
        )
        content: bytes | AsyncIterable[bytes] | None = None
        if body is not None:
            content = body
        elif _has_body(request.headers):
            content = request.stream()
            if (length := _declared_length(request.headers)) is not None:
                headers.append((b"content-length", length.encode()))

        upstream_request = self._client.build_request(
            request.method, url, headers=headers, content=content
        )
        keep = {name.lower() for name, _ in headers} | _BUILT_HEADERS
        for name in [n for n in upstream_request.headers if n.lower().encode() not in keep]:
            del upstream_request.headers[name]

        try:
            resp = await self._client.send(upstream_request, stream=True)
        except ClientDisconnect:
            log.info("client_disconnected", upstream=upstream.name)
            # Ninguém recebe esta resposta; evita o unhandled_exception no middleware
            return Response(status_code=400)
        except httpx.PoolTimeout as exc:
            raise self._unavailable(upstream, exc) from None
        except httpx.TimeoutException as exc:
            log.warning("upstream_timeout", upstream=upstream.name, error_type=type(exc).__name__)
            raise UpstreamTimeoutError(upstream, type(exc).__name__) from None
        except httpx.TransportError as exc:
            raise self._unavailable(upstream, exc) from None

        raw = _raw_body(resp)
        prefix: list[bytes] = []
        try:
            if resp.status_code == 401:
                prefix = await _read_prefix(raw, _MAX_401_BODY)
        except httpx.TransportError as exc:
            await resp.aclose()
            raise self._unavailable(upstream, exc) from None
        if prefix and _is_internal_auth_rejection(b"".join(prefix)):
            await resp.aclose()
            log.error("upstream_internal_auth_rejected", upstream=upstream.name)
            raise UpstreamAuthRejectedError(upstream)

        response = StreamingResponse(
            _relay(prefix, raw, resp),
            status_code=resp.status_code,
            background=BackgroundTask(resp.aclose),
        )
        response.raw_headers = downstream_headers(resp.headers.raw)
        return response

    @staticmethod
    def _unavailable(upstream: Upstream, exc: Exception) -> UpstreamUnavailableError:
        log.warning("upstream_unavailable", upstream=upstream.name, error_type=type(exc).__name__)
        return UpstreamUnavailableError(upstream, type(exc).__name__)
