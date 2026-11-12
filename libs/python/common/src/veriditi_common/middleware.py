"""X-Request-ID, log de acesso e 500 padrão para toda requisição HTTP do serviço"""

import functools
import ipaddress
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Final

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from veriditi_common.errors import internal_error_response
from veriditi_common.logging import get_logger

REQUEST_ID_HEADER: Final = "X-Request-ID"
_QUIET_PREFIX: Final = "/health/"
_DEFERRED_KEY: Final = "veriditi_deferred"

DeferredTask = Callable[[], Awaitable[None]]

log = get_logger(__name__)


def _request_id_from(headers: Headers) -> str:
    """Aceita só UUID válido, normalizado para caber em request_id CHAR(36) ascii_bin"""
    raw = headers.get(REQUEST_ID_HEADER)
    if raw:
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            pass
    return str(uuid.uuid4())


def defer(request: Request, func: Callable[..., Awaitable[None]], *args: Any) -> None:
    """Roda depois da resposta, inclusive de erro, porque o handler descarta as BackgroundTasks"""
    pending: list[DeferredTask] | None = request.scope.get("state", {}).get(_DEFERRED_KEY)
    if pending is None:
        raise RuntimeError("RequestContextMiddleware ausente: a tarefa adiada nunca rodaria")
    pending.append(functools.partial(func, *args))


async def _run_deferred(pending: list[DeferredTask]) -> None:
    while pending:
        task = pending.pop(0)
        try:
            await task()
        except Exception:
            log.exception("deferred_task_failed")


# Precisa ser o último add_middleware do app, para ficar por fora do CORS e dos demais
class RequestContextMiddleware:
    """ASGI puro para não quebrar streaming e manter o request_id nas tarefas adiadas"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = _request_id_from(Headers(scope=scope))
        started_at = time.perf_counter()
        status_code = 500
        response_started = False
        pending: list[DeferredTask] = []
        scope.setdefault("state", {})[_DEFERRED_KEY] = pending

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = rid
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=rid):
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception:
                log.exception("unhandled_exception", method=scope["method"], path=scope["path"])
                # O ServerErrorMiddleware do Starlette responderia sem request_id e sem o header
                if response_started:
                    raise
                await internal_error_response()(scope, receive, send_with_request_id)
            finally:
                path: str = scope["path"]
                log.log(
                    logging.DEBUG if path.startswith(_QUIET_PREFIX) else logging.INFO,
                    "request_finished",
                    method=scope["method"],
                    path=path,
                    status_code=status_code,
                    duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
                )
                await _run_deferred(pending)


def current_request_id() -> str | None:
    rid = structlog.contextvars.get_contextvars().get("request_id")
    return rid if isinstance(rid, str) else None


def client_ip(request: Request) -> str | None:
    """O gateway (#11) sobrescreve o X-Forwarded-For com um único IP real"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        try:
            return str(ipaddress.ip_address(forwarded.split(",")[0].strip()))
        except ValueError:
            pass
    return request.client.host if request.client else None
