import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import httpx
from fastapi import FastAPI

from notification_service.adapters.jinja_renderer import JinjaEmailRenderer
from notification_service.adapters.smtp_sender import SmtpEmailSender, message_id_factory
from notification_service.adapters.sqlalchemy_repo import SqlAlchemyNotificationRepository
from notification_service.api import notifications
from notification_service.catalog import build_registry
from notification_service.config import Settings, get_settings
from notification_service.dependencies import get_session
from notification_service.ports import Clock, EmailSender, MessageIdFactory, Sleep
from veriditi_common.audit import AuditLogger, HttpAuditLogger
from veriditi_common.db import Database
from veriditi_common.db_types import utcnow
from veriditi_common.errors import install_error_handlers
from veriditi_common.health import build_health_router
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from veriditi_common.security import install_internal_auth

# O pedido real tem menos de 1 KiB; a folga cobre o data dos templates do #33
MAX_BODY_BYTES: Final = 16 * 1024


def _smtp_sender(settings: Settings) -> SmtpEmailSender:
    """Não conecta ao ser criado: cada envio abre a própria conexão"""
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender_name=settings.smtp_from.name,
        sender_address=settings.smtp_from.email,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=settings.smtp_starttls,
        timeout=settings.smtp_timeout_seconds,
    )


def create_app(
    settings: Settings | None = None,
    *,
    db: Database | None = None,
    audit_logger: AuditLogger | None = None,
    email_sender: EmailSender | None = None,
    clock: Clock | None = None,
    sleep: Sleep | None = None,
    message_ids: MessageIdFactory | None = None,
) -> FastAPI:
    """App factory para os testes injetarem config, banco, SMTP, auditoria e tempo"""
    settings = settings or get_settings()
    configure_logging(settings.service_name, level=settings.log_level)
    # Fail-fast: sem INTERNAL_API_TOKEN o serviço não sobe
    token = settings.internal_token

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db = db or Database(settings.database_url, echo=settings.debug)
        app.state.notifications = SqlAlchemyNotificationRepository(app.state.db.session_factory)
        # Um client por processo: o pool de conexões é reaproveitado entre requests
        app.state.http = httpx.AsyncClient()
        app.state.audit_logger = audit_logger or HttpAuditLogger(
            app.state.http, settings.monitoring_url, token
        )
        yield
        await app.state.http.aclose()
        await app.state.db.dispose()

    app = FastAPI(title=f"{settings.service_name} service", lifespan=lifespan)
    app.state.registry = build_registry()
    app.state.renderer = JinjaEmailRenderer(web_url=settings.web_url)
    # Fail-fast: template registrado sem os 3 arquivos derruba a subida, não o 1º envio
    app.state.renderer.check(app.state.registry.names)
    app.state.email_sender = email_sender or _smtp_sender(settings)
    app.state.clock = clock or utcnow
    app.state.sleep = sleep or asyncio.sleep
    app.state.message_ids = message_ids or message_id_factory(settings.smtp_from_domain)
    install_error_handlers(app)
    install_internal_auth(app, token)
    app.include_router(build_health_router(get_session))
    app.include_router(notifications.router)
    # Dentro do RequestContextMiddleware: o 413 também leva X-Request-ID e entra no log
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    app.add_middleware(RequestContextMiddleware)
    return app
