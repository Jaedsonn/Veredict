from datetime import UTC, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from auth_service.models import EmailVerificationCode, RefreshToken, User
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
