import uuid

import pytest
from httpx import AsyncClient

from auth_service.config import Settings
from auth_service.main import create_app
from veriditi_common.audit import HttpAuditLogger, InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import HttpNotifier, InMemoryNotifier


async def test_responses_carry_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health/live")

    assert uuid.UUID(resp.headers["X-Request-ID"]).version == 4


async def test_unknown_route_is_standard_not_found(client: AsyncClient) -> None:
    resp = await client.get("/nao-existe")

    assert resp.status_code == 404
    assert resp.json() == {"detail": {"code": "not_found", "message": "Recurso não encontrado."}}


def test_create_app_requires_internal_token(settings: Settings) -> None:
    with pytest.raises(RuntimeError, match="INTERNAL_API_TOKEN"):
        create_app(settings=settings.model_copy(update={"internal_api_token": None}))


def test_internal_urls_default_to_make_dev_ports(settings: Settings) -> None:
    assert settings.monitoring_url == "http://localhost:8003"
    assert settings.notification_url == "http://localhost:8002"


async def test_lifespan_creates_http_clients_and_closes_them(
    settings: Settings, db: Database
) -> None:
    app = create_app(settings=settings, db=db)

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.audit_logger, HttpAuditLogger)
        assert isinstance(app.state.notifier, HttpNotifier)
        assert not app.state.http.is_closed

    assert app.state.http.is_closed


async def test_injected_clients_are_kept(
    settings: Settings,
    db: Database,
    audit: InMemoryAuditLogger,
    notifier: InMemoryNotifier,
) -> None:
    app = create_app(settings=settings, db=db, audit_logger=audit, notifier=notifier)

    async with app.router.lifespan_context(app):
        assert app.state.audit_logger is audit
        assert app.state.notifier is notifier
