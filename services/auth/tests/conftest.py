from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from auth_service.config import Settings
from auth_service.main import create_app
from auth_service.models import Base
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import InMemoryNotifier

TOKEN = "test-internal-token-0123456789"


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
def notifier() -> InMemoryNotifier:
    return InMemoryNotifier()


@pytest.fixture
async def client(
    settings: Settings, db: Database, audit: InMemoryAuditLogger, notifier: InMemoryNotifier
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings=settings, db=db, audit_logger=audit, notifier=notifier)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
