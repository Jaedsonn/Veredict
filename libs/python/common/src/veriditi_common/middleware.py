"""Middleware de contexto de requisição e propagação de X-Request-ID (ADR-001, ADR-012)."""

import uuid
from dataclasses import dataclass

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Metadados transversais da requisição para correlação e auditoria."""

    request_id: str
    actor_ip: str | None = None
    user_agent: str | None = None


def _extract_request_id(raw_value: str | None) -> str:
    if raw_value:
        try:
            return str(uuid.UUID(raw_value.strip()))
        except ValueError:
            pass
    return str(uuid.uuid4())


def _extract_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop[:45]
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()[:45]
    if request.client and request.client.host:
        return request.client.host[:45]
    return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Lê ou gera X-Request-ID (UUID4), injeta no structlog e devolve no header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _extract_request_id(request.headers.get("x-request-id"))
        actor_ip = _extract_client_ip(request)
        user_agent_raw = request.headers.get("user-agent")
        user_agent = user_agent_raw[:255] if user_agent_raw else None

        ctx = RequestContext(
            request_id=request_id,
            actor_ip=actor_ip,
            user_agent=user_agent,
        )
        request.state.context = ctx

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, actor_ip=actor_ip)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers["X-Request-ID"] = request_id
        return response


def get_request_context(request: Request) -> RequestContext:
    """Dependência FastAPI para obter o contexto de requisição em rotas."""
    ctx: RequestContext | None = getattr(request.state, "context", None)
    if ctx is not None:
        return ctx
    request_id = _extract_request_id(request.headers.get("x-request-id"))
    actor_ip = _extract_client_ip(request)
    user_agent_raw = request.headers.get("user-agent")
    return RequestContext(
        request_id=request_id,
        actor_ip=actor_ip,
        user_agent=user_agent_raw[:255] if user_agent_raw else None,
    )
