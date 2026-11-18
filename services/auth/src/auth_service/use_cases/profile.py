"""Casos de uso [S1-10]: Consulta e edição de perfil e troca de senha (RF06)"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import JsonValue

from auth_service.domain.entities import RequestContext, UserEntity
from auth_service.domain.errors import (
    InvalidCurrentPasswordError,
    UserNotFoundError,
    WeakPasswordError,
)
from auth_service.domain.oab import Oab
from auth_service.domain.password_policy import PasswordPolicy
from auth_service.models import RevokeReason, UserStatus, UserType
from auth_service.ports import (
    Clock,
    CpfProtector,
    PasswordHasher,
    RefreshTokenRepository,
    TokenIssuer,
    UserRepository,
)
from veriditi_common.audit import AuditEvent, AuditLogger, AuditOutcome


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ProfileView:
    """Perfil para o próprio usuário: o CPF sai só mascarado e a OAB como foi informada (#60)"""

    id: int
    name: str
    email: str
    status: UserStatus
    email_verified_at: datetime | None
    created_at: datetime
    user_type: UserType
    cpf_masked: str
    oab: Oab | None


def _to_view(user: UserEntity, cpf_protector: CpfProtector) -> ProfileView:
    return ProfileView(
        id=user.id,
        name=user.name,
        email=user.email,
        status=user.status,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        user_type=user.user_type,
        cpf_masked=cpf_protector.decrypt(user.cpf_enc).masked,
        oab=user.oab,
    )


@dataclass(frozen=True, slots=True)
class UpdateProfileCommand:
    user_id: int
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ChangePasswordCommand:
    user_id: int
    current_password: str
    new_password: str
    current_session_id: str | None = None
    current_refresh_token: str | None = None


class GetProfile:
    """Consulta os dados de perfil do usuário autenticado (#10)

    Único lugar que decifra o CPF, e só para devolvê-lo mascarado (ADR-024).
    """

    def __init__(self, users: UserRepository, cpf_protector: CpfProtector) -> None:
        self._users = users
        self._cpf_protector = cpf_protector

    async def execute(self, user_id: int) -> ProfileView:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        return _to_view(user, self._cpf_protector)


class UpdateProfile:
    """Atualiza campos permitidos do perfil e emite auditoria dos campos alterados (#10)

    Tipo de conta, CPF e OAB não são editáveis aqui (#60): o comando nem os carrega.
    """

    def __init__(
        self,
        users: UserRepository,
        audit: AuditLogger,
        clock: Clock,
        cpf_protector: CpfProtector,
    ) -> None:
        self._users = users
        self._audit = audit
        self._clock = clock
        self._cpf_protector = cpf_protector

    async def execute(self, cmd: UpdateProfileCommand, ctx: RequestContext) -> ProfileView:
        user = await self._users.get_by_id(cmd.user_id)
        if user is None:
            raise UserNotFoundError()

        now = self._clock.now()
        changed_fields: list[JsonValue] = []

        if cmd.name is not None:
            cleaned_name = cmd.name.strip()
            user = await self._users.update_name(cmd.user_id, name=cleaned_name, now=now)
            changed_fields.append("name")

        await self._audit.record(
            AuditEvent(
                occurred_at=now,
                service="auth",
                action="auth.profile.updated",
                outcome=AuditOutcome.SUCCESS,
                actor_id=user.id,
                actor_ip=ctx.actor_ip_address,
                request_id=ctx.request_uuid,
                resource_type="user",
                resource_id=str(user.id),
                metadata={"fields": changed_fields},
            )
        )

        return _to_view(user, self._cpf_protector)


class ChangePassword:
    """Valida a senha atual, aplica `PasswordPolicy`, atualiza hash e revoga sessões (#10)"""

    def __init__(
        self,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        hasher: PasswordHasher,
        password_policy: PasswordPolicy,
        tokens: TokenIssuer,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._hasher = hasher
        self._password_policy = password_policy
        self._tokens = tokens
        self._audit = audit
        self._clock = clock

    async def execute(self, cmd: ChangePasswordCommand, ctx: RequestContext) -> None:
        user = await self._users.get_by_id(cmd.user_id)
        if user is None:
            raise UserNotFoundError()

        if not self._hasher.verify(cmd.current_password, user.password_hash):
            raise InvalidCurrentPasswordError()

        self._password_policy.validate(cmd.new_password, field="new_password")
        if cmd.new_password == cmd.current_password:
            raise WeakPasswordError(
                "A nova senha deve ser diferente da atual.",
                field="new_password",
            )

        now = self._clock.now()
        new_hash = self._hasher.hash(cmd.new_password)

        # Atualiza o hash e revoga os demais refresh tokens na mesma transação atômica
        await self._users.update_password_hash(
            user.id,
            password_hash=new_hash,
            now=now,
            commit=False,
        )

        exclude_hash = (
            self._tokens.hash_refresh_token(cmd.current_refresh_token.strip())
            if cmd.current_refresh_token and cmd.current_refresh_token.strip()
            else None
        )
        exclude_family_id = _parse_uuid(cmd.current_session_id)

        await self._refresh_tokens.revoke_all_for_user(
            user.id,
            reason=RevokeReason.LOGOUT,
            revoked_at=now,
            exclude_token_hash=exclude_hash,
            exclude_family_id=exclude_family_id,
        )

        await self._audit.record(
            AuditEvent(
                occurred_at=now,
                service="auth",
                action="auth.password.changed",
                outcome=AuditOutcome.SUCCESS,
                actor_id=user.id,
                actor_ip=ctx.actor_ip_address,
                request_id=ctx.request_uuid,
                resource_type="user",
                resource_id=str(user.id),
            )
        )
