import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from notification_service.config import Settings
from notification_service.main import create_app
from notification_service.models import Base
from veriditi_common.audit import HttpAuditLogger, InMemoryAuditLogger

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
    app = create_app(settings=_settings(), audit_logger=InMemoryAuditLogger())

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


def test_monitoring_url_defaults_to_make_dev_port() -> None:
    assert _settings().monitoring_url == "http://localhost:8003"


async def test_lifespan_creates_http_audit_logger_and_closes_client() -> None:
    app = create_app(settings=_settings(monitoring_url="http://monitoring.test"))

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.audit_logger, HttpAuditLogger)
        assert not app.state.http.is_closed

    assert app.state.http.is_closed


async def test_injected_audit_logger_is_kept() -> None:
    audit = InMemoryAuditLogger()
    app = create_app(settings=_settings(), audit_logger=audit)

    async with app.router.lifespan_context(app):
        assert app.state.audit_logger is audit
