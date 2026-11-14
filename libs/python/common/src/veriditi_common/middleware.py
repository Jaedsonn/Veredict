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
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from veriditi_common.errors import http_error_body, internal_error_response
from veriditi_common.logging import get_logger

REQUEST_ID_HEADER: Final = "X-Request-ID"
MAX_IP_LENGTH: Final = 45  # actor_ip VARCHAR(45) em audit_events
_QUIET_PREFIX: Final = "/health/"
_DEFERRED_KEY: Final = "veriditi_deferred"
_LOG_FIELDS_KEY: Final = "veriditi_log_fields"

DeferredTask = Callable[[], Awaitable[None]]


class _DeferredQueue:
    """Fila da requisição; fechada depois de drenada, para nada entrar sem rodar"""

    def __init__(self) -> None:
        self.tasks: list[DeferredTask] = []
        self.closed = False


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


def set_log_fields(request: Request, **fields: str | int) -> None:
    """Campos por requisição sem vazar contextvars entre requisições da mesma task"""
    state = request.scope.setdefault("state", {})
    state.setdefault(_LOG_FIELDS_KEY, {}).update(fields)


def try_defer[**P](
    request: Request, func: Callable[P, Awaitable[None]], *args: P.args, **kwargs: P.kwargs
) -> bool:
    """False se a fila já foi drenada; quem chama decide o que fazer com a tarefa"""
    queue: _DeferredQueue | None = request.scope.get("state", {}).get(_DEFERRED_KEY)
    if queue is None:
        raise RuntimeError("RequestContextMiddleware ausente: a tarefa adiada nunca rodaria")
    if queue.closed:
        return False
    queue.tasks.append(functools.partial(func, *args, **kwargs))
    return True


def defer[**P](
    request: Request, func: Callable[P, Awaitable[None]], *args: P.args, **kwargs: P.kwargs
) -> None:
    """Roda depois da resposta, inclusive de erro, porque o handler descarta as BackgroundTasks"""
    if not try_defer(request, func, *args, **kwargs):
        raise RuntimeError("A fila de tarefas adiadas desta requisição já foi drenada")


def _task_name(task: DeferredTask) -> str:
    func = task.func if isinstance(task, functools.partial) else task
    return str(getattr(func, "__qualname__", repr(func)))


async def _run_deferred(queue: _DeferredQueue) -> None:
    running = False
    try:
        while queue.tasks:
            task = queue.tasks.pop(0)
            running = True
            try:
                await task()
            except Exception:
                log.exception("deferred_task_failed", task=_task_name(task))
            running = False
    except BaseException:
        # Cancelamento no shutdown: registra o que se perdeu antes de propagar
        log.error("deferred_tasks_dropped", count=len(queue.tasks) + int(running))
        raise
    finally:
        queue.closed = True


# Precisa ser o último add_middleware do app, para ficar por fora do CORS e dos demais
class RequestContextMiddleware:
    """ASGI puro para não quebrar streaming e manter o request_id nas tarefas adiadas"""

    def __init__(self, app: ASGIApp, *, trust_request_id: bool = True) -> None:
        self.app = app
        # Ponto de entrada não confia no id do cliente
        self.trust_request_id = trust_request_id

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = _request_id_from(Headers(scope=scope)) if self.trust_request_id else str(uuid.uuid4())
        started_at = time.perf_counter()
        status_code = 500
        response_started = False
        # Fim do corpo, não do app: as BackgroundTasks rodam depois e não contam na latência
        finished_at: float | None = None
        pending = _DeferredQueue()
        scope.setdefault("state", {})[_DEFERRED_KEY] = pending

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started, finished_at
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = rid
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finished_at = time.perf_counter()

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
                extra: dict[str, Any] = dict(scope["state"].get(_LOG_FIELDS_KEY, {}))
                if response_started and finished_at is None:
                    # O status já foi enviado, mas o corpo parou no meio
                    extra["truncated"] = True
                extra.update(
                    method=scope["method"],
                    path=path,
                    status_code=status_code,
                    duration_ms=round(
                        ((finished_at or time.perf_counter()) - started_at) * 1000, 2
                    ),
                )
                log.log(
                    logging.DEBUG if path.startswith(_QUIET_PREFIX) else logging.INFO,
                    "request_finished",
                    **extra,
                )
                await _run_deferred(pending)


def current_request_id() -> str | None:
    rid = structlog.contextvars.get_contextvars().get("request_id")
    return rid if isinstance(rid, str) else None


def _valid_ip(raw: str) -> str | None:
    """Normalizado e cabendo em actor_ip VARCHAR(45); scope id longo é recusado"""
    try:
        ip = str(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return None
    return ip if len(ip) <= MAX_IP_LENGTH else None


def client_ip(request: Request) -> str | None:
    """O gateway (#11) sobrescreve o X-Forwarded-For com um único IP real"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and (ip := _valid_ip(forwarded.split(",")[0])):
        return ip
    return _valid_ip(request.client.host) if request.client else None


class BodySizeLimitMiddleware:
    """413 pelo Content-Length antes de ler e pela contagem do stream quando ele falta"""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = Headers(scope=scope).get("content-length", "")
        # isascii: "²".isdigit() é True, mas int("²") levanta
        if declared.isascii() and declared.isdigit() and int(declared) > self.max_bytes:
            response = JSONResponse(http_error_body(413), status_code=413)
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # Dentro do app: o handler de HTTPException responde no formato padrão
                    raise HTTPException(413)
            return message

        await self.app(scope, limited_receive, send)
