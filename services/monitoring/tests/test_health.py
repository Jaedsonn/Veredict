from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from monitoring_service.config import Settings
from monitoring_service.main import create_app
from monitoring_service.models import Base


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # Host inexistente e sem senha: o ready só passa se não abrir conexão
    settings = Settings(_env_file=None, db_host="nowhere.invalid", db_user="x")  # type: ignore[call-arg]
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200


async def test_ready_does_not_connect_to_database(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_metadata_has_no_tables_yet() -> None:
    assert Base.metadata.tables == {}


def test_database_defaults_to_logs_storage() -> None:
    settings = Settings(_env_file=None, db_user="x", db_password="y")  # type: ignore[call-arg, arg-type]

    assert settings.database_url.endswith("/veriditi_logs?charset=utf8mb4")
