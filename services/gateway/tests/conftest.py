import io
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterable, Iterator, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import jwt
import pytest
import respx
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.types import Message

from gateway_service.adapters.token_bucket import InMemoryTokenBucket
from gateway_service.config import Settings
from gateway_service.domain import InvalidTokenError, Principal, RateDecision, RateLimit
from gateway_service.main import create_app
from veriditi_common.logging import configure_logging

ISSUER = "veriditi-auth"
AUDIENCE = "veriditi"
USER_ID = 42
EMAIL = "ana@exemplo.com"

TOKEN = "test-internal-token-0123456789"
CLIENT_IP = "203.0.113.7"
AUTH = "http://auth.test"

TokenFactory = Callable[..., str]
JsonLogs = Callable[[], list[dict[str, Any]]]
ClientFactory = Callable[[str], AbstractAsyncContextManager[AsyncClient]]


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


class FakeVerifier:
    """Aceita só o token "valido"; guarda o que recebeu"""

    def __init__(self) -> None:
        self.tokens: list[str] = []

    def verify(self, token: str) -> Principal:
        self.tokens.append(token)
        if token != "valido":
            raise InvalidTokenError("signature")
        return Principal(user_id=USER_ID, email=EMAIL)


class RecordingLimiter:
    """Guarda as chaves; nega quando allowed é False"""

    def __init__(self, *, allowed: bool = True, retry_after: int = 12) -> None:
        self.allowed = allowed
        self.retry_after = retry_after
        self.hits: list[tuple[str, RateLimit]] = []

    async def hit(self, key: str, limit: RateLimit) -> RateDecision:
        self.hits.append((key, limit))
        if self.allowed:
            return RateDecision(allowed=True)
        return RateDecision(allowed=False, retry_after=self.retry_after)


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
def settings(rsa_keys: RsaKeys) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        auth_url=AUTH,
        internal_api_token=TOKEN,  # type: ignore[arg-type]
        jwt_public_key=rsa_keys.public_pem_escaped,
        trusted_proxies="10.0.0.0/8",  # type: ignore[arg-type]
        web_url="http://web.test",
    )


@pytest.fixture
async def app(settings: Settings, fake_clock: FakeClock) -> AsyncIterator[FastAPI]:
    application = create_app(settings, rate_limiter=InMemoryTokenBucket(clock=fake_clock))
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
def client_from(app: FastAPI) -> ClientFactory:
    """Cliente com outro IP de origem (o peer da conexão)"""

    def factory(ip: str) -> AbstractAsyncContextManager[AsyncClient]:
        transport = ASGITransport(app=app, client=(ip, 50000))
        return AsyncClient(transport=transport, base_url="http://gateway.test")

    return factory


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from(CLIENT_IP) as ac:
        yield ac


@pytest.fixture
def auth_mock() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=AUTH, assert_all_called=False) as mock:
        yield mock


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: dict[str, str]
    body: bytes


async def raw_request(
    app: FastAPI,
    method: str,
    raw_path: bytes,
    headers: Sequence[tuple[bytes, bytes]] = (),
) -> RawResponse:
    """Scope montado à mão: o httpx normalizaria .. e %2e no cliente"""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": unquote(raw_path.decode("latin-1")),
        "raw_path": raw_path,
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"gateway.test"), *headers],
        "client": (CLIENT_IP, 50000),
        "server": ("gateway.test", 80),
        "state": {},
    }
    sent: list[Message] = []
    done = False

    async def receive() -> Message:
        nonlocal done
        if done:
            return {"type": "http.disconnect"}
        done = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return RawResponse(
        start["status"],
        {k.decode(): v.decode() for k, v in start["headers"]},
        body,
    )


def _reset_logging() -> None:
    root = logging.getLogger()
    for handler in [h for h in root.handlers if h.name == "veriditi"]:
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)
    structlog.reset_defaults()


@pytest.fixture
def reset_logging() -> Iterator[None]:
    """Desfaz o configure_logging, que mexe no root logger e no structlog"""
    yield
    _reset_logging()


@pytest.fixture
def json_logs(reset_logging: None) -> JsonLogs:
    """Saída real com redação; peça depois do app, porque o create_app reconfigura o logging"""
    stream = io.StringIO()
    configure_logging("gateway", stream=stream, level="DEBUG")

    def read() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines()]

    return read
