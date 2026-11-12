"""Casos de uso [S1-08]: Verificação de e-mail por código de 6 dígitos e reenvio (RF02, ADR-007)."""

import math
import uuid
from dataclasses import dataclass
from datetime import timedelta

from auth_service.domain.entities import UserEntity
from auth_service.domain.errors import (
    InvalidVerificationCodeError,
    ResendRateLimitError,
    VerificationCodeExpiredError,
    VerificationCodeTooManyAttemptsError,
)
from auth_service.domain.verification_code import VerificationCodeService
from auth_service.models import UserStatus, VerificationPurpose
from auth_service.ports import Clock, UserRepository, VerificationCodeRepository
from veriditi_common.audit import AuditEvent, AuditLogger, AuditOutcome
from veriditi_common.middleware import RequestContext
from veriditi_common.notifications import NotificationRequest, Notifier


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class VerifyEmailCommand:
    email: str
    code: str


@dataclass(frozen=True, slots=True)
class ResendVerificationCommand:
    email: str


class VerifyEmail:
    """Valida o código de 6 dígitos, ativa o usuário e dispara boas-vindas e auditoria (#8)."""

    def __init__(
        self,
        users: UserRepository,
        codes: VerificationCodeRepository,
        code_service: VerificationCodeService,
        notifier: Notifier,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._users = users
        self._codes = codes
        self._code_service = code_service
        self._notifier = notifier
        self._audit = audit
        self._clock = clock

    async def execute(self, cmd: VerifyEmailCommand, ctx: RequestContext) -> UserEntity:
        normalized_email = cmd.email.strip().lower()
        now = self._clock.now()

        user = await self._users.get_by_email(normalized_email)
        if user is None:
            raise VerificationCodeExpiredError()

        active_code = await self._codes.get_latest_active(
            user.id,
            purpose=VerificationPurpose.EMAIL_VERIFICATION,
        )
        if active_code is None:
            latest_code = await self._codes.get_latest_for_user(
                user.id,
                purpose=VerificationPurpose.EMAIL_VERIFICATION,
            )
            if (
                latest_code is not None
                and latest_code.attempts >= self._code_service.max_attempts
                and latest_code.expires_at > now
            ):
                raise VerificationCodeTooManyAttemptsError()
            raise VerificationCodeExpiredError()

        if active_code.expires_at <= now:
            await self._codes.mark_consumed(active_code.id, consumed_at=now)
            raise VerificationCodeExpiredError()

        if active_code.attempts >= self._code_service.max_attempts:
            await self._codes.mark_consumed(active_code.id, consumed_at=now)
            raise VerificationCodeTooManyAttemptsError()

        if not self._code_service.verify_code(cmd.code, active_code.code_hash):
            updated = await self._codes.increment_attempts(
                active_code.id,
                max_attempts=self._code_service.max_attempts,
                now=now,
            )
            remaining = max(0, self._code_service.max_attempts - updated.attempts)
            await self._audit.record(
                AuditEvent(
                    occurred_at=now,
                    service="auth",
                    action="auth.email.verification_failed",
                    outcome=AuditOutcome.FAILURE,
                    actor_id=user.id,
                    actor_ip=ctx.actor_ip,
                    request_id=_parse_uuid(ctx.request_id),
                    resource_type="user",
                    resource_id=str(user.id),
                    metadata={"attempts": updated.attempts, "attempts_remaining": remaining},
                )
            )
            if updated.attempts >= self._code_service.max_attempts:
                raise VerificationCodeTooManyAttemptsError()
            raise InvalidVerificationCodeError(attempts_remaining=remaining)

        await self._codes.mark_consumed(active_code.id, consumed_at=now)
        verified_user = await self._users.mark_email_verified(user.id, verified_at=now)

        await self._notifier.send(
            NotificationRequest(
                template="welcome",
                to=verified_user.email,
                data={"name": verified_user.name},
                idempotency_key=f"welcome:{verified_user.id}",
            )
        )

        await self._audit.record(
            AuditEvent(
                occurred_at=now,
                service="auth",
                action="auth.email.verified",
                outcome=AuditOutcome.SUCCESS,
                actor_id=verified_user.id,
                actor_ip=ctx.actor_ip,
                request_id=_parse_uuid(ctx.request_id),
                resource_type="user",
                resource_id=str(verified_user.id),
            )
        )

        return verified_user


class ResendVerificationCode:
    """Reenvia um novo código de verificação respeitando cooldown de 60s e limite de 5/hora (#8)."""

    def __init__(
        self,
        users: UserRepository,
        codes: VerificationCodeRepository,
        code_service: VerificationCodeService,
        notifier: Notifier,
        audit: AuditLogger,
        clock: Clock,
        *,
        cooldown_seconds: int = 60,
        max_resends_per_hour: int = 5,
    ) -> None:
        self._users = users
        self._codes = codes
        self._code_service = code_service
        self._notifier = notifier
        self._audit = audit
        self._clock = clock
        self._cooldown_seconds = cooldown_seconds
        self._max_resends_per_hour = max_resends_per_hour

    async def execute(self, cmd: ResendVerificationCommand, ctx: RequestContext) -> None:
        normalized_email = cmd.email.strip().lower()
        now = self._clock.now()

        user = await self._users.get_by_email(normalized_email)
        if user is None or user.status != UserStatus.PENDING_VERIFICATION:
            # Anti-enumeração: responde 202 sem revelar se o e-mail existe ou já está ativo (#8)
            return

        latest = await self._codes.get_latest_for_user(
            user.id,
            purpose=VerificationPurpose.EMAIL_VERIFICATION,
        )
        if latest is not None:
            elapsed = (now - latest.created_at).total_seconds()
            if elapsed < self._cooldown_seconds:
                retry_after = max(1, math.ceil(self._cooldown_seconds - elapsed))
                raise ResendRateLimitError(retry_after_seconds=retry_after)

        one_hour_ago = now - timedelta(hours=1)
        codes_last_hour = await self._codes.count_created_since(
            user.id,
            since=one_hour_ago,
            purpose=VerificationPurpose.EMAIL_VERIFICATION,
        )
        if codes_last_hour >= self._max_resends_per_hour:
            raise ResendRateLimitError(retry_after_seconds=3600)

        raw_code = self._code_service.generate_code()
        code_hash = self._code_service.hash_code(raw_code)
        expires_at = self._code_service.compute_expiry(now)

        code_record = await self._codes.create_and_invalidate_previous(
            user_id=user.id,
            code_hash=code_hash,
            expires_at=expires_at,
            now=now,
            purpose=VerificationPurpose.EMAIL_VERIFICATION,
        )

        await self._notifier.send(
            NotificationRequest(
                template="email_verification",
                to=user.email,
                data={
                    "name": user.name,
                    "code": raw_code,
                    "expires_in_minutes": self._code_service.ttl_minutes,
                },
                idempotency_key=f"email_verification:{code_record.id}",
            )
        )

        await self._audit.record(
            AuditEvent(
                occurred_at=now,
                service="auth",
                action="auth.email.verification_resent",
                outcome=AuditOutcome.SUCCESS,
                actor_id=user.id,
                actor_ip=ctx.actor_ip,
                request_id=_parse_uuid(ctx.request_id),
                resource_type="user",
                resource_id=str(user.id),
            )
        )
