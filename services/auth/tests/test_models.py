from datetime import UTC, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from auth_service.models import User
from veriditi_common.db import Database
from veriditi_common.db_types import utcnow


async def test_created_at_comes_from_server_in_utc(db: Database) -> None:
    before = utcnow() - timedelta(seconds=1)
    async with db.session_factory() as session:
        user = User(email="ana@example.com", name="Ana")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    assert user.created_at.tzinfo is UTC
    assert before <= user.created_at <= utcnow() + timedelta(seconds=1)


async def test_duplicate_email_is_rejected(db: Database) -> None:
    async with db.session_factory() as session:
        session.add(User(email="dup@example.com", name="A"))
        await session.commit()

        session.add(User(email="dup@example.com", name="B"))
        with pytest.raises(IntegrityError):
            await session.commit()


def test_constraints_follow_naming_convention() -> None:
    names = {c.name for c in User.__table__.constraints}

    assert {"pk_users", "uq_users_email"} <= names
