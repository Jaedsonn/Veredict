from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from notification_service.config import Settings, get_settings
from notification_service.dependencies import get_session
from veriditi_common.audit import AuditLogger, HttpAuditLogger
from veriditi_common.db import Database
from veriditi_common.errors import install_error_handlers
from veriditi_common.health import build_health_router
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import RequestContextMiddleware
from veriditi_common.security import install_internal_auth


def create_app(
    settings: Settings | None = None,
    *,
    db: Database | None = None,
    audit_logger: AuditLogger | None = None,
) -> FastAPI:
    """App factory para os testes injetarem config, banco e auditoria"""
    settings = settings or get_settings()
    configure_logging(settings.service_name, level=settings.log_level)
    # Fail-fast: sem INTERNAL_API_TOKEN o serviço não sobe
    token = settings.internal_token

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db = db or Database(settings.database_url, echo=settings.debug)
        # Um client por processo: o pool de conexões é reaproveitado entre requests
        app.state.http = httpx.AsyncClient()
        app.state.audit_logger = audit_logger or HttpAuditLogger(
            app.state.http, settings.monitoring_url, token
        )
        yield
        await app.state.http.aclose()
        await app.state.db.dispose()

    app = FastAPI(title=f"{settings.service_name} service", lifespan=lifespan)
    install_error_handlers(app)
    install_internal_auth(app, token)
    app.include_router(build_health_router(get_session))
    app.add_middleware(RequestContextMiddleware)
    return app
