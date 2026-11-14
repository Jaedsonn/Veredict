import uuid

import pytest
from httpx import AsyncClient

from monitoring_service.config import Settings
from monitoring_service.main import create_app


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200


async def test_readiness_checks_database(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "up"}


def test_database_defaults_to_logs_storage(settings: Settings) -> None:
    assert settings.database_url.endswith("/veriditi_logs?charset=utf8mb4")


async def test_responses_carry_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health/live")

    assert uuid.UUID(resp.headers["X-Request-ID"]).version == 4


async def test_unknown_route_is_standard_not_found(client: AsyncClient) -> None:
    resp = await client.get("/nao-existe")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


def test_create_app_requires_internal_token(settings: Settings) -> None:
    without_token = settings.model_copy(update={"internal_api_token": None})

    with pytest.raises(RuntimeError, match="INTERNAL_API_TOKEN"):
        create_app(settings=without_token)
