from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from auth_service.api.users import router as users_router
from auth_service.config import Settings, get_settings
from auth_service.dependencies import get_session
from veriditi_common.db import Database
from veriditi_common.health import build_health_router


def create_app(settings: Settings | None = None, db: Database | None = None) -> FastAPI:
    """App factory: permite criar instâncias com config/banco diferentes (ex.: testes)."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db = db or Database(settings.database_url, echo=settings.debug)
        yield
        await app.state.db.dispose()

    app = FastAPI(title=f"{settings.service_name} service", lifespan=lifespan)
    app.include_router(build_health_router(get_session))
    app.include_router(users_router)
    return app
