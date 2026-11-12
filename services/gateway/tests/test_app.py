import uuid

from httpx import AsyncClient

RID = "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"


async def test_generates_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health/live")

    assert uuid.UUID(resp.headers["X-Request-ID"]).version == 4


async def test_echoes_valid_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health/live", headers={"X-Request-ID": RID})

    assert resp.headers["X-Request-ID"] == RID


async def test_unknown_route_is_standard_not_found(client: AsyncClient) -> None:
    resp = await client.get("/nao-existe")

    assert resp.status_code == 404
    assert resp.json() == {"detail": {"code": "not_found", "message": "Recurso não encontrado."}}
    assert "X-Request-ID" in resp.headers
