from collections.abc import Callable
from datetime import UTC, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from auth_service.models import (
    EmailVerificationCode,
    OabKind,
    OabUf,
    PasswordResetToken,
    RefreshToken,
    RevokeReason,
    User,
    UserType,
)
from veriditi_common.db import Database
from veriditi_common.db_types import utcnow

Columns = Callable[..., dict[str, Any]]
OAB = ("12345", OabUf.BA, OabKind.PRINCIPAL)


async def test_created_at_comes_from_server_in_utc(db: Database, columns_for: Columns) -> None:
    before = utcnow() - timedelta(seconds=1)
    async with db.session_factory() as session:
        user = User(**columns_for("ana@example.com"))
        session.add(user)
        await session.commit()
        await session.refresh(user)

    assert user.created_at.tzinfo is UTC
    assert before <= user.created_at <= utcnow() + timedelta(seconds=1)


async def test_duplicate_email_is_rejected(db: Database, columns_for: Columns) -> None:
    async with db.session_factory() as session:
        session.add(User(**columns_for("dup@example.com", cpf_seed=1)))
        await session.commit()

        session.add(User(**columns_for("dup@example.com", cpf_seed=2)))
        with pytest.raises(IntegrityError):
            await session.commit()


def test_constraints_follow_naming_convention() -> None:
    user_names = {c.name for c in User.__table__.constraints}
    code_names = {c.name for c in EmailVerificationCode.__table__.constraints}
    refresh_names = {c.name for c in RefreshToken.__table__.constraints}
    reset_names = {c.name for c in PasswordResetToken.__table__.constraints}

    assert {
        "pk_users",
        "uq_users_email",
        "uq_users_cpf_hmac",
        "uq_users_oab_uf_oab_number",
        "ck_users_active_requires_verified",
        "ck_users_oab_matches_type",
    } <= user_names
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


async def test_duplicate_reset_token_hash_is_rejected(db: Database, columns_for: Columns) -> None:
    expires = utcnow() + timedelta(minutes=30)
    async with db.session_factory() as session:
        user = User(**columns_for("rt@example.com"))
        session.add(user)
        await session.flush()
        session.add(PasswordResetToken(user_id=user.id, token_hash="a" * 64, expires_at=expires))
        await session.commit()

        session.add(PasswordResetToken(user_id=user.id, token_hash="A" * 64, expires_at=expires))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_duplicate_cpf_hmac_is_rejected(db: Database, columns_for: Columns) -> None:
    async with db.session_factory() as session:
        session.add(User(**columns_for("a@example.com", cpf_seed=7)))
        await session.commit()

        session.add(User(**columns_for("b@example.com", cpf_seed=7)))
        with pytest.raises(IntegrityError, match="users.cpf_hmac"):
            await session.commit()


async def test_same_oab_number_in_other_uf_is_allowed(db: Database, columns_for: Columns) -> None:
    lawyer = UserType.LAWYER
    async with db.session_factory() as session:
        session.add(User(**columns_for("a@example.com", user_type=lawyer, oab=OAB)))
        session.add(
            User(**columns_for("b@example.com", user_type=lawyer, oab=("12345", OabUf.SP, OAB[2])))
        )
        await session.commit()

        session.add(User(**columns_for("c@example.com", user_type=lawyer, oab=OAB)))
        with pytest.raises(IntegrityError, match="users.oab_uf, users.oab_number"):
            await session.commit()


async def test_many_common_users_have_null_oab(db: Database, columns_for: Columns) -> None:
    async with db.session_factory() as session:
        session.add_all(User(**columns_for(f"u{i}@example.com")) for i in range(3))
        await session.commit()


@pytest.mark.parametrize(
    ("user_type", "oab"),
    [
        (UserType.LAWYER, None),
        (UserType.COMMON, OAB),
        (UserType.LAWYER, ("12345", OabUf.BA, None)),
        (UserType.LAWYER, ("12345", None, OabKind.PRINCIPAL)),
    ],
)
async def test_check_requires_oab_iff_lawyer(
    db: Database, columns_for: Columns, user_type: UserType, oab: Any
) -> None:
    async with db.session_factory() as session:
        session.add(User(**columns_for("x@example.com", user_type=user_type, oab=oab)))
        with pytest.raises(IntegrityError, match="ck_users_oab_matches_type"):
            await session.commit()
