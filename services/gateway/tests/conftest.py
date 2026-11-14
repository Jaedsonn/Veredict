from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from gateway_service.config import Settings
from gateway_service.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, auth_url="http://auth.test")  # type: ignore[call-arg]
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
