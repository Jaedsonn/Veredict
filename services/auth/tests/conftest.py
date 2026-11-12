"""Fixtures de teste para o `auth-service` (SQLite em memória + adaptadores determinísticos)."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from auth_service.adapters.clock import FakeClock
from auth_service.adapters.password_hasher import Argon2PasswordHasher
from auth_service.adapters.token_issuer import PyJwtTokenIssuer
from auth_service.config import Settings
from auth_service.main import create_app
from auth_service.models import Base
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import InMemoryNotifier

TEST_INTERNAL_TOKEN = "test-internal-token"
TEST_PEPPER = "test-verification-pepper"


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        service_name="auth",
        internal_api_token=SecretStr(TEST_INTERNAL_TOKEN),
        verification_pepper=SecretStr(TEST_PEPPER),
        verification_code_ttl_minutes=15,
        verification_max_attempts=5,
        verification_resend_cooldown_seconds=60,
        verification_max_resends_per_hour=5,
        access_token_ttl_seconds=900,
        refresh_token_ttl_days=7,
    )


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def audit_logger() -> InMemoryAuditLogger:
    return InMemoryAuditLogger()


@pytest.fixture
def notifier() -> InMemoryNotifier:
    return InMemoryNotifier()


@pytest.fixture(scope="session")
def password_hasher() -> Argon2PasswordHasher:
    # Parâmetros rápidos do Argon2id para suíte de testes mantendo o algoritmo real
    return Argon2PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)


@pytest.fixture
def token_issuer(test_settings: Settings) -> PyJwtTokenIssuer:
    return PyJwtTokenIssuer(
        private_key_pem=test_settings.resolved_jwt_private_key(),
        public_key_pem=test_settings.resolved_jwt_public_key(),
        issuer=test_settings.jwt_issuer,
        audience=test_settings.jwt_audience,
        access_ttl_seconds=test_settings.access_token_ttl_seconds,
        refresh_ttl_days=test_settings.refresh_token_ttl_days,
    )


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    database = Database.__new__(Database)
    database.engine = engine
    database.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    yield database
    await engine.dispose()


@pytest.fixture
async def client(
    test_settings: Settings,
    db: Database,
    fake_clock: FakeClock,
    audit_logger: InMemoryAuditLogger,
    notifier: InMemoryNotifier,
    password_hasher: Argon2PasswordHasher,
    token_issuer: PyJwtTokenIssuer,
) -> AsyncIterator[AsyncClient]:
    app = create_app(
        settings=test_settings,
        db=db,
        audit_logger=audit_logger,
        notifier=notifier,
        clock=fake_clock,
        password_hasher=password_hasher,
        token_issuer=token_issuer,
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c,
    ):
        yield c
