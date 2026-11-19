"""Casos de uso [S2-02]: Recuperação de senha por link enviado por e-mail (RF05, ADR-008)"""

from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn

from auth_service.domain.entities import PasswordResetTokenEntity, RequestContext
from auth_service.domain.errors import InvalidResetTokenError, WeakPasswordError
from auth_service.domain.password_policy import PasswordPolicy
from auth_service.domain.reset_token import ResetTokenService
from auth_service.models import RevokeReason, UserStatus
from auth_service.ports import (
    Clock,
    PasswordHasher,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from veriditi_common.audit import AuditEvent, AuditLogger, AuditOutcome
from veriditi_common.notifications import NotificationRequest, NotificationTemplate, Notifier


@dataclass(frozen=True, slots=True)
class RequestPasswordResetCommand:
    email: str


@dataclass(frozen=True, slots=True)
class ResetPasswordCommand:
    token: str
    new_password: str


class RequestPasswordReset:
    """Gera o link de uso único para conta ativa; para as demais, o mesmo 202 sem efeito (#19)"""

    def __init__(
        self,
        users: UserRepository,
        reset_tokens: PasswordResetTokenRepository,
        token_service: ResetTokenService,
        notifier: Notifier,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._users = users
        self._reset_tokens = reset_tokens
        self._token_service = token_service
        self._notifier = notifier
        self._audit = audit
        self._clock = clock

    async def execute(self, cmd: RequestPasswordResetCommand, ctx: RequestContext) -> None:
        normalized_email = cmd.email.strip().lower()
        now = self._clock.now()

        # Sem lock por e-mail: FOR UPDATE num e-mail inexistente vira gap lock em uq_users_email
        user = await self._users.get_by_email(normalized_email)
        if user is not None and user.status == UserStatus.ACTIVE:
            # Ordem única com o reset: usuário (PK) e depois tokens; serializa os pedidos da conta
            user = await self._users.get_by_id(user.id, for_update=True)
        if user is None or user.status != UserStatus.ACTIVE:
            # Anti-enumeração: a resposta é igual; a auditoria guarda o motivo, nunca o e-mail
            await self._audit.record(
                AuditEvent(
                    occurred_at=now,
                    service="auth",
                    action="auth.password.reset_requested",
                    outcome=AuditOutcome.FAILURE,
                    actor_id=user.id if user is not None else None,
                    actor_ip=ctx.actor_ip_address,
                    request_id=ctx.request_uuid,
                    metadata={"reason": "user_not_found" if user is None else "account_not_active"},
                )
            )
            return

        raw_token, token_hash = self._token_service.generate()
        record = await self._reset_tokens.create_and_invalidate_previous(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=self._token_service.compute_expiry(now),
            requested_ip=ctx.actor_ip,
            now=now,
        )

        await self._notifier.send(
            NotificationRequest(
                template=NotificationTemplate.PASSWORD_RESET,
                to=user.email,
                data={
                    "name": user.name,
                    "token": raw_token,
                    "expires_in_minutes": self._token_service.ttl_minutes,
                },
                idempotency_key=f"password_reset:{record.id}",
            )
        )

        await self._audit.record(
            AuditEvent(
                occurred_at=now,
                service="auth",
                action="auth.password.reset_requested",
                outcome=AuditOutcome.SUCCESS,
                actor_id=user.id,
                actor_ip=ctx.actor_ip_address,
                request_id=ctx.request_uuid,
                resource_type="user",
                resource_id=str(user.id),
            )
        )


class ResetPassword:
    """Consome o link, troca o hash e revoga todas as sessões numa transação só (#19)"""

    def __init__(
        self,
        users: UserRepository,
        reset_tokens: PasswordResetTokenRepository,
        refresh_tokens: RefreshTokenRepository,
        token_service: ResetTokenService,
        hasher: PasswordHasher,
        password_policy: PasswordPolicy,
        notifier: Notifier,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._users = users
        self._reset_tokens = reset_tokens
        self._refresh_tokens = refresh_tokens
        self._token_service = token_service
        self._hasher = hasher
        self._password_policy = password_policy
        self._notifier = notifier
        self._audit = audit
        self._clock = clock

    async def execute(self, cmd: ResetPasswordCommand, ctx: RequestContext) -> None:
        token = cmd.token.strip()
        if not self._token_service.is_well_formed(token):
            await self._fail(ctx, reason="malformed")

        # Antes de consumir: senha fraca não pode queimar o link
        self._password_policy.validate(cmd.new_password, field="new_password")
        # Calcula o hash novo antes de abrir a transação para reduzir o tempo sob lock
        new_hash = self._hasher.hash(cmd.new_password)

        now = self._clock.now()
        token_hash = self._token_service.hash_token(token)
        # Leitura sem lock só para achar o dono; quem decide é o UPDATE condicional abaixo
        stored = await self._reset_tokens.get_by_hash(token_hash)
        if stored is None or not _is_usable(stored, now):
            await self._fail(ctx, reason=_failure_reason(stored), stored=stored)

        # Mesma ordem do forgot: trava o usuário por PK antes de tocar nos tokens dele
        user = await self._users.get_by_id(stored.user_id, for_update=True)
        if user is None or user.status != UserStatus.ACTIVE:
            # Sem commit: a sessão fecha com rollback e o token continua como estava
            await self._fail(ctx, reason="account_not_active", stored=stored)

        record = await self._reset_tokens.consume(token_hash, now=now, commit=False)
        if record is None:
            # Perdeu a corrida: a leitura travada enxerga o consumo que a outra já gravou
            current = await self._reset_tokens.get_by_hash(token_hash, for_update=True)
            await self._fail(ctx, reason=_failure_reason(current), stored=current)

        if self._hasher.verify(cmd.new_password, user.password_hash):
            # O rollback da sessão desfaz o consumo provisório e permite reutilizar o link
            raise WeakPasswordError(
                "A nova senha deve ser diferente da atual.",
                field="new_password",
            )

        await self._users.update_password_hash(
            user.id,
            password_hash=new_hash,
            now=now,
            commit=False,
        )
        # Faz o COMMIT do consumo, do hash novo e das revogações juntos
        revoked = await self._refresh_tokens.revoke_all_for_user(
            user.id,
            reason=RevokeReason.PASSWORD_RESET,
            revoked_at=now,
        )

        await self._notifier.send(
            NotificationRequest(
                template=NotificationTemplate.PASSWORD_CHANGED,
                to=user.email,
                data={"name": user.name},
                idempotency_key=f"password_changed:{record.id}",
            )
        )

        await self._audit.record(
            AuditEvent(
                occurred_at=now,
                service="auth",
                action="auth.password.reset_completed",
                outcome=AuditOutcome.SUCCESS,
                actor_id=user.id,
                actor_ip=ctx.actor_ip_address,
                request_id=ctx.request_uuid,
                resource_type="user",
                resource_id=str(user.id),
                metadata={"revoked_sessions": revoked},
            )
        )

    async def _fail(
        self,
        ctx: RequestContext,
        *,
        reason: str,
        stored: PasswordResetTokenEntity | None = None,
    ) -> NoReturn:
        """Audita o motivo real e levanta sempre o mesmo 400, para o link não virar oráculo"""
        await self._audit.record(
            AuditEvent(
                occurred_at=self._clock.now(),
                service="auth",
                action="auth.password.reset_failed",
                outcome=AuditOutcome.FAILURE,
                actor_id=stored.user_id if stored is not None else None,
                actor_ip=ctx.actor_ip_address,
                request_id=ctx.request_uuid,
                resource_type="user" if stored is not None else None,
                resource_id=str(stored.user_id) if stored is not None else None,
                metadata={"reason": reason},
            )
        )
        raise InvalidResetTokenError()


def _is_usable(stored: PasswordResetTokenEntity, now: datetime) -> bool:
    return stored.consumed_at is None and stored.expires_at > now


def _failure_reason(stored: PasswordResetTokenEntity | None) -> str:
    """Usado e substituído têm o mesmo consumed_at; expirado é o que ainda estava ativo"""
    if stored is None:
        return "not_found"
    if stored.consumed_at is not None:
        return "consumed"
    return "expired"
