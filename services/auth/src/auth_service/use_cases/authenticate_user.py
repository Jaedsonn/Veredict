"""Casos de uso [S1-09]: Login, rotação de refresh token com detecção de reuso e logout (RF03)."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from auth_service.domain.entities import (
    AuthenticatedResult,
    LoginResult,
    TokenPairResult,
)
from auth_service.domain.errors import (
    AccountBlockedError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenReuseDetectedError,
)
from auth_service.models import RevokeReason, UserStatus
from auth_service.ports import (
    Clock,
    PasswordHasher,
    RefreshTokenRepository,
    TokenIssuer,
    UserRepository,
)
from veriditi_common.audit import AuditEvent, AuditLogger, AuditOutcome
from veriditi_common.middleware import RequestContext


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class LoginCommand:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class RefreshCommand:
    refresh_token: str


@dataclass(frozen=True, slots=True)
class LogoutCommand:
    refresh_token: str
    actor_id: int | None = None


class AuthenticateUser:
    """Autentica credenciais, verifica status da conta e emite par de tokens RS256 + Refresh (#9).

    Retorna `LoginResult` (união de tipos preparada para `MfaRequiredResult` na Sprint 2 — OCP).
    """

    def __init__(
        self,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        hasher: PasswordHasher,
        tokens: TokenIssuer,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._hasher = hasher
        self._tokens = tokens
        self._audit = audit
        self._clock = clock

    async def execute(self, cmd: LoginCommand, ctx: RequestContext) -> LoginResult:
        normalized_email = cmd.email.strip().lower()
        now = self._clock.now()

        user = await self._users.get_by_email(normalized_email)
        if user is None:
            # Sempre executa Argon2id verify para evitar ataque de tempo (enumeração de e-mail)
            self._hasher.verify_dummy(cmd.password)
            await self._audit.record(
                AuditEvent(
                    occurred_at=now,
                    service="auth",
                    action="auth.session.login_failed",
                    outcome=AuditOutcome.FAILURE,
                    actor_id=None,
                    actor_ip=ctx.actor_ip,
                    request_id=_parse_uuid(ctx.request_id),
                    resource_type="session",
                    metadata={"reason": "user_not_found"},
                )
            )
            raise InvalidCredentialsError()

        if not self._hasher.verify(cmd.password, user.password_hash):
            await self._audit.record(
                AuditEvent(
                    occurred_at=now,
                    service="auth",
                    action="auth.session.login_failed",
                    outcome=AuditOutcome.FAILURE,
                    actor_id=user.id,
                    actor_ip=ctx.actor_ip,
                    request_id=_parse_uuid(ctx.request_id),
                    resource_type="user",
                    resource_id=str(user.id),
                    metadata={"reason": "invalid_password"},
                )
            )
            raise InvalidCredentialsError()

        if user.status == UserStatus.PENDING_VERIFICATION:
            await self._audit.record(
                AuditEvent(
                    occurred_at=now,
                    service="auth",
                    action="auth.session.login_failed",
                    outcome=AuditOutcome.FAILURE,
                    actor_id=user.id,
                    actor_ip=ctx.actor_ip,
                    request_id=_parse_uuid(ctx.request_id),
                    resource_type="user",
                    resource_id=str(user.id),
                    metadata={"reason": "email_not_verified"},
                )
            )
            raise EmailNotVerifiedError()

        if user.status == UserStatus.BLOCKED:
            await self._audit.record(
                AuditEvent(
                    occurred_at=now,
                    service="auth",
                    action="auth.session.login_failed",
                    outcome=AuditOutcome.FAILURE,
                    actor_id=user.id,
                    actor_ip=ctx.actor_ip,
                    request_id=_parse_uuid(ctx.request_id),
                    resource_type="user",
                    resource_id=str(user.id),
                    metadata={"reason": "account_blocked"},
                )
            )
            raise AccountBlockedError()

        access_token = self._tokens.issue_access_token(
            user_id=user.id,
            email=user.email,
            now=now,
        )
        raw_refresh, refresh_hash = self._tokens.generate_refresh_token()
        family_id = uuid.uuid4()
        expires_at = now + timedelta(days=self._tokens.refresh_ttl_days)

        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=refresh_hash,
            family_id=family_id,
            expires_at=expires_at,
            created_ip=ctx.actor_ip,
            user_agent=ctx.user_agent,
            now=now,
        )

        await self._audit.record(
            AuditEvent(
                occurred_at=now,
                service="auth",
                action="auth.session.login_succeeded",
                outcome=AuditOutcome.SUCCESS,
                actor_id=user.id,
                actor_ip=ctx.actor_ip,
                request_id=_parse_uuid(ctx.request_id),
                resource_type="session",
                resource_id=str(family_id),
            )
        )

        return AuthenticatedResult(
            tokens=TokenPairResult(
                access_token=access_token,
                refresh_token=raw_refresh,
                expires_in=self._tokens.access_ttl_seconds,
            ),
            user=user,
        )


class RefreshSession:
    """Rotaciona refresh tokens e revoga todas as sessões em caso de reuso (#9)."""

    def __init__(
        self,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        tokens: TokenIssuer,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._tokens = tokens
        self._audit = audit
        self._clock = clock

    async def execute(self, cmd: RefreshCommand, ctx: RequestContext) -> TokenPairResult:
        now = self._clock.now()
        raw_token = cmd.refresh_token.strip()
        if not raw_token:
            raise InvalidRefreshTokenError()

        token_hash = self._tokens.hash_refresh_token(raw_token)
        stored = await self._refresh_tokens.get_by_hash(token_hash)
        if stored is None:
            raise InvalidRefreshTokenError()

        if stored.revoked_at is not None:
            if stored.revoke_reason in (RevokeReason.ROTATED, RevokeReason.REUSE_DETECTED):
                # Reuso de refresh token já rotacionado: possível comprometimento de sessão!
                revoked_count = await self._refresh_tokens.revoke_all_for_user(
                    stored.user_id,
                    reason=RevokeReason.REUSE_DETECTED,
                    revoked_at=now,
                )
                await self._audit.record(
                    AuditEvent(
                        occurred_at=now,
                        service="auth",
                        action="auth.session.refresh_reuse_detected",
                        outcome=AuditOutcome.FAILURE,
                        actor_id=stored.user_id,
                        actor_ip=ctx.actor_ip,
                        request_id=_parse_uuid(ctx.request_id),
                        resource_type="session",
                        resource_id=str(stored.family_id),
                        metadata={
                            "family_id": str(stored.family_id),
                            "revoked_sessions": revoked_count,
                        },
                    )
                )
                raise RefreshTokenReuseDetectedError()
            raise InvalidRefreshTokenError()

        if stored.expires_at <= now:
            raise InvalidRefreshTokenError()

        user = await self._users.get_by_id(stored.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise InvalidRefreshTokenError()

        await self._refresh_tokens.revoke(
            stored.id,
            reason=RevokeReason.ROTATED,
            revoked_at=now,
        )

        access_token = self._tokens.issue_access_token(
            user_id=user.id,
            email=user.email,
            now=now,
        )
        new_raw_refresh, new_refresh_hash = self._tokens.generate_refresh_token()
        expires_at = now + timedelta(days=self._tokens.refresh_ttl_days)

        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=new_refresh_hash,
            family_id=stored.family_id,
            expires_at=expires_at,
            created_ip=ctx.actor_ip,
            user_agent=ctx.user_agent,
            now=now,
        )

        return TokenPairResult(
            access_token=access_token,
            refresh_token=new_raw_refresh,
            expires_in=self._tokens.access_ttl_seconds,
        )


class LogoutUser:
    """Revoga o refresh token informado e registra evento de auditoria (#9, REQ 04)."""

    def __init__(
        self,
        refresh_tokens: RefreshTokenRepository,
        tokens: TokenIssuer,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._refresh_tokens = refresh_tokens
        self._tokens = tokens
        self._audit = audit
        self._clock = clock

    async def execute(self, cmd: LogoutCommand, ctx: RequestContext) -> None:
        now = self._clock.now()
        raw_token = cmd.refresh_token.strip()
        stored = None
        if raw_token:
            token_hash = self._tokens.hash_refresh_token(raw_token)
            stored = await self._refresh_tokens.get_by_hash(token_hash)
            if stored is not None and stored.revoked_at is None:
                await self._refresh_tokens.revoke(
                    stored.id,
                    reason=RevokeReason.LOGOUT,
                    revoked_at=now,
                )

        actor_id = (
            cmd.actor_id if cmd.actor_id is not None else (stored.user_id if stored else None)
        )
        await self._audit.record(
            AuditEvent(
                occurred_at=now,
                service="auth",
                action="auth.session.logout",
                outcome=AuditOutcome.SUCCESS,
                actor_id=actor_id,
                actor_ip=ctx.actor_ip,
                request_id=_parse_uuid(ctx.request_id),
                resource_type="session",
                resource_id=str(stored.family_id) if stored else None,
            )
        )
