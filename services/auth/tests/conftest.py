from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from auth_service.config import Settings
from auth_service.main import create_app
from auth_service.models import Base
from veriditi_common.db import Database


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
async def client(db: Database) -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, db_user="test", db_password="test")  # type: ignore[call-arg, arg-type]
    app = create_app(settings=settings, db=db)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
