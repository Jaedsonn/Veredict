from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200


async def test_readiness_checks_database(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.json() == {"status": "ok", "database": "up"}


async def test_create_and_get_user(client: AsyncClient) -> None:
    created = await client.post("/users", json={"email": "ana@example.com", "name": "Ana"})
    assert created.status_code == 201
    user_id = created.json()["id"]

    fetched = await client.get(f"/users/{user_id}")
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "ana@example.com"


async def test_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {"email": "dup@example.com", "name": "Dup"}
    assert (await client.post("/users", json=payload)).status_code == 201
    assert (await client.post("/users", json=payload)).status_code == 409


async def test_unknown_user_returns_404(client: AsyncClient) -> None:
    assert (await client.get("/users/999")).status_code == 404


async def test_invalid_email_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/users", json={"email": "not-an-email", "name": "X"})
    assert resp.status_code == 422
