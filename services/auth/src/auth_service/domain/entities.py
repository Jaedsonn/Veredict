"""Entidades e objetos de valor do domínio de Autenticação."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from auth_service.models import RevokeReason, UserRole, UserStatus, VerificationPurpose


@dataclass(slots=True)
class UserEntity:
    """Representação de domínio de um usuário da plataforma."""

    id: int
    email: str
    name: str
    password_hash: str
    status: UserStatus
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime
    role: UserRole = UserRole.COMMON
    cpf: str | None = None
    oab_number: str | None = None


@dataclass(slots=True)
class VerificationCodeEntity:
    """Representação de domínio de um código de verificação de 6 dígitos."""

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
    """Representação de domínio de um refresh token persistido por hash."""

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
    """Par de tokens (Access JWT RS256 + Refresh opaco) emitido em sessões autenticadas."""

    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class AuthenticatedResult:
    """Resultado de login concluído com emissão imediata de sessão."""

    tokens: TokenPairResult
    user: UserEntity


@dataclass(frozen=True, slots=True)
class MfaRequiredResult:
    """Ponto de extensão (OCP) para o desafio de 2º fator na Sprint 2 (#18 / ADR-009)."""

    mfa_token: str
    methods: tuple[str, ...] = ("totp", "email")


@dataclass(frozen=True, slots=True)
class MfaSetupRequiredResult:
    """Ponto de extensão (OCP) para configuração obrigatória de MFA no 1º acesso (#18)."""

    mfa_setup_token: str


type LoginResult = AuthenticatedResult | MfaRequiredResult | MfaSetupRequiredResult
