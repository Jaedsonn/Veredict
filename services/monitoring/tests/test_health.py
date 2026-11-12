import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from monitoring_service.config import Settings
from monitoring_service.main import create_app

TOKEN = "test-internal-token-0123456789"


def _settings(**overrides: object) -> Settings:
    # Host inexistente e sem senha: o ready só passa se não abrir conexão
    values: dict[str, object] = {
        "db_host": "nowhere.invalid",
        "db_user": "x",
        "internal_api_token": TOKEN,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(settings=_settings())

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


def test_database_defaults_to_logs_storage() -> None:
    settings = Settings(_env_file=None, db_user="x", db_password="y")  # type: ignore[call-arg, arg-type]

    assert settings.database_url.endswith("/veriditi_logs?charset=utf8mb4")


async def test_responses_carry_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health/live")

    assert uuid.UUID(resp.headers["X-Request-ID"]).version == 4


async def test_unknown_route_is_standard_not_found(client: AsyncClient) -> None:
    resp = await client.get("/nao-existe")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


def test_create_app_requires_internal_token() -> None:
    with pytest.raises(RuntimeError, match="INTERNAL_API_TOKEN"):
        create_app(settings=_settings(internal_api_token=None))
