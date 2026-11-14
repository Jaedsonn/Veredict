"""Adaptadores de repositório em SQLAlchemy assíncrono"""

import uuid
from datetime import datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.entities import (
    RefreshTokenEntity,
    UserEntity,
    VerificationCodeEntity,
)
from auth_service.domain.errors import (
    EmailAlreadyRegisteredError,
    UserNotFoundError,
    VerificationCodeExpiredError,
)
from auth_service.models import (
    EmailVerificationCode,
    RefreshToken,
    RevokeReason,
    User,
    UserStatus,
    VerificationPurpose,
)


def _to_user_entity(model: User) -> UserEntity:
    return UserEntity(
        id=model.id,
        email=model.email,
        name=model.name,
        password_hash=model.password_hash,
        status=model.status,
        email_verified_at=model.email_verified_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
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
    """Implementação SQLAlchemy de `UserRepository`"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        email: str,
        name: str,
        password_hash: str,
        now: datetime,
        commit: bool = True,
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
            if commit:
                await self._session.commit()
                await self._session.refresh(user)
            else:
                await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError(email) from exc
        return _to_user_entity(user)

    async def get_by_id(self, user_id: int) -> UserEntity | None:
        user = await self._session.get(User, user_id)
        return _to_user_entity(user) if user is not None else None

    async def get_by_email(
        self,
        email: str,
        *,
        for_update: bool = False,
    ) -> UserEntity | None:
        stmt = select(User).where(User.email == email)
        if for_update:
            stmt = stmt.with_for_update()
        user = await self._session.scalar(stmt)
        return _to_user_entity(user) if user is not None else None

    async def mark_email_verified(
        self,
        user_id: int,
        *,
        verified_at: datetime,
        commit: bool = True,
    ) -> UserEntity:
        stmt = (
            update(User)
            .where(
                User.id == user_id,
                User.status == UserStatus.PENDING_VERIFICATION,
            )
            .values(
                status=UserStatus.ACTIVE,
                email_verified_at=verified_at,
                updated_at=verified_at,
            )
        )
        result = await self._session.execute(stmt)
        if int(result.rowcount or 0) != 1:  # type: ignore[attr-defined]
            await self._session.rollback()
            raise VerificationCodeExpiredError()
        if commit:
            await self._session.commit()
        else:
            await self._session.flush()
        user = await self._session.get(User, user_id, populate_existing=True)
        if user is None:
            raise UserNotFoundError()
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
        self,
        user_id: int,
        *,
        password_hash: str,
        now: datetime,
        commit: bool = True,
    ) -> UserEntity:
        user = await self._session.get(User, user_id)
        if user is None:
            raise UserNotFoundError()
        user.password_hash = password_hash
        user.updated_at = now
        if commit:
            await self._session.commit()
            await self._session.refresh(user)
        else:
            await self._session.flush()
        return _to_user_entity(user)


class SqlAlchemyVerificationCodeRepository:
    """Implementação SQLAlchemy de `VerificationCodeRepository`"""

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
        next_attempts = EmailVerificationCode.attempts + 1
        stmt = (
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.id == code_id,
                EmailVerificationCode.consumed_at.is_(None),
                EmailVerificationCode.attempts < max_attempts,
                EmailVerificationCode.expires_at > now,
            )
            .values(
                attempts=next_attempts,
                consumed_at=case(
                    (next_attempts >= max_attempts, now),
                    else_=EmailVerificationCode.consumed_at,
                ),
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()
        record = await self._session.get(
            EmailVerificationCode,
            code_id,
            populate_existing=True,
        )
        if record is None:
            raise ValueError(f"Código de verificação {code_id} não encontrado.")
        return _to_code_entity(record)

    async def mark_consumed(
        self,
        code_id: int,
        *,
        consumed_at: datetime,
        max_attempts: int | None = None,
        commit: bool = True,
    ) -> bool:
        conditions = [
            EmailVerificationCode.id == code_id,
            EmailVerificationCode.consumed_at.is_(None),
        ]
        if max_attempts is not None:
            conditions.append(EmailVerificationCode.attempts < max_attempts)
            conditions.append(EmailVerificationCode.expires_at > consumed_at)

        stmt = update(EmailVerificationCode).where(*conditions).values(consumed_at=consumed_at)
        result = await self._session.execute(stmt)
        consumed = int(result.rowcount or 0) == 1  # type: ignore[attr-defined]
        if commit:
            await self._session.commit()
        else:
            await self._session.flush()
        return consumed


class SqlAlchemyRefreshTokenRepository:
    """Implementação SQLAlchemy de `RefreshTokenRepository`"""

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
        revoke_stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.id == current_token_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(revoked_at=now, revoke_reason=RevokeReason.ROTATED)
        )
        result = await self._session.execute(revoke_stmt)
        if int(result.rowcount or 0) != 1:  # type: ignore[attr-defined]
            await self._session.rollback()
            return None

        successor = RefreshToken(
            user_id=user_id,
            token_hash=new_token_hash,
            family_id=family_id,
            expires_at=expires_at,
            revoked_at=None,
            revoke_reason=None,
            created_ip=created_ip,
            user_agent=user_agent,
            created_at=now,
        )
        self._session.add(successor)
        await self._session.commit()
        await self._session.refresh(successor)
        return _to_refresh_entity(successor)

    async def revoke(
        self,
        token_id: int,
        *,
        reason: RevokeReason,
        revoked_at: datetime,
    ) -> None:
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.id == token_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, revoke_reason=reason)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def revoke_all_for_user(
        self,
        user_id: int,
        *,
        reason: RevokeReason,
        revoked_at: datetime,
        exclude_token_hash: str | None = None,
        exclude_family_id: uuid.UUID | None = None,
    ) -> int:
        conditions = [
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        ]
        if exclude_token_hash:
            conditions.append(RefreshToken.token_hash != exclude_token_hash.lower())
        if exclude_family_id is not None:
            conditions.append(RefreshToken.family_id != exclude_family_id)

        stmt = (
            update(RefreshToken)
            .where(*conditions)
            .values(revoked_at=revoked_at, revoke_reason=reason)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
