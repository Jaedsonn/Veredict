from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def build_health_router(get_session: Callable[..., Any]) -> APIRouter:
    """Cria rotas padrão de saúde para orquestradores (Docker, Kubernetes).

    - /health/live  -> o processo está de pé? (não toca dependências)
    - /health/ready -> consegue atender? (verifica o banco)
    """
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    async def ready(
        response: Response,
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> dict[str, str]:
        try:
            await session.execute(text("SELECT 1"))
        except Exception:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "unavailable", "database": "down"}
        return {"status": "ok", "database": "up"}

    return router
