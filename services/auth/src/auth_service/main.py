"""App factory e mapeamento centralizado de exceções de domínio para HTTP"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from auth_service.adapters.clock import SystemClock
from auth_service.adapters.password_hasher import Argon2PasswordHasher
from auth_service.adapters.token_issuer import PyJwtTokenIssuer
from auth_service.api.auth import router as auth_router
from auth_service.api.profile import router as profile_router
from auth_service.config import Settings, get_settings
from auth_service.dependencies import get_session
from auth_service.domain.errors import (
    AccountBlockedError,
    DomainError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    InvalidRefreshTokenError,
    InvalidVerificationCodeError,
    RefreshTokenReuseDetectedError,
    UserNotFoundError,
    VerificationCodeExpiredError,
    VerificationCodeTooManyAttemptsError,
    WeakPasswordError,
)
from auth_service.domain.password_policy import PasswordPolicy
from auth_service.ports import Clock, PasswordHasher, TokenIssuer
from veriditi_common.audit import AuditLogger, HttpAuditLogger
from veriditi_common.db import Database
from veriditi_common.errors import install_error_handlers
from veriditi_common.health import build_health_router
from veriditi_common.logging import configure_logging
from veriditi_common.middleware import RequestContextMiddleware
from veriditi_common.notifications import HttpNotifier, Notifier
from veriditi_common.security import install_internal_auth


def _register_exception_handlers(app: FastAPI) -> None:
    """Converte erros de domínio puros em respostas HTTP padronizadas"""

    @app.exception_handler(EmailAlreadyRegisteredError)
    async def handle_email_conflict(
        _request: Request, exc: EmailAlreadyRegisteredError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(WeakPasswordError)
    async def handle_validation_domain_error(
        _request: Request, exc: WeakPasswordError
    ) -> JSONResponse:
        field = exc.field or "password"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": [
                    {
                        "loc": ["body", field],
                        "msg": exc.message,
                        "type": "value_error",
                    }
                ]
            },
        )

    @app.exception_handler(InvalidVerificationCodeError)
    async def handle_invalid_code(
        _request: Request, exc: InvalidVerificationCodeError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": {
                    "code": exc.code,
                    "message": exc.message,
                    "attempts_remaining": exc.attempts_remaining,
                }
            },
        )

    @app.exception_handler(VerificationCodeExpiredError)
    @app.exception_handler(VerificationCodeTooManyAttemptsError)
    @app.exception_handler(InvalidCurrentPasswordError)
    async def handle_bad_request_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(InvalidCredentialsError)
    @app.exception_handler(InvalidRefreshTokenError)
    @app.exception_handler(RefreshTokenReuseDetectedError)
    async def handle_unauthorized_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(EmailNotVerifiedError)
    @app.exception_handler(AccountBlockedError)
    async def handle_forbidden_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "code": exc.code,
                "detail": {"code": exc.code, "message": exc.message},
            },
        )

    @app.exception_handler(UserNotFoundError)
    async def handle_not_found(_request: Request, exc: UserNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )


def create_app(
    settings: Settings | None = None,
    db: Database | None = None,
    audit_logger: AuditLogger | None = None,
    notifier: Notifier | None = None,
    *,
    clock: Clock | None = None,
    password_hasher: PasswordHasher | None = None,
    token_issuer: TokenIssuer | None = None,
) -> FastAPI:
    """App factory do serviço de Autenticação (`auth-service`)"""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.service_name, level=resolved_settings.log_level)

    # Fail-fast: valida segredos obrigatórios antes de aceitar tráfego
    token = resolved_settings.internal_token
    _ = resolved_settings.pepper
    resolved_token_issuer = token_issuer or PyJwtTokenIssuer(
        private_key_pem=resolved_settings.resolved_jwt_private_key(),
        public_key_pem=resolved_settings.resolved_jwt_public_key(),
        issuer=resolved_settings.jwt_issuer,
        audience=resolved_settings.jwt_audience,
        access_ttl_seconds=resolved_settings.access_token_ttl_seconds,
        refresh_ttl_days=resolved_settings.refresh_token_ttl_days,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.db = db or Database(resolved_settings.database_url, echo=resolved_settings.debug)
        app.state.clock = clock or SystemClock()
        app.state.password_policy = PasswordPolicy()
        app.state.password_hasher = password_hasher or Argon2PasswordHasher()
        app.state.token_issuer = resolved_token_issuer

        app.state.http = httpx.AsyncClient()
        app.state.audit_logger = audit_logger or HttpAuditLogger(
            app.state.http, resolved_settings.monitoring_url, token
        )
        app.state.notifier = notifier or HttpNotifier(
            app.state.http, resolved_settings.notification_url, token
        )
        try:
            yield
        finally:
            await app.state.http.aclose()
            await app.state.db.dispose()

    app = FastAPI(title=f"{resolved_settings.service_name} service", lifespan=lifespan)
    install_error_handlers(app)
    install_internal_auth(app, token)
    _register_exception_handlers(app)
    app.include_router(build_health_router(get_session))
    app.include_router(auth_router)
    app.include_router(profile_router)
    # Último add_middleware para envolver toda a pilha e drenar tarefas adiadas no finally
    app.add_middleware(RequestContextMiddleware)
    return app
