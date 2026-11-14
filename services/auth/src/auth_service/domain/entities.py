"""Entidades e objetos de valor do domínio de Autenticação"""

import ipaddress
import uuid
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from auth_service.models import RevokeReason, UserStatus, VerificationPurpose


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Metadados de transporte extraídos da requisição HTTP para auditoria e sessão"""

    request_id: str | None = None
    actor_ip: str | None = None
    user_agent: str | None = None

    @property
    def request_uuid(self) -> uuid.UUID | None:
        if not self.request_id:
            return None
        try:
            return uuid.UUID(self.request_id)
        except ValueError:
            return None

    @property
    def actor_ip_address(self) -> IPv4Address | IPv6Address | None:
        if not self.actor_ip:
            return None
        try:
            return ipaddress.ip_address(self.actor_ip)
        except ValueError:
            return None


@dataclass(slots=True)
class UserEntity:
    """Representação de domínio de um usuário da plataforma (`docs/banco-de-dados.md` §5.1)"""

    id: int
    email: str
    name: str
    password_hash: str
    status: UserStatus
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class VerificationCodeEntity:
    """Representação de domínio de um código de verificação de 6 dígitos (§5.2)"""

    id: int
    user_id: int
    purpose: VerificationPurpose
    code_hash: str
    attempts: int
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime


@dataclass(slots=True)
class RefreshTokenEntity:
    """Representação de domínio de um refresh token persistido por hash (§5.3)"""

    id: int
    user_id: int
    token_hash: str
    family_id: uuid.UUID
    expires_at: datetime
    revoked_at: datetime | None
    revoke_reason: RevokeReason | None
    created_ip: str | None
    user_agent: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TokenPairResult:
    """Par de tokens (Access JWT RS256 + Refresh opaco) emitido em sessões autenticadas"""

    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class AuthenticatedResult:
    """Resultado de login concluído com emissão imediata de sessão"""

    tokens: TokenPairResult
    user: UserEntity


@dataclass(frozen=True, slots=True)
class MfaRequiredResult:
    """Ponto de extensão para o desafio de 2º fator na Sprint 2 (#18 / ADR-009)"""

    mfa_token: str
    methods: tuple[str, ...] = ("totp", "email")


@dataclass(frozen=True, slots=True)
class MfaSetupRequiredResult:
    """Ponto de extensão para configuração obrigatória de MFA no 1º acesso (#18)"""

    mfa_setup_token: str


type LoginResult = AuthenticatedResult | MfaRequiredResult | MfaSetupRequiredResult
