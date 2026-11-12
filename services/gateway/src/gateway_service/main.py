from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from gateway_service.adapters.jwt_verifier import RS256JwtVerifier
from gateway_service.adapters.reverse_proxy import block_cookies, build_http_client
from gateway_service.adapters.token_bucket import InMemoryTokenBucket
from gateway_service.api import proxy
from gateway_service.config import Settings, get_settings
from gateway_service.dependencies import build_gateway, get_http_client
from gateway_service.errors import install_gateway_error_handlers
from gateway_service.health import build_health_router
from gateway_service.ports import RateLimiter
from veriditi_common.errors import install_error_handlers
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import BodySizeLimitMiddleware, RequestContextMiddleware


def create_app(
    settings: Settings | None = None,
    http_client: httpx.AsyncClient | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """App factory para os testes injetarem config, client HTTP e rate limiter"""
    settings = settings or get_settings()
    configure_logging(settings.service_name, level=settings.log_level)
    # Fail-fast: sem token interno ou sem chave pública o gateway não sobe
    _ = settings.internal_token
    verifier = RS256JwtVerifier.from_pem(
        settings.require_jwt_public_key(),
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        leeway_seconds=settings.jwt_leeway_seconds,
    )
    # is None, não "or": um bucket vazio tem len 0 e seria falso
    limiter = rate_limiter if rate_limiter is not None else InMemoryTokenBucket()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own = http_client is None
        client = http_client or build_http_client(settings.upstream_timeout_seconds)
        # Também no client injetado: não guardar cookie é comportamento do gateway
        block_cookies(client)
        app.state.http = client
        app.state.gateway = build_gateway(settings, client, limiter=limiter, verifier=verifier)
        yield
        # Client injetado pertence a quem injetou
        if own:
            await client.aclose()

    # Porta pública: não publica o próprio esquema nem redireciona /api para /api/
    app = FastAPI(
        title=f"{settings.service_name} service",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    install_error_handlers(app)
    install_gateway_error_handlers(app)
    app.include_router(
        build_health_router(get_http_client, settings.upstream_urls, settings.health_timeout_s)
    )
    app.include_router(proxy.router)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    # Sempre o último add_middleware, para ficar por fora do CORS e do limite de corpo
    app.add_middleware(RequestContextMiddleware, trust_request_id=False)
    return app
