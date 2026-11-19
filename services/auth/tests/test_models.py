from datetime import UTC, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from auth_service.models import (
    EmailVerificationCode,
    PasswordResetToken,
    RefreshToken,
    RevokeReason,
    User,
)
from veriditi_common.db import Database
from veriditi_common.db_types import utcnow


async def test_created_at_comes_from_server_in_utc(db: Database) -> None:
    before = utcnow() - timedelta(seconds=1)
    async with db.session_factory() as session:
        user = User(email="ana@example.com", name="Ana", password_hash="$argon2id$stub")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    assert user.created_at.tzinfo is UTC
    assert before <= user.created_at <= utcnow() + timedelta(seconds=1)


async def test_duplicate_email_is_rejected(db: Database) -> None:
    async with db.session_factory() as session:
        session.add(User(email="dup@example.com", name="A", password_hash="$argon2id$stub"))
        await session.commit()

        session.add(User(email="dup@example.com", name="B", password_hash="$argon2id$stub"))
        with pytest.raises(IntegrityError):
            await session.commit()


def test_constraints_follow_naming_convention() -> None:
    user_names = {c.name for c in User.__table__.constraints}
    code_names = {c.name for c in EmailVerificationCode.__table__.constraints}
    refresh_names = {c.name for c in RefreshToken.__table__.constraints}
    reset_names = {c.name for c in PasswordResetToken.__table__.constraints}

    assert {"pk_users", "uq_users_email", "ck_users_active_requires_verified"} <= user_names
    assert {
        "pk_email_verification_codes",
        "fk_email_verification_codes_user_id_users",
        "ck_email_verification_codes_attempts_non_negative",
    } <= code_names
    assert {
        "pk_refresh_tokens",
        "uq_refresh_tokens_token_hash",
        "fk_refresh_tokens_user_id_users",
        "ck_refresh_tokens_revocation_consistent",
    } <= refresh_names
    assert {
        "pk_password_reset_tokens",
        "uq_password_reset_tokens_token_hash",
        "fk_password_reset_tokens_user_id_users",
    } <= reset_names
    assert {ix.name for ix in PasswordResetToken.__table__.indexes} == {
        "ix_password_reset_tokens_user_id_consumed_at"
    }


def test_password_reset_is_the_last_revoke_reason() -> None:
    # Acrescentar no fim do ENUM é o ALTER instantâneo da migration 0005
    assert list(RevokeReason)[-1] is RevokeReason.PASSWORD_RESET


async def test_duplicate_reset_token_hash_is_rejected(db: Database) -> None:
    expires = utcnow() + timedelta(minutes=30)
    async with db.session_factory() as session:
        user = User(email="rt@example.com", name="Rt", password_hash="$argon2id$stub")
        session.add(user)
        await session.flush()
        session.add(PasswordResetToken(user_id=user.id, token_hash="a" * 64, expires_at=expires))
        await session.commit()

        session.add(PasswordResetToken(user_id=user.id, token_hash="A" * 64, expires_at=expires))
        with pytest.raises(IntegrityError):
            await session.commit()
