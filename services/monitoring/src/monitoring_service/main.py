from fastapi import FastAPI

from monitoring_service.config import Settings, get_settings
from veriditi_common.errors import install_error_handlers
from veriditi_common.health import build_health_router
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import RequestContextMiddleware
from veriditi_common.security import install_internal_auth


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory para os testes injetarem config"""
    settings = settings or get_settings()
    configure_logging(settings.service_name, level=settings.log_level)

    app = FastAPI(title=f"{settings.service_name} service")
    install_error_handlers(app)
    # Fail-fast: sem INTERNAL_API_TOKEN o serviço não sobe
    install_internal_auth(app, settings.internal_token)
    # Sem sessão até o #5: o usuário de runtime sem GRANT não conecta (1044)
    app.include_router(build_health_router())
    app.add_middleware(RequestContextMiddleware)
    return app
