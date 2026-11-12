from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request

from gateway_service.config import Settings, get_settings
from gateway_service.health import build_health_router
from veriditi_common.errors import install_error_handlers
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import RequestContextMiddleware


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Um client por processo (pool de conexões), criado no lifespan"""
    client: httpx.AsyncClient = request.app.state.http
    return client


def create_app(
    settings: Settings | None = None, http_client: httpx.AsyncClient | None = None
) -> FastAPI:
    """App factory para os testes injetarem config e client HTTP"""
    settings = settings or get_settings()
    configure_logging(settings.service_name, level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own = http_client is None
        app.state.http = http_client or httpx.AsyncClient(timeout=settings.health_timeout_s)
        yield
        # Client injetado pertence a quem injetou
        if own:
            await app.state.http.aclose()

    app = FastAPI(title=f"{settings.service_name} service", lifespan=lifespan)
    install_error_handlers(app)
    app.include_router(
        build_health_router(get_http_client, settings.upstream_urls, settings.health_timeout_s)
    )
    # Sempre o último add_middleware, para ficar por fora do CORS do #11
    app.add_middleware(RequestContextMiddleware)
    return app
