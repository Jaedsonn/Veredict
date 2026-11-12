import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from notification_service.config import Settings
from notification_service.main import create_app
from notification_service.models import Base
from veriditi_common.audit import HttpAuditLogger, InMemoryAuditLogger
from veriditi_common.db import Database


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200


async def test_readiness_checks_database(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "up"}


async def test_readiness_reports_database_down(settings: Settings) -> None:
    broken = Database("sqlite+aiosqlite:////nao-existe/dir/x.db")
    app = create_app(settings, db=broken, audit_logger=InMemoryAuditLogger())

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac,
    ):
        resp = await ac.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable", "database": "down"}


def test_database_defaults_to_central_storage(settings: Settings) -> None:
    assert settings.database_url.endswith("/veriditi?charset=utf8mb4")


def test_metadata_only_has_notifications_sent() -> None:
    assert set(Base.metadata.tables) == {"notifications_sent"}


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
        create_app(without_token)


def test_monitoring_url_defaults_to_make_dev_port(settings: Settings) -> None:
    assert settings.monitoring_url == "http://localhost:8003"


async def test_lifespan_creates_database_and_http_audit_logger(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"monitoring_url": "http://monitoring.test"}))

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.db, Database)
        assert isinstance(app.state.audit_logger, HttpAuditLogger)
        assert not app.state.http.is_closed

    assert app.state.http.is_closed


async def test_injected_audit_logger_and_database_are_kept(
    settings: Settings, db: Database
) -> None:
    audit = InMemoryAuditLogger()
    app = create_app(settings, db=db, audit_logger=audit)

    async with app.router.lifespan_context(app):
        assert app.state.audit_logger is audit
        assert app.state.db is db
