from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def build_health_router(get_session: Callable[..., Any] | None = None) -> APIRouter:
    """Rotas /health/live (processo de pé) e /health/ready (consegue atender) para o orquestrador"""
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    if get_session is None:

        @router.get("/ready")
        async def ready_without_db() -> dict[str, str]:
            """O serviço ainda sem tabela não tem GRANT e não conectaria (1044)"""
            return {"status": "ok"}

        return router

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
