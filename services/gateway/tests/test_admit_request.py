import hashlib

import pytest
from structlog.testing import capture_logs

from gateway_service.domain import (
    InvalidTokenError,
    Principal,
    RateLimitExceededError,
    Route,
)
from gateway_service.routes import LOGIN_LIMIT, REGISTER_LIMIT, ROUTES
from gateway_service.use_cases.admit_request import (
    AdmitRequest,
    bearer_token,
    login_email,
    rate_key,
)

from .conftest import EMAIL, USER_ID, FakeVerifier, RecordingLimiter

LOGIN = next(r for r in ROUTES if r.path == "/api/auth/login")
REGISTER = next(r for r in ROUTES if r.path == "/api/auth/register")
REFRESH = next(r for r in ROUTES if r.path == "/api/auth/refresh")
ME = next(r for r in ROUTES if r.path == "/api/me")
IP = "203.0.113.7"


@pytest.fixture
def verifier() -> FakeVerifier:
    return FakeVerifier()


@pytest.fixture
def limiter() -> RecordingLimiter:
    return RecordingLimiter()


@pytest.fixture
def admit(limiter: RecordingLimiter, verifier: FakeVerifier) -> AdmitRequest:
    return AdmitRequest(limiter, verifier)


async def _run(
    admit: AdmitRequest, route: Route, authorization: str | None = None, body: bytes | None = None
) -> Principal | None:
    return await admit.execute(route, client_ip=IP, authorization=authorization, body=body)


async def test_public_route_without_limit_touches_nothing(
    admit: AdmitRequest, limiter: RecordingLimiter, verifier: FakeVerifier
) -> None:
    assert await _run(admit, REFRESH) is None
    assert limiter.hits == []
    assert verifier.tokens == []


async def test_public_route_ignores_authorization(
    admit: AdmitRequest, verifier: FakeVerifier
) -> None:
    assert await _run(admit, REFRESH, "Bearer qualquer") is None
    assert verifier.tokens == []


async def test_protected_route_returns_principal(admit: AdmitRequest) -> None:
    principal = await _run(admit, ME, "Bearer valido")

    assert principal == Principal(user_id=USER_ID, email=EMAIL)


async def test_lowercase_scheme_is_accepted(admit: AdmitRequest, verifier: FakeVerifier) -> None:
    assert await _run(admit, ME, "bearer valido") is not None
    assert verifier.tokens == ["valido"]


@pytest.mark.parametrize(
    ("authorization", "reason"),
    [
        (None, "missing"),
        ("", "missing"),
        ("Basic x", "malformed"),
        ("Bearer", "malformed"),
        ("Bearer ", "malformed"),
        ("Bearer a b", "malformed"),
        ("Bearer  valido", "malformed"),
    ],
)
async def test_bad_authorization_never_reaches_verifier(
    admit: AdmitRequest, verifier: FakeVerifier, authorization: str | None, reason: str
) -> None:
    with capture_logs() as logs, pytest.raises(InvalidTokenError) as exc:
        await _run(admit, ME, authorization)

    assert exc.value.reason == reason
    assert verifier.tokens == []
    assert {"event": "jwt_rejected", "reason": reason, "log_level": "info"} in logs


async def test_invalid_token_propagates(admit: AdmitRequest) -> None:
    with pytest.raises(InvalidTokenError):
        await _run(admit, ME, "Bearer outro")


async def test_login_key_normalizes_email(admit: AdmitRequest, limiter: RecordingLimiter) -> None:
    await _run(admit, LOGIN, body=b'{"email": "  Ana@Exemplo.COM ", "password": "x"}')
    await _run(admit, LOGIN, body=b'{"email": "ana@exemplo.com"}')

    [(first, policy), (second, _)] = limiter.hits
    assert first == second
    assert first.startswith(f"{IP}|")
    assert policy is LOGIN_LIMIT


@pytest.mark.parametrize(
    "body", [b"{nao json", b'{"email": 7}', b"", None, b"[1]", b"\xff\xfe", b"[" * 5000]
)
def test_unusable_body_counts_as_empty_email(body: bytes | None) -> None:
    assert login_email(body) == ""
    empty = hashlib.sha256(b"").hexdigest()[:32]
    assert rate_key(LOGIN_LIMIT, IP, body) == f"{IP}|{empty}"


async def test_register_key_is_only_ip(admit: AdmitRequest, limiter: RecordingLimiter) -> None:
    await _run(admit, REGISTER, body=b'{"email": "ana@exemplo.com"}')

    assert limiter.hits == [(IP, REGISTER_LIMIT)]


def test_missing_ip_uses_unknown() -> None:
    assert rate_key(REGISTER_LIMIT, None, None) == "unknown"
    assert rate_key(LOGIN_LIMIT, None, None).startswith("unknown|")


def test_rate_key_has_no_plain_email() -> None:
    key = rate_key(LOGIN_LIMIT, IP, b'{"email": "ana@exemplo.com"}')

    assert "ana" not in key
    assert "@" not in key


async def test_limit_is_checked_before_jwt(verifier: FakeVerifier) -> None:
    limited_me = Route("/api/me", "auth", "/me", public=False, rate_limit=REGISTER_LIMIT)
    admit = AdmitRequest(RecordingLimiter(allowed=False, retry_after=6), verifier)

    with capture_logs() as logs, pytest.raises(RateLimitExceededError) as exc:
        await admit.execute(limited_me, client_ip=IP, authorization="Bearer x", body=None)

    assert (exc.value.policy, exc.value.retry_after) == ("register", 6)
    assert verifier.tokens == []
    assert logs == [
        {"event": "rate_limited", "policy": "register", "retry_after": 6, "log_level": "warning"}
    ]


def test_bearer_token_extracts_token() -> None:
    assert bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"
    assert bearer_token("BEARER abc") == "abc"


def test_lone_surrogate_in_email_still_builds_a_key() -> None:
    body = b'{"email": "a\\ud800@x.com", "password": "p"}'

    key = rate_key(LOGIN_LIMIT, IP, body)

    assert key.startswith(f"{IP}|")
    assert key != rate_key(LOGIN_LIMIT, IP, b'{"email": "a@x.com"}')
