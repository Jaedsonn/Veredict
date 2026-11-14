import re
import unicodedata
import uuid
from typing import Any, Final, Self

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from gateway_service.domain import InvalidTokenError, Principal
from veriditi_common.logging import get_logger

MAX_TOKEN_LENGTH: Final = 8192
MIN_KEY_BITS: Final = 2048
_ALGORITHMS: Final = ["RS256"]
_REQUIRED: Final = ["exp", "iat", "iss", "aud", "sub"]
# Mesma regra do get_current_user da lib: BIGINT positivo sem zero à esquerda
_USER_ID: Final = re.compile(r"[1-9][0-9]{0,18}")
_MAX_BIGINT: Final = 2**63 - 1
_MAX_EMAIL_LENGTH: Final = 255

# Ordem importa: as subclasses vêm antes de DecodeError e InvalidTokenError
_REASONS: Final[tuple[tuple[type[jwt.PyJWTError], str], ...]] = (
    (jwt.ExpiredSignatureError, "expired"),
    (jwt.ImmatureSignatureError, "immature"),
    (jwt.InvalidSignatureError, "signature"),
    (jwt.InvalidAlgorithmError, "algorithm"),
    (jwt.InvalidIssuerError, "issuer"),
    (jwt.InvalidAudienceError, "audience"),
    (jwt.DecodeError, "malformed"),
)

log = get_logger(__name__)


def load_rsa_public_key(pem: str) -> RSAPublicKey:
    """Carrega uma vez no startup; a mensagem de erro nunca repete a chave"""
    data = pem.replace("\\n", "\n").strip().encode()
    try:
        key = serialization.load_pem_public_key(data)
    except Exception:
        raise ValueError("JWT_PUBLIC_KEY inválido: não é um PEM de chave pública") from None
    if not isinstance(key, RSAPublicKey):
        raise ValueError("JWT_PUBLIC_KEY precisa ser uma chave RSA")
    if key.key_size < MIN_KEY_BITS:
        raise ValueError(f"JWT_PUBLIC_KEY precisa de ao menos {MIN_KEY_BITS} bits")
    return key


def _reject(reason: str) -> InvalidTokenError:
    log.info("jwt_rejected", reason=reason)
    return InvalidTokenError(reason)


def _reason(exc: jwt.PyJWTError) -> str:
    for kind, reason in _REASONS:
        if isinstance(exc, kind):
            return reason
    return "claims"


def _valid_email(value: object) -> str | None:
    """CR/LF no header viraria 500 no h11"""
    if not isinstance(value, str) or not 0 < len(value) <= _MAX_EMAIL_LENGTH:
        return None
    if any(unicodedata.category(char) == "Cc" for char in value):
        return None
    return value


def _principal(claims: dict[str, Any]) -> Principal:
    sub = claims["sub"]
    if not isinstance(sub, str) or not _USER_ID.fullmatch(sub) or int(sub) > _MAX_BIGINT:
        raise _reject("claims")
    email = _valid_email(claims.get("email"))
    if email is None:
        raise _reject("claims")
    sid = claims.get("sid")
    session_id: str | None = None
    if sid is not None:
        try:
            session_id = str(uuid.UUID(sid))
        except (TypeError, ValueError, AttributeError):
            raise _reject("claims") from None
    return Principal(user_id=int(sub), email=email, session_id=session_id)


class RS256JwtVerifier:
    """Só RS256 com a chave carregada: alg none, HS256 e afins caem como algorithm"""

    def __init__(
        self, key: RSAPublicKey, *, issuer: str, audience: str, leeway_seconds: int = 10
    ) -> None:
        self._key = key
        self._issuer = issuer
        self._audience = audience
        self._leeway = leeway_seconds

    @classmethod
    def from_pem(cls, pem: str, *, issuer: str, audience: str, leeway_seconds: int = 10) -> Self:
        return cls(
            load_rsa_public_key(pem),
            issuer=issuer,
            audience=audience,
            leeway_seconds=leeway_seconds,
        )

    def verify(self, token: str) -> Principal:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            raise _reject("malformed")
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=self._key,
                algorithms=_ALGORITHMS,
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={"require": _REQUIRED},
            )
        except jwt.PyJWTError as exc:
            raise _reject(_reason(exc)) from None
        return _principal(claims)
