from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from notification_service.config import Settings
from notification_service.main import create_app
from notification_service.models import Base
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.security import INTERNAL_TOKEN_HEADER

TOKEN = "test-internal-token-0123456789"


@pytest.fixture
def token() -> str:
    return TOKEN


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
def audit() -> InMemoryAuditLogger:
    return InMemoryAuditLogger()


@pytest.fixture
async def app(
    settings: Settings, db: Database, audit: InMemoryAuditLogger
) -> AsyncIterator[FastAPI]:
    application = create_app(settings, db=db, audit_logger=audit)

    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {INTERNAL_TOKEN_HEADER: TOKEN}
