from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from payment_service.adapters.sandbox_provider import SandboxPixProvider
from payment_service.config import Settings
from payment_service.domain import PixCharge, PixChargeRequest, ProviderError
from payment_service.main import create_app
from payment_service.models import Base, CreditPackageRecord
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.security import INTERNAL_TOKEN_HEADER, USER_EMAIL_HEADER, USER_ID_HEADER

TOKEN = "test-internal-token-0123456789"
START = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)

# O mesmo seed da migration 0001 (D2)
PACKAGES: list[dict[str, Any]] = [
    {"code": "premium", "name": "Premium", "credits": 60, "unit_price_cents": 350,
     "price_cents": 21000, "benefits": "Alto volume.", "highlight": False},
    {"code": "basico", "name": "Básico", "credits": 5, "unit_price_cents": 500,
     "price_cents": 2500, "benefits": "Registros pontuais.", "highlight": False},
    {"code": "medio", "name": "Médio", "credits": 20, "unit_price_cents": 400,
     "price_cents": 8000, "benefits": "Uso frequente.", "highlight": True},
]  # fmt: skip


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


class FlakyProvider:
    """Sandbox que pode ser desligado para simular o provedor fora do ar"""

    name = "sandbox"

    def __init__(self) -> None:
        self.down = False
        self.requests: list[PixChargeRequest] = []
        self._inner = SandboxPixProvider(
            pix_key="pagamentos@veriditi.app", merchant_name="Veriditi", merchant_city="Salvador"
        )

    async def create_pix_charge(self, request: PixChargeRequest) -> PixCharge:
        self.requests.append(request)
        if self.down:
            raise ProviderError("timeout")
        return await self._inner.create_pix_charge(request)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        db_password="test",  # type: ignore[arg-type]
        internal_api_token=TOKEN,  # type: ignore[arg-type]
    )


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(CreditPackageRecord.__table__.insert(), PACKAGES)
    yield database
    await database.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def audit() -> InMemoryAuditLogger:
    return InMemoryAuditLogger()


@pytest.fixture
def provider() -> FlakyProvider:
    return FlakyProvider()


@pytest.fixture
async def app(
    settings: Settings,
    db: Database,
    audit: InMemoryAuditLogger,
    clock: FakeClock,
    provider: FlakyProvider,
) -> AsyncIterator[FastAPI]:
    application = create_app(settings, db, audit, clock=clock, provider=provider)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


UserHeaders = Callable[..., dict[str, str]]


@pytest.fixture
def user_headers() -> UserHeaders:
    """Headers que o gateway injeta depois de validar o JWT"""

    def factory(user_id: int = 7, **extra: str) -> dict[str, str]:
        return {
            INTERNAL_TOKEN_HEADER: TOKEN,
            USER_ID_HEADER: str(user_id),
            USER_EMAIL_HEADER: f"user{user_id}@example.com",
            "X-Forwarded-For": "203.0.113.9",
            **extra,
        }

    return factory


@pytest.fixture
def billing() -> dict[str, Any]:
    return {
        "name": "Ana Maria Souza",
        "email": "Ana@Example.com",
        "phone": "(71) 99876-5432",
        "cpf": "529.982.247-25",
        "cep": "40110-100",
        "street": "Avenida Sete de Setembro",
        "number": "1234",
        "complement": "Sala 5",
        "district": "Centro",
        "city": "Salvador",
        "state": "ba",
    }
