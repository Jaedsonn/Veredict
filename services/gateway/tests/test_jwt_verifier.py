import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from structlog.testing import capture_logs

from gateway_service.adapters.jwt_verifier import (
    MAX_TOKEN_LENGTH,
    RS256JwtVerifier,
    load_rsa_public_key,
)
from gateway_service.domain import InvalidTokenError, Principal

from .conftest import AUDIENCE, EMAIL, ISSUER, USER_ID, RsaKeys, TokenFactory


@pytest.fixture
def verifier(rsa_keys: RsaKeys) -> RS256JwtVerifier:
    return RS256JwtVerifier(rsa_keys.public, issuer=ISSUER, audience=AUDIENCE)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims = {"sub": "42", "email": EMAIL, "iat": now, "exp": now + 900}
    return {**claims, "iss": ISSUER, "aud": AUDIENCE, **overrides}


def _unsigned(header: dict[str, Any], claims: dict[str, Any]) -> str:
    return f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"


def _reason(verifier: RS256JwtVerifier, token: str) -> str:
    with pytest.raises(InvalidTokenError) as exc:
        verifier.verify(token)
    return exc.value.reason


def test_valid_token(verifier: RS256JwtVerifier, make_token: TokenFactory) -> None:
    principal = verifier.verify(make_token())

    assert principal == Principal(user_id=USER_ID, email=EMAIL, session_id=None)
    assert EMAIL not in repr(principal)


def test_sid_is_normalized(verifier: RS256JwtVerifier, make_token: TokenFactory) -> None:
    sid = uuid.uuid4()

    principal = verifier.verify(make_token(sid=str(sid).upper()))

    assert principal.session_id == str(sid)


def test_expired_within_leeway_is_accepted(
    verifier: RS256JwtVerifier, make_token: TokenFactory
) -> None:
    now = int(time.time())

    assert verifier.verify(make_token(iat=now - 900, exp=now - 5)).user_id == USER_ID


def test_audience_list_with_ours_is_accepted(
    verifier: RS256JwtVerifier, make_token: TokenFactory
) -> None:
    assert verifier.verify(make_token(aud=["outro", AUDIENCE])).user_id == USER_ID


def test_unknown_kid_and_jku_are_ignored(
    verifier: RS256JwtVerifier, make_token: TokenFactory
) -> None:
    token = make_token(headers={"kid": "desconhecido", "jku": "http://evil.test/jwks"})

    assert verifier.verify(token).user_id == USER_ID


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"exp": int(time.time()) - 30}, "expired"),
        ({"iat": int(time.time()) + 60}, "immature"),
        ({"nbf": int(time.time()) + 60}, "immature"),
        ({"iss": "outro"}, "issuer"),
        ({"aud": "outro"}, "audience"),
        ({"aud": ["a", "b"]}, "audience"),
    ],
)
def test_rejected_claims(
    verifier: RS256JwtVerifier,
    make_token: TokenFactory,
    overrides: dict[str, Any],
    reason: str,
) -> None:
    assert _reason(verifier, make_token(**overrides)) == reason


@pytest.mark.parametrize("claim", ["exp", "iat", "iss", "aud", "sub"])
def test_missing_required_claim(
    verifier: RS256JwtVerifier, make_token: TokenFactory, claim: str
) -> None:
    assert _reason(verifier, make_token(drop=(claim,))) == "claims"


def test_signature_from_other_key(
    verifier: RS256JwtVerifier, make_token: TokenFactory, intruder_key: rsa.RSAPrivateKey
) -> None:
    assert _reason(verifier, make_token(key=intruder_key)) == "signature"


def test_tampered_payload(verifier: RS256JwtVerifier, make_token: TokenFactory) -> None:
    header, _, signature = make_token().split(".")
    forged = _b64(json.dumps(_claims(sub="1")).encode())

    assert _reason(verifier, f"{header}.{forged}.{signature}") == "signature"


def test_alg_none(verifier: RS256JwtVerifier) -> None:
    token = _unsigned({"alg": "none", "typ": "JWT"}, _claims()) + "."

    assert _reason(verifier, token) == "algorithm"


def test_hs256_with_public_pem_as_secret(verifier: RS256JwtVerifier, rsa_keys: RsaKeys) -> None:
    signing_input = _unsigned({"alg": "HS256", "typ": "JWT"}, _claims())
    mac = hmac.new(rsa_keys.public_pem.encode(), signing_input.encode(), hashlib.sha256)
    token = f"{signing_input}.{_b64(mac.digest())}"

    assert _reason(verifier, token) == "algorithm"


@pytest.mark.parametrize("algorithm", ["RS512", "PS256"])
def test_other_rsa_algorithms_with_right_key(
    verifier: RS256JwtVerifier, make_token: TokenFactory, algorithm: str
) -> None:
    assert _reason(verifier, make_token(algorithm=algorithm)) == "algorithm"


def test_es256(verifier: RS256JwtVerifier, make_token: TokenFactory) -> None:
    key = ec.generate_private_key(ec.SECP256R1())

    assert _reason(verifier, make_token(key=key, algorithm="ES256")) == "algorithm"


@pytest.mark.parametrize(
    "token",
    ["", "lixo", "a.b.c", "não.é.base64", "x" * (MAX_TOKEN_LENGTH + 1)],
)
def test_malformed(verifier: RS256JwtVerifier, token: str) -> None:
    assert _reason(verifier, token) == "malformed"


def test_truncated(verifier: RS256JwtVerifier, make_token: TokenFactory) -> None:
    token = make_token()

    assert _reason(verifier, token[: len(token) // 2]) in {"malformed", "signature"}


@pytest.mark.parametrize("sub", [42, "0", "-1", "abc", "01", str(2**63), " 1", ""])
def test_invalid_sub(verifier: RS256JwtVerifier, make_token: TokenFactory, sub: object) -> None:
    assert _reason(verifier, make_token(sub=sub)) == "claims"


def test_max_bigint_sub_is_accepted(verifier: RS256JwtVerifier, make_token: TokenFactory) -> None:
    assert verifier.verify(make_token(sub=str(2**63 - 1))).user_id == 2**63 - 1


@pytest.mark.parametrize("email", [None, 7, "", "a" * 256, "ana@x.com\r\nX-User-Id: 1"])
def test_invalid_email(verifier: RS256JwtVerifier, make_token: TokenFactory, email: object) -> None:
    token = make_token(drop=("email",)) if email is None else make_token(email=email)

    assert _reason(verifier, token) == "claims"


def test_unicode_email_is_accepted(verifier: RS256JwtVerifier, make_token: TokenFactory) -> None:
    assert verifier.verify(make_token(email="joão@exemplo.com")).email == "joão@exemplo.com"


@pytest.mark.parametrize("sid", ["nao-uuid", 7, ""])
def test_invalid_sid(verifier: RS256JwtVerifier, make_token: TokenFactory, sid: object) -> None:
    assert _reason(verifier, make_token(sid=sid)) == "claims"


def test_rejection_is_logged_with_reason_only(
    verifier: RS256JwtVerifier, make_token: TokenFactory
) -> None:
    token = make_token(exp=int(time.time()) - 60)

    with capture_logs() as logs:
        _reason(verifier, token)

    assert logs == [{"event": "jwt_rejected", "reason": "expired", "log_level": "info"}]


def test_leeway_is_configurable(rsa_keys: RsaKeys, make_token: TokenFactory) -> None:
    strict = RS256JwtVerifier(rsa_keys.public, issuer=ISSUER, audience=AUDIENCE, leeway_seconds=0)
    now = int(time.time())

    assert _reason(strict, make_token(iat=now - 900, exp=now - 5)) == "expired"


def test_from_pem_accepts_escaped_newlines(rsa_keys: RsaKeys, make_token: TokenFactory) -> None:
    verifier = RS256JwtVerifier.from_pem(
        rsa_keys.public_pem_escaped, issuer=ISSUER, audience=AUDIENCE
    )

    assert verifier.verify(make_token()).user_id == USER_ID


def test_load_accepts_real_pem(rsa_keys: RsaKeys) -> None:
    assert load_rsa_public_key(rsa_keys.public_pem).public_numbers() == (
        rsa_keys.public.public_numbers()
    )


def _pem(key: Any) -> str:
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


@pytest.mark.parametrize(
    ("make_pem", "message"),
    [
        (lambda: "-----BEGIN PUBLIC KEY-----\nlixo\n-----END PUBLIC KEY-----", "PEM"),
        (lambda: "não é pem", "PEM"),
        (lambda: _pem(ec.generate_private_key(ec.SECP256R1())), "RSA"),
        (lambda: _pem(rsa.generate_private_key(public_exponent=65537, key_size=1024)), "2048"),
    ],
)
def test_load_rejects_bad_keys_without_echoing(make_pem: Any, message: str) -> None:
    pem = make_pem()

    with pytest.raises(ValueError, match=message) as exc:
        load_rsa_public_key(pem)

    assert pem not in str(exc.value)
    assert "lixo" not in str(exc.value)


def test_load_rejects_private_key_pasted_as_public(rsa_keys: RsaKeys) -> None:
    private_pem = rsa_keys.private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    with pytest.raises(ValueError, match="PEM") as exc:
        load_rsa_public_key(private_pem)

    assert "PRIVATE" not in str(exc.value)
