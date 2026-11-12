from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from monitoring_service.api import events
from monitoring_service.config import Settings, get_settings
from monitoring_service.dependencies import get_session
from monitoring_service.ports import Clock, system_clock
from veriditi_common.db import Database
from veriditi_common.errors import install_error_handlers
from veriditi_common.health import build_health_router
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import RequestContextMiddleware
from veriditi_common.security import install_internal_auth


def create_app(
    settings: Settings | None = None,
    db: Database | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """App factory para os testes injetarem config, banco e relógio"""
    settings = settings or get_settings()
    configure_logging(settings.service_name, level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db = db or Database(settings.database_url, echo=settings.debug)
        yield
        await app.state.db.dispose()

    app = FastAPI(title=f"{settings.service_name} service", lifespan=lifespan)
    app.state.clock = clock or system_clock
    install_error_handlers(app)
    # Fail-fast: sem INTERNAL_API_TOKEN o serviço não sobe
    install_internal_auth(app, settings.internal_token)
    app.include_router(build_health_router(get_session))
    app.include_router(events.router)
    app.add_middleware(RequestContextMiddleware)
    return app
