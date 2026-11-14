from fastapi import FastAPI

from notification_service.config import Settings, get_settings
from veriditi_common.health import build_health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory para os testes injetarem config"""
    settings = settings or get_settings()

    app = FastAPI(title=f"{settings.service_name} service")
    # Sem sessão até o #6: o usuário de runtime sem GRANT não conecta (1044)
    app.include_router(build_health_router())
    return app
