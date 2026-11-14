from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from monitoring_service.config import Settings
from monitoring_service.main import create_app
from monitoring_service.models import Base
from veriditi_common.audit import AuditEvent
from veriditi_common.db import Database
from veriditi_common.security import INTERNAL_TOKEN_HEADER

TOKEN = "test-internal-token-0123456789"
RECEIVED_AT = datetime(2026, 11, 12, 15, 0, 0, 654321, tzinfo=UTC)

EventFactory = Callable[..., dict[str, Any]]


@pytest.fixture
def token() -> str:
    return TOKEN


@pytest.fixture
def received_at() -> datetime:
    return RECEIVED_AT


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        db_user="test",
        db_password="test",  # type: ignore[arg-type]
        internal_api_token=TOKEN,  # type: ignore[arg-type]
    )


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
async def app(settings: Settings, db: Database) -> AsyncIterator[FastAPI]:
    application = create_app(settings=settings, db=db, clock=lambda: RECEIVED_AT)

    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {INTERNAL_TOKEN_HEADER: TOKEN}


@pytest.fixture
def make_event() -> EventFactory:
    """Corpo JSON como o HttpAuditLogger o envia, com request_id explícito"""

    def factory(**overrides: Any) -> dict[str, Any]:
        values: dict[str, Any] = {
            "service": "auth",
            "action": "auth.user.registered",
            "outcome": "success",
            "request_id": None,
        }
        values.update(overrides)
        return AuditEvent(**values).model_dump(mode="json")

    return factory
