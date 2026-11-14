import uuid

import pytest
from httpx import AsyncClient

from gateway_service.config import Settings
from gateway_service.main import create_app

from .conftest import AUTH, TOKEN, RsaKeys

RID = "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"


async def test_generates_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health/live")

    assert uuid.UUID(resp.headers["X-Request-ID"]).version == 4


async def test_client_request_id_is_replaced(client: AsyncClient) -> None:
    resp = await client.get("/health/live", headers={"X-Request-ID": RID})

    assert resp.headers["X-Request-ID"] != RID
    assert uuid.UUID(resp.headers["X-Request-ID"]).version == 4


async def test_unknown_route_is_standard_not_found(client: AsyncClient) -> None:
    resp = await client.get("/nao-existe")

    assert resp.status_code == 404
    assert resp.json() == {"detail": {"code": "not_found", "message": "Recurso não encontrado."}}
    assert "X-Request-ID" in resp.headers


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
async def test_schema_and_docs_are_not_published(client: AsyncClient, path: str) -> None:
    resp = await client.get(path)

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("INTERNAL_API_TOKEN", "JWT_PUBLIC_KEY"):
        monkeypatch.delenv(name, raising=False)


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, auth_url=AUTH, **values)  # type: ignore[arg-type]


def test_fails_fast_without_public_key() -> None:
    with pytest.raises(RuntimeError, match="make keys"):
        create_app(_settings(internal_api_token=TOKEN))


def test_fails_fast_with_invalid_public_key() -> None:
    with pytest.raises(ValueError, match="JWT_PUBLIC_KEY"):
        create_app(_settings(internal_api_token=TOKEN, jwt_public_key="nao-e-pem"))


def test_fails_fast_without_internal_token(rsa_keys: RsaKeys) -> None:
    with pytest.raises(RuntimeError, match="INTERNAL_API_TOKEN"):
        create_app(_settings(jwt_public_key=rsa_keys.public_pem))
