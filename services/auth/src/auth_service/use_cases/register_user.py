"""Caso de uso [S1-07]: Cadastro de conta com senha forte (RF01, ADR-002, ADR-007, ADR-012)."""

import uuid
from dataclasses import dataclass

from auth_service.domain.entities import UserEntity
from auth_service.domain.password_policy import PasswordPolicy, validate_registration_profile
from auth_service.domain.verification_code import VerificationCodeService
from auth_service.models import UserRole, VerificationPurpose
from auth_service.ports import (
    Clock,
    PasswordHasher,
    UserRepository,
    VerificationCodeRepository,
)
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
class RegisterCommand:
    """Comando de entrada do caso de uso de cadastro."""

    name: str
    email: str
    password: str
    role: str | UserRole = UserRole.COMMON
    cpf: str | None = None
    oab_number: str | None = None


class RegisterUser:
    """Coordena o cadastro de usuário, geração do código de verificação, notificação e auditoria.

    Princípios SOLID aplicados:
    - SRP: Apenas orquestra o fluxo de registro; validação de senha (`PasswordPolicy`),
      hash Argon2id (`PasswordHasher`) e geração de código (`VerificationCodeService`)
      estão em classes dedicadas.
    - DIP / ISP: Depende exclusivamente de `Protocol`s injetados no construtor.
    """

    def __init__(
        self,
        users: UserRepository,
        codes: VerificationCodeRepository,
        hasher: PasswordHasher,
        code_service: VerificationCodeService,
        password_policy: PasswordPolicy,
        notifier: Notifier,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._users = users
        self._codes = codes
        self._hasher = hasher
        self._code_service = code_service
        self._password_policy = password_policy
        self._notifier = notifier
        self._audit = audit
        self._clock = clock

    async def execute(self, cmd: RegisterCommand, ctx: RequestContext) -> UserEntity:
        normalized_email = cmd.email.strip().lower()
        normalized_name = cmd.name.strip()

        self._password_policy.validate(cmd.password, field="password")
        parsed_role, normalized_cpf, normalized_oab = validate_registration_profile(
            role=cmd.role,
            cpf=cmd.cpf,
            oab_number=cmd.oab_number,
        )

        now = self._clock.now()
        password_hash = self._hasher.hash(cmd.password)

        user = await self._users.create(
            email=normalized_email,
            name=normalized_name,
            password_hash=password_hash,
            role=parsed_role,
            cpf=normalized_cpf,
            oab_number=normalized_oab,
            now=now,
        )

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
                action="auth.user.registered",
                outcome=AuditOutcome.SUCCESS,
                actor_id=user.id,
                actor_ip=ctx.actor_ip,
                request_id=_parse_uuid(ctx.request_id),
                resource_type="user",
                resource_id=str(user.id),
                metadata={"role": user.role.value},
            )
        )

        return user
