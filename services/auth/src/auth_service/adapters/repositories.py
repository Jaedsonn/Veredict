"""Adaptadores de repositório em SQLAlchemy assíncrono (SRP, ISP, DIP)."""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.entities import (
    RefreshTokenEntity,
    UserEntity,
    VerificationCodeEntity,
)
from auth_service.domain.errors import EmailAlreadyRegisteredError, UserNotFoundError
from auth_service.models import (
    EmailVerificationCode,
    RefreshToken,
    RevokeReason,
    User,
    UserRole,
    UserStatus,
    VerificationPurpose,
)


def _to_user_entity(
    model: User,
    *,
    role: UserRole = UserRole.COMMON,
    cpf: str | None = None,
    oab_number: str | None = None,
) -> UserEntity:
    return UserEntity(
        id=model.id,
        email=model.email,
        name=model.name,
        password_hash=model.password_hash,
        status=model.status,
        email_verified_at=model.email_verified_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        role=role,
        cpf=cpf,
        oab_number=oab_number,
    )


def _to_code_entity(model: EmailVerificationCode) -> VerificationCodeEntity:
    return VerificationCodeEntity(
        id=model.id,
        user_id=model.user_id,
        purpose=model.purpose,
        code_hash=model.code_hash,
        attempts=model.attempts,
        expires_at=model.expires_at,
        consumed_at=model.consumed_at,
        created_at=model.created_at,
    )


def _to_refresh_entity(model: RefreshToken) -> RefreshTokenEntity:
    return RefreshTokenEntity(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        family_id=model.family_id,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
        revoke_reason=model.revoke_reason,
        created_ip=model.created_ip,
        user_agent=model.user_agent,
        created_at=model.created_at,
    )


class SqlAlchemyUserRepository:
    """Implementação SQLAlchemy de `UserRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        email: str,
        name: str,
        password_hash: str,
        role: UserRole = UserRole.COMMON,
        cpf: str | None = None,
        oab_number: str | None = None,
        now: datetime,
    ) -> UserEntity:
        user = User(
            email=email,
            name=name,
            password_hash=password_hash,
            status=UserStatus.PENDING_VERIFICATION,
            email_verified_at=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(user)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError(email) from exc
        await self._session.refresh(user)
        return _to_user_entity(user, role=role, cpf=cpf, oab_number=oab_number)

    async def get_by_id(self, user_id: int) -> UserEntity | None:
        user = await self._session.get(User, user_id)
        return _to_user_entity(user) if user is not None else None

    async def get_by_email(self, email: str) -> UserEntity | None:
        stmt = select(User).where(User.email == email)
        user = await self._session.scalar(stmt)
        return _to_user_entity(user) if user is not None else None

    async def mark_email_verified(self, user_id: int, *, verified_at: datetime) -> UserEntity:
        user = await self._session.get(User, user_id)
        if user is None:
            raise UserNotFoundError()
        user.status = UserStatus.ACTIVE
        user.email_verified_at = verified_at
        user.updated_at = verified_at
        await self._session.commit()
        await self._session.refresh(user)
        return _to_user_entity(user)

    async def update_name(self, user_id: int, *, name: str, now: datetime) -> UserEntity:
        user = await self._session.get(User, user_id)
        if user is None:
            raise UserNotFoundError()
        user.name = name
        user.updated_at = now
        await self._session.commit()
        await self._session.refresh(user)
        return _to_user_entity(user)

    async def update_password_hash(
        self, user_id: int, *, password_hash: str, now: datetime
    ) -> UserEntity:
        user = await self._session.get(User, user_id)
        if user is None:
            raise UserNotFoundError()
        user.password_hash = password_hash
        user.updated_at = now
        await self._session.commit()
        await self._session.refresh(user)
        return _to_user_entity(user)


class SqlAlchemyVerificationCodeRepository:
    """Implementação SQLAlchemy de `VerificationCodeRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_and_invalidate_previous(
        self,
        *,
        user_id: int,
        code_hash: str,
        expires_at: datetime,
        now: datetime,
        purpose: VerificationPurpose = VerificationPurpose.EMAIL_VERIFICATION,
    ) -> VerificationCodeEntity:
        invalidate_stmt = (
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        await self._session.execute(invalidate_stmt)

        record = EmailVerificationCode(
            user_id=user_id,
            purpose=purpose,
            code_hash=code_hash,
            attempts=0,
            expires_at=expires_at,
            consumed_at=None,
            created_at=now,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return _to_code_entity(record)

    async def get_latest_active(
        self,
        user_id: int,
        *,
        purpose: VerificationPurpose = VerificationPurpose.EMAIL_VERIFICATION,
    ) -> VerificationCodeEntity | None:
        stmt = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.consumed_at.is_(None),
            )
            .order_by(EmailVerificationCode.id.desc())
            .limit(1)
        )
        record = await self._session.scalar(stmt)
        return _to_code_entity(record) if record is not None else None

    async def get_latest_for_user(
        self,
        user_id: int,
        *,
        purpose: VerificationPurpose = VerificationPurpose.EMAIL_VERIFICATION,
    ) -> VerificationCodeEntity | None:
        stmt = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.purpose == purpose,
            )
            .order_by(EmailVerificationCode.id.desc())
            .limit(1)
        )
        record = await self._session.scalar(stmt)
        return _to_code_entity(record) if record is not None else None

    async def count_created_since(
        self,
        user_id: int,
        *,
        since: datetime,
        purpose: VerificationPurpose = VerificationPurpose.EMAIL_VERIFICATION,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(EmailVerificationCode)
            .where(
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.created_at >= since,
            )
        )
        count = await self._session.scalar(stmt)
        return int(count or 0)

    async def increment_attempts(
        self,
        code_id: int,
        *,
        max_attempts: int,
        now: datetime,
    ) -> VerificationCodeEntity:
        record = await self._session.get(EmailVerificationCode, code_id)
        if record is None:
            raise ValueError(f"Código de verificação {code_id} não encontrado.")
        record.attempts += 1
        if record.attempts >= max_attempts:
            record.consumed_at = now
        await self._session.commit()
        await self._session.refresh(record)
        return _to_code_entity(record)

    async def mark_consumed(self, code_id: int, *, consumed_at: datetime) -> None:
        record = await self._session.get(EmailVerificationCode, code_id)
        if record is not None:
            record.consumed_at = consumed_at
            await self._session.commit()


class SqlAlchemyRefreshTokenRepository:
    """Implementação SQLAlchemy de `RefreshTokenRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        record = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
            revoked_at=None,
            revoke_reason=None,
            created_ip=created_ip,
            user_agent=user_agent,
            created_at=now,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return _to_refresh_entity(record)

    async def get_by_hash(self, token_hash: str) -> RefreshTokenEntity | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash.lower())
        record = await self._session.scalar(stmt)
        return _to_refresh_entity(record) if record is not None else None

    async def revoke(
        self,
        token_id: int,
        *,
        reason: RevokeReason,
        revoked_at: datetime,
    ) -> None:
        record = await self._session.get(RefreshToken, token_id)
        if record is not None and record.revoked_at is None:
            record.revoked_at = revoked_at
            record.revoke_reason = reason
            await self._session.commit()

    async def revoke_all_for_user(
        self,
        user_id: int,
        *,
        reason: RevokeReason,
        revoked_at: datetime,
        exclude_token_hash: str | None = None,
    ) -> int:
        conditions = [
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        ]
        if exclude_token_hash:
            conditions.append(RefreshToken.token_hash != exclude_token_hash.lower())

        stmt = (
            update(RefreshToken)
            .where(*conditions)
            .values(revoked_at=revoked_at, revoke_reason=reason)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
