import uuid
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, model_validator

from veriditi_common.errors import (
    INTERNAL_ERROR_CODE,
    AppError,
    UnauthorizedError,
    install_error_handlers,
    internal_error_response,
)

REF = uuid.UUID("3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55")


class Payload(BaseModel):
    email: str
    password: str = ""
    age: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _no_same(self) -> "Payload":
        if self.password and self.password == self.email:
            raise ValueError("senha igual ao e-mail")
        return self


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/code")
    async def invalid_code() -> None:
        raise AppError(400, "invalid_code", "Código incorreto.", attempts_remaining=3)

    @app.get("/limited")
    async def limited() -> None:
        raise AppError(
            429, "too_many_requests", "Muitas tentativas.", headers={"Retry-After": "30"}
        )

    @app.get("/typed-extras")
    async def typed_extras() -> None:
        raise AppError(
            409, "conflict", "Conflito.", ref=REF, at=datetime(2026, 1, 1, 12, tzinfo=UTC)
        )

    @app.get("/unauthorized")
    async def unauthorized() -> None:
        raise UnauthorizedError()

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise HTTPException(403)

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(418)

    @app.get("/dict-detail")
    async def dict_detail() -> None:
        raise HTTPException(
            403,
            detail={"code": "email_not_verified", "message": "Confirme."},
            headers={"X-Extra": "1"},
        )

    @app.get("/no-body")
    async def no_body() -> None:
        raise HTTPException(304)

    @app.post("/items")
    async def create(payload: Payload) -> Payload:
        return payload

    return app


async def _call(method: str, path: str, **kwargs: object) -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)  # type: ignore[arg-type]


async def test_app_error_body_has_code_message_and_extras() -> None:
    resp = await _call("GET", "/code")

    assert resp.status_code == 400
    assert resp.json() == {
        "detail": {"code": "invalid_code", "message": "Código incorreto.", "attempts_remaining": 3}
    }


async def test_app_error_keeps_retry_after_header() -> None:
    resp = await _call("GET", "/limited")

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "30"
    assert resp.json()["detail"]["code"] == "too_many_requests"


async def test_extras_are_json_encoded() -> None:
    resp = await _call("GET", "/typed-extras")

    assert resp.json()["detail"]["ref"] == str(REF)
    assert datetime.fromisoformat(resp.json()["detail"]["at"]) == datetime(
        2026, 1, 1, 12, tzinfo=UTC
    )


async def test_unauthorized_error() -> None:
    resp = await _call("GET", "/unauthorized")

    assert resp.status_code == 401
    assert resp.json() == {"detail": {"code": "unauthorized", "message": "Não autenticado."}}


async def test_unknown_route_is_standard_not_found() -> None:
    resp = await _call("GET", "/nao-existe")

    assert resp.status_code == 404
    assert resp.json() == {"detail": {"code": "not_found", "message": "Recurso não encontrado."}}


async def test_wrong_method_is_method_not_allowed_and_keeps_allow() -> None:
    resp = await _call("DELETE", "/code")

    assert resp.status_code == 405
    assert resp.json()["detail"]["code"] == "method_not_allowed"
    assert "GET" in resp.headers["Allow"]


async def test_http_exception_is_mapped_by_status() -> None:
    forbidden = await _call("GET", "/forbidden")
    teapot = await _call("GET", "/teapot")

    assert forbidden.json() == {"detail": {"code": "forbidden", "message": "Acesso negado."}}
    assert teapot.status_code == 418
    assert teapot.json()["detail"]["code"] == "http_error"


async def test_http_exception_with_dict_detail_passes_through_with_headers() -> None:
    resp = await _call("GET", "/dict-detail")

    assert resp.status_code == 403
    assert resp.json() == {"detail": {"code": "email_not_verified", "message": "Confirme."}}
    assert resp.headers["X-Extra"] == "1"


async def test_status_without_body_stays_empty() -> None:
    resp = await _call("GET", "/no-body")

    assert resp.status_code == 304
    assert resp.content == b""


async def test_validation_error_keeps_fastapi_format() -> None:
    resp = await _call("POST", "/items", json={})

    assert resp.status_code == 422
    [item] = resp.json()["detail"]
    assert {"loc", "msg", "type"} <= item.keys()
    assert item["loc"] == ["body", "email"]


async def test_validation_error_does_not_echo_input_or_ctx() -> None:
    body = {"password": "s3cr3t-echo", "age": -1}

    resp = await _call("POST", "/items", json=body)

    assert resp.status_code == 422
    assert "s3cr3t-echo" not in resp.text
    assert {tuple(item["loc"]) for item in resp.json()["detail"]} == {
        ("body", "email"),
        ("body", "age"),
    }
    for item in resp.json()["detail"]:
        assert set(item) == {"type", "loc", "msg"}


async def test_model_validator_error_does_not_echo_the_body() -> None:
    body = {"email": "s3cr3t-echo", "password": "s3cr3t-echo"}

    resp = await _call("POST", "/items", json=body)

    assert resp.status_code == 422
    assert "s3cr3t-echo" not in resp.text
    assert resp.json()["detail"][0]["loc"] == ["body"]


async def test_malformed_json_does_not_echo_the_body() -> None:
    resp = await _call(
        "POST",
        "/items",
        content=b'{"password": "s3cr3t-echo"',
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 422
    assert "s3cr3t-echo" not in resp.text


def test_internal_error_response() -> None:
    resp = internal_error_response()

    assert resp.status_code == 500
    assert resp.body.startswith(b'{"detail":{"code":"' + INTERNAL_ERROR_CODE.encode())
