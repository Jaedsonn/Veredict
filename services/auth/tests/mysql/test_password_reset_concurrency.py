"""Corridas do [S2-02] contra MySQL real: link de uso único e forgot x reset sem deadlock"""

import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from auth_service.adapters.clock import SystemClock
from auth_service.adapters.password_hasher import Argon2PasswordHasher
from auth_service.adapters.repositories import (
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyUserRepository,
)
from auth_service.domain.entities import RequestContext
from auth_service.domain.errors import InvalidResetTokenError
from auth_service.domain.password_policy import PasswordPolicy
from auth_service.domain.reset_token import ResetTokenService
from auth_service.models import User
from auth_service.use_cases.password_reset import (
    RequestPasswordReset,
    RequestPasswordResetCommand,
    ResetPassword,
    ResetPasswordCommand,
)
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import InMemoryNotifier

pytestmark = pytest.mark.mysql

EMAIL = "corrida@example.com"
CTX = RequestContext(actor_ip="203.0.113.7")
HASHER = Argon2PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
REPETITIONS = 10


class Harness:
    """Cada chamada abre a própria sessão, como duas requisições em paralelo"""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.notifier = InMemoryNotifier()
        self.audit = InMemoryAuditLogger()
        self.clock = SystemClock()

    async def forgot(self) -> None:
        async with self.db.session_factory() as session:
            await RequestPasswordReset(
                users=SqlAlchemyUserRepository(session),
                reset_tokens=SqlAlchemyPasswordResetTokenRepository(session),
                token_service=ResetTokenService(),
                notifier=self.notifier,
                audit=self.audit,
                clock=self.clock,
            ).execute(RequestPasswordResetCommand(email=EMAIL), CTX)

    async def reset(self, token: str, new_password: str) -> None:
        async with self.db.session_factory() as session:
            await ResetPassword(
                users=SqlAlchemyUserRepository(session),
                reset_tokens=SqlAlchemyPasswordResetTokenRepository(session),
                refresh_tokens=SqlAlchemyRefreshTokenRepository(session),
                token_service=ResetTokenService(),
                hasher=HASHER,
                password_policy=PasswordPolicy(),
                notifier=self.notifier,
                audit=self.audit,
                clock=self.clock,
            ).execute(ResetPasswordCommand(token=token, new_password=new_password), CTX)

    async def forgot_token(self) -> str:
        await self.forgot()
        token = self.notifier.sent[-1].data["token"]
        assert isinstance(token, str)
        return token

    async def password_hash(self) -> str:
        async with self.db.session_factory() as session:
            return str(await session.scalar(select(User.password_hash)))

    def reasons(self, action: str) -> list[object]:
        return [(e.metadata or {}).get("reason") for e in self.audit.events if e.action == action]


@pytest.fixture
async def harness(auth_database_url: str) -> AsyncIterator[Harness]:
    db = Database(auth_database_url)
    clock = SystemClock()
    async with db.session_factory() as session:
        users = SqlAlchemyUserRepository(session)
        user = await users.create(
            email=EMAIL, name="Corrida", password_hash=HASHER.hash("SenhaInicial1"), now=clock.now()
        )
        await users.mark_email_verified(user.id, verified_at=clock.now())
    yield Harness(db)
    await db.dispose()


async def test_same_link_twice_at_once_changes_the_password_once(harness: Harness) -> None:
    for round_ in range(REPETITIONS):
        token = await harness.forgot_token()
        passwords = (f"SenhaA{round_}xyz", f"SenhaB{round_}xyz")

        results = await asyncio.gather(
            *(harness.reset(token, password) for password in passwords),
            return_exceptions=True,
        )

        winners = [p for p, r in zip(passwords, results, strict=True) if r is None]
        losers = [r for r in results if r is not None]
        assert len(winners) == 1, results
        assert len(losers) == 1 and isinstance(losers[0], InvalidResetTokenError), results
        assert HASHER.verify(winners[0], await harness.password_hash())

    assert len(harness.reasons("auth.password.reset_completed")) == REPETITIONS
    # O perdedor relê o token travado: vê o consumo do vencedor, não um falso "expired"
    assert harness.reasons("auth.password.reset_failed") == ["consumed"] * REPETITIONS
    changed = [n for n in harness.notifier.sent if n.template == "password_changed"]
    assert len(changed) == REPETITIONS


async def test_forgot_and_reset_of_the_same_account_never_deadlock(harness: Harness) -> None:
    for round_ in range(REPETITIONS):
        token = await harness.forgot_token()

        results = await asyncio.gather(
            harness.reset(token, f"SenhaC{round_}xyz"),
            harness.forgot(),
            return_exceptions=True,
        )

        # Erro 1213 (deadlock) ou 1205 (lock wait) chegaria aqui como DBAPIError
        assert not any(isinstance(r, DBAPIError) for r in results), results
        reset_result, forgot_result = results
        assert forgot_result is None
        # Quem trava o usuário primeiro vence: ou troca a senha, ou o forgot invalidou o link
        assert reset_result is None or isinstance(reset_result, InvalidResetTokenError)

    assert set(harness.reasons("auth.password.reset_failed")) <= {"consumed"}
