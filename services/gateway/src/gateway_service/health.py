import asyncio
from collections.abc import Callable
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, Response, status


def build_health_router(
    get_client: Callable[[Request], httpx.AsyncClient], upstreams: dict[str, str]
) -> APIRouter:
    """Ready agregado no formato do apps/web/mock/gateway.mjs"""
    router = APIRouter(prefix="/health", tags=["health"])

    async def probe(client: httpx.AsyncClient, base_url: str) -> str:
        try:
            resp = await client.get(f"{base_url.rstrip('/')}/health/ready")
        except httpx.HTTPError:
            return "down"
        return "up" if resp.is_success else "down"

    @router.get("/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    async def ready(
        response: Response, client: Annotated[httpx.AsyncClient, Depends(get_client)]
    ) -> dict[str, object]:
        results = await asyncio.gather(*(probe(client, url) for url in upstreams.values()))
        services = dict(zip(upstreams, results, strict=True))
        if all(state == "up" for state in results):
            return {"status": "ok", "services": services}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "services": services}

    return router
