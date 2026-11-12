"""Composition Root do serviço de Autenticação (Dependency Inversion Principle — DIP).

Monta os casos de uso injetando implementações concretas (`adapters`) nas portas
abstratas (`ports`). Os testes podem substituir qualquer dependência via
`app.state` ou `app.dependency_overrides` sem alterar uma única linha de regra de negócio.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.adapters.clock import SystemClock
from auth_service.adapters.password_hasher import Argon2PasswordHasher
from auth_service.adapters.repositories import (
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyVerificationCodeRepository,
)
from auth_service.adapters.token_issuer import PyJwtTokenIssuer
from auth_service.config import Settings
from auth_service.domain.entities import RequestContext
from auth_service.domain.password_policy import PasswordPolicy
from auth_service.domain.verification_code import VerificationCodeService
from auth_service.ports import (
    Clock,
    PasswordHasher,
    RefreshTokenRepository,
    TokenIssuer,
    UserRepository,
    VerificationCodeRepository,
)
from auth_service.use_cases import (
    AuthenticateUser,
    ChangePassword,
    GetProfile,
    LogoutUser,
    RefreshSession,
    RegisterUser,
    ResendVerificationCode,
    UpdateProfile,
    VerifyEmail,
)
from veriditi_common.audit import AuditLoggerDep, get_audit_logger
from veriditi_common.middleware import client_ip, current_request_id
from veriditi_common.notifications import NotifierDep, get_notifier
from veriditi_common.security import CurrentUserDep, get_current_user


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """O Database vive em app.state (criado no lifespan) para os testes poderem trocá-lo."""
    async for session in request.app.state.db.session():
        yield session


def get_clock(request: Request) -> Clock:
    clock: Clock | None = getattr(request.app.state, "clock", None)
    return clock if clock is not None else SystemClock()


def get_password_hasher(request: Request) -> PasswordHasher:
    hasher: PasswordHasher = request.app.state.password_hasher
    return hasher


def get_password_policy(request: Request) -> PasswordPolicy:
    policy: PasswordPolicy | None = getattr(request.app.state, "password_policy", None)
    return policy if policy is not None else PasswordPolicy()


def get_verification_code_service(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> VerificationCodeService:
    return VerificationCodeService(
        pepper=settings.pepper,
        ttl_minutes=settings.verification_code_ttl_minutes,
        max_attempts=settings.verification_max_attempts,
    )


def get_token_issuer(request: Request) -> TokenIssuer:
    issuer: TokenIssuer = request.app.state.token_issuer
    return issuer


def get_request_context(request: Request) -> RequestContext:
    raw_ua = request.headers.get("user-agent")
    user_agent = raw_ua.strip()[:255] if raw_ua and raw_ua.strip() else None
    return RequestContext(
        request_id=current_request_id(),
        actor_ip=client_ip(request),
        user_agent=user_agent,
    )


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ClockDep = Annotated[Clock, Depends(get_clock)]
PasswordHasherDep = Annotated[PasswordHasher, Depends(get_password_hasher)]
PasswordPolicyDep = Annotated[PasswordPolicy, Depends(get_password_policy)]
CodeServiceDep = Annotated[VerificationCodeService, Depends(get_verification_code_service)]
TokenIssuerDep = Annotated[TokenIssuer, Depends(get_token_issuer)]
RequestContextDep = Annotated[RequestContext, Depends(get_request_context)]


def get_user_repository(session: SessionDep) -> UserRepository:
    return SqlAlchemyUserRepository(session)


def get_verification_code_repository(session: SessionDep) -> VerificationCodeRepository:
    return SqlAlchemyVerificationCodeRepository(session)


def get_refresh_token_repository(session: SessionDep) -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(session)


UserRepoDep = Annotated[UserRepository, Depends(get_user_repository)]
CodeRepoDep = Annotated[VerificationCodeRepository, Depends(get_verification_code_repository)]
RefreshRepoDep = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]


def get_register_user_use_case(
    users: UserRepoDep,
    codes: CodeRepoDep,
    hasher: PasswordHasherDep,
    code_service: CodeServiceDep,
    password_policy: PasswordPolicyDep,
    notifier: NotifierDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
) -> RegisterUser:
    return RegisterUser(
        users=users,
        codes=codes,
        hasher=hasher,
        code_service=code_service,
        password_policy=password_policy,
        notifier=notifier,
        audit=audit,
        clock=clock,
    )


def get_verify_email_use_case(
    users: UserRepoDep,
    codes: CodeRepoDep,
    code_service: CodeServiceDep,
    notifier: NotifierDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
) -> VerifyEmail:
    return VerifyEmail(
        users=users,
        codes=codes,
        code_service=code_service,
        notifier=notifier,
        audit=audit,
        clock=clock,
    )


def get_resend_code_use_case(
    users: UserRepoDep,
    codes: CodeRepoDep,
    code_service: CodeServiceDep,
    notifier: NotifierDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> ResendVerificationCode:
    return ResendVerificationCode(
        users=users,
        codes=codes,
        code_service=code_service,
        notifier=notifier,
        audit=audit,
        clock=clock,
        cooldown_seconds=settings.verification_resend_cooldown_seconds,
        max_resends_per_hour=settings.verification_max_resends_per_hour,
    )


def get_authenticate_user_use_case(
    users: UserRepoDep,
    refresh_tokens: RefreshRepoDep,
    hasher: PasswordHasherDep,
    tokens: TokenIssuerDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
) -> AuthenticateUser:
    return AuthenticateUser(
        users=users,
        refresh_tokens=refresh_tokens,
        hasher=hasher,
        tokens=tokens,
        audit=audit,
        clock=clock,
    )


def get_refresh_session_use_case(
    users: UserRepoDep,
    refresh_tokens: RefreshRepoDep,
    tokens: TokenIssuerDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
) -> RefreshSession:
    return RefreshSession(
        users=users,
        refresh_tokens=refresh_tokens,
        tokens=tokens,
        audit=audit,
        clock=clock,
    )


def get_logout_user_use_case(
    refresh_tokens: RefreshRepoDep,
    tokens: TokenIssuerDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
) -> LogoutUser:
    return LogoutUser(
        refresh_tokens=refresh_tokens,
        tokens=tokens,
        audit=audit,
        clock=clock,
    )


def get_profile_use_case(users: UserRepoDep) -> GetProfile:
    return GetProfile(users=users)


def get_update_profile_use_case(
    users: UserRepoDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
) -> UpdateProfile:
    return UpdateProfile(users=users, audit=audit, clock=clock)


def get_change_password_use_case(
    users: UserRepoDep,
    refresh_tokens: RefreshRepoDep,
    hasher: PasswordHasherDep,
    password_policy: PasswordPolicyDep,
    tokens: TokenIssuerDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
) -> ChangePassword:
    return ChangePassword(
        users=users,
        refresh_tokens=refresh_tokens,
        hasher=hasher,
        password_policy=password_policy,
        tokens=tokens,
        audit=audit,
        clock=clock,
    )


__all__ = [
    "Argon2PasswordHasher",
    "AuditLoggerDep",
    "ClockDep",
    "CodeRepoDep",
    "CodeServiceDep",
    "CurrentUserDep",
    "NotifierDep",
    "PasswordHasherDep",
    "PasswordPolicyDep",
    "PyJwtTokenIssuer",
    "RefreshRepoDep",
    "RequestContextDep",
    "SessionDep",
    "SettingsDep",
    "TokenIssuerDep",
    "UserRepoDep",
    "get_audit_logger",
    "get_authenticate_user_use_case",
    "get_change_password_use_case",
    "get_clock",
    "get_current_user",
    "get_logout_user_use_case",
    "get_notifier",
    "get_profile_use_case",
    "get_refresh_session_use_case",
    "get_register_user_use_case",
    "get_request_context",
    "get_resend_code_use_case",
    "get_session",
    "get_update_profile_use_case",
    "get_verify_email_use_case",
]
