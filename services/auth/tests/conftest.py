from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from auth_service.config import Settings
from auth_service.main import create_app
from auth_service.models import Base
from veriditi_common.db import Database


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    db = Database("sqlite+aiosqlite:///:memory:")
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = Settings(db_user="test", db_password="test", db_name="test")  # type: ignore[arg-type]
    app = create_app(settings=settings, db=db)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
