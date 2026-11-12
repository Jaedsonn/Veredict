"""Erro padrão {"detail": {"code", "message", ...}} lido pelo parseApiError da web"""

from collections.abc import Mapping
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException

INTERNAL_ERROR_CODE: Final = "internal_error"
_INTERNAL_ERROR_MESSAGE: Final = "Erro interno. Tente novamente em instantes."

_HTTP_ERRORS: Final[dict[int, tuple[str, str]]] = {
    401: ("unauthorized", "Não autenticado."),
    403: ("forbidden", "Acesso negado."),
    404: ("not_found", "Recurso não encontrado."),
    405: ("method_not_allowed", "Método não permitido."),
}
_DEFAULT_HTTP_ERROR: Final = ("http_error", "Não foi possível concluir a operação.")


def error_body(code: str, message: str, **extras: Any) -> dict[str, Any]:
    return {"detail": {"code": code, "message": message, **jsonable_encoder(extras)}}


class AppError(Exception):
    """Erro de negócio com code estável para a web traduzir e extras como attempts_remaining"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: Mapping[str, str] | None = None,
        **extras: Any,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers: dict[str, str] = dict(headers or {})
        self.extras: dict[str, Any] = extras

    def body(self) -> dict[str, Any]:
        return error_body(self.code, self.message, **self.extras)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Não autenticado.") -> None:
        super().__init__(401, "unauthorized", message)


def internal_error_response() -> JSONResponse:
    return JSONResponse(error_body(INTERNAL_ERROR_CODE, _INTERNAL_ERROR_MESSAGE), status_code=500)


async def _app_error_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, AppError):  # pragma: no cover
        raise exc
    return JSONResponse(exc.body(), status_code=exc.status_code, headers=exc.headers)


async def _http_exception_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        raise exc
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=exc.headers)
    if isinstance(exc.detail, dict):
        body: dict[str, Any] = {"detail": exc.detail}
    else:
        body = error_body(*_HTTP_ERRORS.get(exc.status_code, _DEFAULT_HTTP_ERROR))
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


def install_error_handlers(app: FastAPI) -> None:
    """Normaliza 404/405 e HTTPException; o 422 de validação segue o padrão do FastAPI"""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
