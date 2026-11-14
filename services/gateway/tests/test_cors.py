import respx
from httpx import AsyncClient

WEB = "http://web.test"
EVIL = "http://evil.test"


def _preflight(origin: str) -> dict[str, str]:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization, content-type",
    }


async def test_preflight_from_web_origin(client: AsyncClient, auth_mock: respx.MockRouter) -> None:
    resp = await client.options("/api/me", headers=_preflight(WEB))

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == WEB
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in resp.headers
    assert resp.headers["access-control-max-age"] == "600"
    assert "X-Request-ID" in resp.headers
    assert not auth_mock.calls


async def test_preflight_from_other_origin_is_refused(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    resp = await client.options("/api/me", headers=_preflight(EVIL))

    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers
    assert not auth_mock.calls


async def test_simple_request_from_web_origin_exposes_headers(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    auth_mock.post("/auth/refresh").respond(200, json={})

    resp = await client.post("/api/auth/refresh", json={}, headers={"Origin": WEB})

    assert resp.headers["access-control-allow-origin"] == WEB
    exposed = resp.headers["access-control-expose-headers"].lower()
    assert "retry-after" in exposed
    assert "x-request-id" in exposed


async def test_simple_request_from_other_origin_has_no_cors(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    auth_mock.post("/auth/refresh").respond(200, json={})

    resp = await client.post("/api/auth/refresh", json={}, headers={"Origin": EVIL})

    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


async def test_gateway_errors_also_carry_cors(
    client: AsyncClient, auth_mock: respx.MockRouter
) -> None:
    auth_mock.post("/auth/register").respond(201, json={})
    for _ in range(10):
        await client.post("/api/auth/register", json={})

    limited = await client.post("/api/auth/register", json={}, headers={"Origin": WEB})
    unauthorized = await client.get("/api/me", headers={"Origin": WEB})

    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == WEB
    assert unauthorized.status_code == 401
    assert unauthorized.headers["access-control-allow-origin"] == WEB


async def test_body_too_large_carries_cors(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/me/password", content=b"x" * (1024 * 1024 + 1), headers={"Origin": WEB}
    )

    assert resp.status_code == 413
    assert resp.headers["access-control-allow-origin"] == WEB
    assert "X-Request-ID" in resp.headers
