"""App factory do serviço de Pagamento e tradução dos erros de domínio para HTTP"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from payment_service.adapters.qr import SegnoQrRenderer
from payment_service.adapters.sandbox_provider import SandboxPixProvider
from payment_service.api import credits, orders, packages
from payment_service.config import Settings, get_settings
from payment_service.dependencies import get_session
from payment_service.domain import (
    IdempotencyKeyReusedError,
    OrderNotFoundError,
    OrderNotPayableError,
    PackageNotFoundError,
    PaymentError,
    ProviderUnavailableError,
)
from payment_service.ports import Clock, PaymentProvider, QrRenderer, system_clock
from veriditi_common.audit import AuditLogger, HttpAuditLogger
from veriditi_common.db import Database
from veriditi_common.errors import error_body, install_error_handlers
from veriditi_common.health import build_health_router
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from veriditi_common.security import install_internal_auth

# O maior corpo é o pedido com o faturamento: 16 KiB sobram
MAX_BODY_BYTES: Final = 16 * 1024

_STATUS: Final[dict[type[PaymentError], int]] = {
    PackageNotFoundError: status.HTTP_404_NOT_FOUND,
    OrderNotFoundError: status.HTTP_404_NOT_FOUND,
    IdempotencyKeyReusedError: status.HTTP_409_CONFLICT,
    OrderNotPayableError: status.HTTP_409_CONFLICT,
    ProviderUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _build_provider(settings: Settings) -> PaymentProvider:
    # O provedor real (#23) entra aqui, escolhido por PAYMENT_PROVIDER
    return SandboxPixProvider(
        pix_key=settings.pix_key,
        merchant_name=settings.pix_merchant_name,
        merchant_city=settings.pix_merchant_city,
    )


def create_app(
    settings: Settings | None = None,
    db: Database | None = None,
    audit_logger: AuditLogger | None = None,
    *,
    clock: Clock | None = None,
    provider: PaymentProvider | None = None,
    qr_renderer: QrRenderer | None = None,
) -> FastAPI:
    """App factory para os testes injetarem config, banco, auditoria, relógio e provedor"""
    resolved = settings or get_settings()
    configure_logging(resolved.service_name, level=resolved.log_level)
    token = resolved.internal_token

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db = db or Database(resolved.database_url, echo=resolved.debug)
        app.state.http = httpx.AsyncClient()
        app.state.audit_logger = audit_logger or HttpAuditLogger(
            app.state.http, resolved.monitoring_url, token
        )
        try:
            yield
        finally:
            await app.state.http.aclose()
            await app.state.db.dispose()

    app = FastAPI(title=f"{resolved.service_name} service", lifespan=lifespan)
    app.state.settings = resolved
    app.state.clock = clock or system_clock
    app.state.payment_provider = provider or _build_provider(resolved)
    app.state.qr_renderer = qr_renderer or SegnoQrRenderer()
    install_error_handlers(app)
    install_internal_auth(app, token)

    @app.exception_handler(PaymentError)
    async def handle_payment_error(_request: Request, exc: PaymentError) -> JSONResponse:
        return JSONResponse(
            status_code=_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST),
            content=error_body(exc.code, exc.message),
        )

    app.include_router(build_health_router(get_session))
    app.include_router(packages.router)
    app.include_router(orders.router)
    app.include_router(credits.router)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    # Último add_middleware para envolver toda a pilha e drenar tarefas adiadas no finally
    app.add_middleware(RequestContextMiddleware)
    return app
