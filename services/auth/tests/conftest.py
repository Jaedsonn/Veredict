"""Fixtures de teste para o `auth-service` (SQLite em memória + adaptadores determinísticos)."""

import base64
import hashlib
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from auth_service.adapters.clock import FakeClock
from auth_service.adapters.password_hasher import Argon2PasswordHasher
from auth_service.adapters.token_issuer import PyJwtTokenIssuer
from auth_service.config import Settings
from auth_service.main import create_app
from auth_service.models import Base, OabKind, OabUf, UserType
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import InMemoryNotifier

TOKEN = "test-internal-token-0123456789"
TEST_INTERNAL_TOKEN = TOKEN
TEST_PEPPER = "test-verification-pepper-0123456789"
TEST_CPF_ENCRYPTION_KEY = base64.b64encode(os.urandom(32)).decode()
TEST_CPF_HMAC_KEY = base64.b64encode(os.urandom(32)).decode()


def make_cpf(seed: int, *, masked: bool = True) -> str:
    """CPF válido e distinto por seed (1 a 10⁸), com os dígitos verificadores calculados"""
    base = f"{seed:09d}"
    if len(set(base)) == 1:
        base = f"{seed + 1:09d}"
    digits = base
    for _ in range(2):
        weights = range(len(digits) + 1, 1, -1)
        total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
        digits += str(total * 10 % 11 % 10)
    if not masked:
        return digits
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def user_columns(
    email: str,
    *,
    name: str = "Usuária",
    user_type: UserType = UserType.COMMON,
    cpf_seed: int | None = None,
    oab: tuple[str, OabUf, OabKind] | None = None,
) -> dict[str, Any]:
    """Colunas obrigatórias de `User` para inserir direto pelo ORM, sem passar pela cifra"""
    seed = cpf_seed if cpf_seed is not None else int(hashlib.sha256(email.encode()).hexdigest(), 16)
    number, uf, kind = oab if oab else (None, None, None)
    return {
        "email": email,
        "name": name,
        "password_hash": "$argon2id$stub",
        "user_type": user_type,
        # 40 bytes como a cifra real; o conteúdo não importa sem o protector
        "cpf_enc": b"\x01" + hashlib.sha256(f"enc:{seed}".encode()).digest() + b"\x00" * 7,
        "cpf_hmac": hashlib.sha256(str(seed).encode()).hexdigest(),
        "oab_number": number,
        "oab_uf": uf,
        "oab_kind": kind,
    }


# Fixtures porque o --import-mode=importlib não deixa os testes importarem módulos auxiliares
@pytest.fixture(scope="session")
def cpf_for() -> Callable[..., str]:
    return make_cpf


@pytest.fixture(scope="session")
def columns_for() -> Callable[..., dict[str, Any]]:
    return user_columns


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return priv_pem, pub_pem


@pytest.fixture
def settings(rsa_keypair: tuple[str, str]) -> Settings:
    priv_pem, pub_pem = rsa_keypair
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        service_name="auth",
        db_user="test",
        db_password=SecretStr("test"),
        internal_api_token=SecretStr(TOKEN),
        verification_pepper=SecretStr(TEST_PEPPER),
        verification_code_ttl_minutes=15,
        verification_max_attempts=5,
        verification_resend_cooldown_seconds=60,
        verification_max_resends_per_hour=5,
        jwt_private_key=SecretStr(priv_pem),
        jwt_public_key=pub_pem,
        access_token_ttl_seconds=900,
        refresh_token_ttl_days=7,
        cpf_encryption_key=SecretStr(TEST_CPF_ENCRYPTION_KEY),
        cpf_hmac_key=SecretStr(TEST_CPF_HMAC_KEY),
    )


@pytest.fixture
def test_settings(settings: Settings) -> Settings:
    return settings


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def audit() -> InMemoryAuditLogger:
    return InMemoryAuditLogger()


@pytest.fixture
def audit_logger(audit: InMemoryAuditLogger) -> InMemoryAuditLogger:
    return audit


@pytest.fixture
def notifier() -> InMemoryNotifier:
    return InMemoryNotifier()


@pytest.fixture(scope="session")
def password_hasher() -> Argon2PasswordHasher:
    # Parâmetros rápidos do Argon2id para suíte de testes mantendo o algoritmo real
    return Argon2PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)


@pytest.fixture
def token_issuer(settings: Settings) -> PyJwtTokenIssuer:
    return PyJwtTokenIssuer(
        private_key_pem=settings.resolved_jwt_private_key(),
        public_key_pem=settings.resolved_jwt_public_key(),
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        access_ttl_seconds=settings.access_token_ttl_seconds,
        refresh_ttl_days=settings.refresh_token_ttl_days,
    )


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
async def client(
    settings: Settings,
    db: Database,
    fake_clock: FakeClock,
    audit: InMemoryAuditLogger,
    notifier: InMemoryNotifier,
    password_hasher: Argon2PasswordHasher,
    token_issuer: PyJwtTokenIssuer,
) -> AsyncIterator[AsyncClient]:
    app = create_app(
        settings=settings,
        db=db,
        audit_logger=audit,
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
        ) as ac,
    ):
        yield ac
