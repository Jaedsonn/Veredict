from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200


async def test_readiness_checks_database(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.json() == {"status": "ok", "database": "up"}


async def test_template_crud_was_removed(client: AsyncClient) -> None:
    assert (await client.get("/users")).status_code == 404
