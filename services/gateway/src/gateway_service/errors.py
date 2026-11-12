"""Erros do gateway no formato padrão {"detail": {code, message, ...}} da web"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from gateway_service.domain import (
    InvalidTokenError,
    RateLimitExceededError,
    UpstreamAuthRejectedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from veriditi_common.errors import UnauthorizedError, error_body


async def _invalid_token(request: Request, exc: Exception) -> Response:
    error = UnauthorizedError()
    return JSONResponse(error.body(), status_code=401, headers={"WWW-Authenticate": "Bearer"})


async def _rate_limited(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RateLimitExceededError):  # pragma: no cover
        raise exc
    seconds = exc.retry_after
    unit = "segundo" if seconds == 1 else "segundos"
    body = error_body(
        "rate_limited",
        f"Muitas tentativas. Tente novamente em {seconds} {unit}.",
        retry_after=seconds,
    )
    return JSONResponse(body, status_code=429, headers={"Retry-After": str(seconds)})


async def _upstream_unavailable(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, UpstreamUnavailableError):  # pragma: no cover
        raise exc
    upstream = exc.upstream
    body = error_body(
        "upstream_unavailable", f"Serviço de {upstream.label} indisponível.", service=upstream.name
    )
    return JSONResponse(body, status_code=503)


async def _upstream_timeout(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, UpstreamTimeoutError):  # pragma: no cover
        raise exc
    upstream = exc.upstream
    body = error_body(
        "upstream_timeout",
        f"O serviço de {upstream.label} demorou para responder. Tente novamente.",
        service=upstream.name,
    )
    return JSONResponse(body, status_code=504)


async def _upstream_auth_rejected(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, UpstreamAuthRejectedError):  # pragma: no cover
        raise exc
    upstream = exc.upstream
    body = error_body(
        "upstream_auth_failed",
        f"Falha na comunicação interna com o serviço de {upstream.label}. "
        "Tente novamente em instantes.",
        service=upstream.name,
    )
    return JSONResponse(body, status_code=502)


def install_gateway_error_handlers(app: FastAPI) -> None:
    """Os logs saem onde o erro nasce; aqui só a tradução para HTTP"""
    app.add_exception_handler(InvalidTokenError, _invalid_token)
    app.add_exception_handler(RateLimitExceededError, _rate_limited)
    app.add_exception_handler(UpstreamUnavailableError, _upstream_unavailable)
    app.add_exception_handler(UpstreamTimeoutError, _upstream_timeout)
    app.add_exception_handler(UpstreamAuthRejectedError, _upstream_auth_rejected)
