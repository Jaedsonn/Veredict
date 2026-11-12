import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from gateway_service.config import Settings
from gateway_service.main import create_app

ISSUER = "veriditi-auth"
AUDIENCE = "veriditi"
USER_ID = 42
EMAIL = "ana@exemplo.com"

TokenFactory = Callable[..., str]


@dataclass(frozen=True)
class RsaKeys:
    private: rsa.RSAPrivateKey
    public: rsa.RSAPublicKey
    public_pem: str
    # Como o make keys grava no .env: uma linha com \n literal
    public_pem_escaped: str


class FakeClock:
    """Relógio monotônico controlado pelo teste, sem sleep real"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


def _rsa_keys() -> RsaKeys:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    pem = public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return RsaKeys(private, public, pem, pem.strip().replace("\n", "\\n"))


@pytest.fixture(scope="session")
def rsa_keys() -> RsaKeys:
    return _rsa_keys()


@pytest.fixture(scope="session")
def intruder_key() -> rsa.RSAPrivateKey:
    return _rsa_keys().private


@pytest.fixture
def make_token(rsa_keys: RsaKeys) -> TokenFactory:
    """Claims no formato exato do PyJwtTokenIssuer do auth (#54)"""

    def factory(
        *,
        drop: Iterable[str] = (),
        headers: dict[str, Any] | None = None,
        key: Any = None,
        algorithm: str = "RS256",
        **overrides: Any,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": str(USER_ID),
            "email": EMAIL,
            "iat": now,
            "exp": now + 900,
            "jti": str(uuid.uuid4()),
            "iss": ISSUER,
            "aud": AUDIENCE,
        }
        claims.update(overrides)
        for name in drop:
            claims.pop(name, None)
        return jwt.encode(
            claims, key if key is not None else rsa_keys.private, algorithm, headers=headers
        )

    return factory


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, auth_url="http://auth.test")  # type: ignore[call-arg]
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
