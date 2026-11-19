import httpx
import respx
from httpx import AsyncClient

AUTH_READY = "http://auth.test/health/ready"
PAYMENT_READY = "http://payment.test/health/ready"


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200


@respx.mock
async def test_ready_when_auth_is_up(client: AsyncClient) -> None:
    respx.get(AUTH_READY).respond(200, json={"status": "ok", "database": "up"})
    respx.get(PAYMENT_READY).respond(200)

    resp = await client.get("/health/ready")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "services": {"auth": "up", "payment": "up"}}


@respx.mock
async def test_ready_is_503_when_auth_is_unavailable(client: AsyncClient) -> None:
    respx.get(AUTH_READY).respond(503, json={"status": "unavailable"})
    respx.get(PAYMENT_READY).respond(200)

    resp = await client.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable", "services": {"auth": "down", "payment": "up"}}


@respx.mock
async def test_ready_is_503_when_auth_is_unreachable(client: AsyncClient) -> None:
    respx.get(AUTH_READY).mock(side_effect=httpx.ConnectError("recusado"))
    respx.get(PAYMENT_READY).respond(200)

    resp = await client.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json()["services"] == {"auth": "down", "payment": "up"}


@respx.mock
async def test_ready_aggregates_auth_and_payment(client: AsyncClient) -> None:
    respx.get(AUTH_READY).respond(200)
    respx.get(PAYMENT_READY).respond(200)

    resp = await client.get("/health/ready")

    assert set(resp.json()["services"]) == {"auth", "payment"}


@respx.mock
async def test_probe_uses_health_timeout(client: AsyncClient) -> None:
    route = respx.get(AUTH_READY).respond(200)
    respx.get(PAYMENT_READY).respond(200)

    await client.get("/health/ready")

    assert route.calls.last.request.extensions["timeout"]["read"] == 2.0


@respx.mock
async def test_ready_is_503_when_probe_times_out(client: AsyncClient) -> None:
    respx.get(AUTH_READY).mock(side_effect=httpx.ReadTimeout("lento"))
    respx.get(PAYMENT_READY).respond(200)

    resp = await client.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json()["services"] == {"auth": "down", "payment": "up"}


@respx.mock
async def test_ready_is_503_when_payment_is_down(client: AsyncClient) -> None:
    respx.get(AUTH_READY).respond(200)
    respx.get(PAYMENT_READY).mock(side_effect=httpx.ConnectError("recusado"))

    resp = await client.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable", "services": {"auth": "up", "payment": "down"}}
