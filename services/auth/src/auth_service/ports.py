"""Portas (Protocols) do serviço de Autenticação

Interfaces enxutas para que os casos de uso dependam só de abstrações,
desacoplando regras de negócio de SQLAlchemy, Argon2, PyJWT e relógio do sistema.
"""

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from auth_service.domain.entities import (
    RefreshTokenEntity,
    UserEntity,
    VerificationCodeEntity,
)
from auth_service.models import RevokeReason, VerificationPurpose


@runtime_checkable
class Clock(Protocol):
    """Abstração de relógio para permitir testes determinísticos de expiração"""

    def now(self) -> datetime:
        """Retorna o instante atual em UTC (timezone-aware)"""


@runtime_checkable
class PasswordHasher(Protocol):
    """Porta para hash e verificação de senhas"""

    def hash(self, plain_password: str) -> str:
        """Gera o hash seguro (Argon2id) da senha"""

    def verify(self, plain_password: str, password_hash: str) -> bool:
        """Verifica se a senha corresponde ao hash armazenado"""

    def verify_dummy(self, plain_password: str) -> None:
        """Executa uma verificação de custo equivalente para mitigar ataques de tempo"""


@runtime_checkable
class TokenIssuer(Protocol):
    """Porta para emissão de tokens de sessão"""

    @property
    def access_ttl_seconds(self) -> int:
        """Tempo de vida do access token em segundos"""

    @property
    def refresh_ttl_days(self) -> int:
        """Tempo de vida do refresh token em dias"""

    def issue_access_token(
        self,
        *,
        user_id: int,
        email: str,
        now: datetime,
        session_id: uuid.UUID | None = None,
    ) -> str:
        """Emite um JWT RS256 assinado com as claims exigidas pelo API Gateway (#9)"""

    def generate_refresh_token(self) -> tuple[str, str]:
        """Gera um refresh token aleatório de 32 bytes e retorna `(raw_token, sha256_hex)`"""

    def hash_refresh_token(self, raw_token: str) -> str:
        """Calcula o SHA-256 hex de um refresh token opaco"""


@runtime_checkable
class UserRepository(Protocol):
    """Porta de persistência de usuários"""

    async def create(
        self,
        *,
        email: str,
        name: str,
        password_hash: str,
        now: datetime,
        commit: bool = True,
    ) -> UserEntity:
        """Cria usuário `pending_verification`; levanta `EmailAlreadyRegisteredError`"""

    async def get_by_id(self, user_id: int) -> UserEntity | None:
        """Busca usuário pelo ID primário"""

    async def get_by_email(
        self,
        email: str,
        *,
        for_update: bool = False,
    ) -> UserEntity | None:
        """Busca usuário pelo e-mail normalizado (opcionalmente com `SELECT ... FOR UPDATE`)"""

    async def mark_email_verified(
        self,
        user_id: int,
        *,
        verified_at: datetime,
        commit: bool = True,
    ) -> UserEntity:
        """Ativa conta `pending_verification` (`status = active`) e preenche `email_verified_at`"""

    async def update_name(self, user_id: int, *, name: str, now: datetime) -> UserEntity:
        """Atualiza o nome do usuário"""

    async def update_password_hash(
        self,
        user_id: int,
        *,
        password_hash: str,
        now: datetime,
        commit: bool = True,
    ) -> UserEntity:
        """Atualiza o hash de senha do usuário"""


@runtime_checkable
class VerificationCodeRepository(Protocol):
    """Porta de persistência de códigos de verificação"""

    async def create_and_invalidate_previous(
        self,
        *,
        user_id: int,
        code_hash: str,
        expires_at: datetime,
        now: datetime,
        purpose: VerificationPurpose = VerificationPurpose.EMAIL_VERIFICATION,
    ) -> VerificationCodeEntity:
        """Invalida códigos ativos anteriores do usuário e cria um novo código"""

    async def get_latest_active(
        self,
        user_id: int,
        *,
        purpose: VerificationPurpose = VerificationPurpose.EMAIL_VERIFICATION,
    ) -> VerificationCodeEntity | None:
        """Retorna o código ativo mais recente (`consumed_at IS NULL`) do usuário"""

    async def get_latest_for_user(
        self,
        user_id: int,
        *,
        purpose: VerificationPurpose = VerificationPurpose.EMAIL_VERIFICATION,
    ) -> VerificationCodeEntity | None:
        """Retorna o último código emitido para o usuário (consumido ou não)"""

    async def count_created_since(
        self,
        user_id: int,
        *,
        since: datetime,
        purpose: VerificationPurpose = VerificationPurpose.EMAIL_VERIFICATION,
    ) -> int:
        """Conta quantos códigos foram gerados para o usuário desde `since`"""

    async def increment_attempts(
        self,
        code_id: int,
        *,
        max_attempts: int,
        now: datetime,
    ) -> VerificationCodeEntity:
        """Incrementa `attempts` atomicamente; ao atingir `max_attempts`, marca `consumed_at`"""

    async def mark_consumed(
        self,
        code_id: int,
        *,
        consumed_at: datetime,
        max_attempts: int | None = None,
        commit: bool = True,
    ) -> bool:
        """Marca o código como consumido condicionalmente; retorna `True` se consumiu"""


@runtime_checkable
class RefreshTokenRepository(Protocol):
    """Porta de persistência de refresh tokens"""

    async def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        family_id: uuid.UUID,
        expires_at: datetime,
        created_ip: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> RefreshTokenEntity:
        """Persiste um novo refresh token"""

    async def get_by_hash(self, token_hash: str) -> RefreshTokenEntity | None:
        """Busca um refresh token pelo seu hash SHA-256"""

    async def rotate_token(
        self,
        *,
        current_token_id: int,
        user_id: int,
        new_token_hash: str,
        family_id: uuid.UUID,
        expires_at: datetime,
        created_ip: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> RefreshTokenEntity | None:
        """Revoga condicionalmente o token atual (`rotated`) e cria o sucessor na transação"""

    async def revoke(
        self,
        token_id: int,
        *,
        reason: RevokeReason,
        revoked_at: datetime,
    ) -> None:
        """Revoga um refresh token específico"""

    async def revoke_all_for_user(
        self,
        user_id: int,
        *,
        reason: RevokeReason,
        revoked_at: datetime,
        exclude_token_hash: str | None = None,
        exclude_family_id: uuid.UUID | None = None,
    ) -> int:
        """Revoga os refresh tokens ativos do usuário (preservando opcionalmente a sessão atual)"""
