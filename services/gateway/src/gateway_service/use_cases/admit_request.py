import hashlib
import json
from typing import Final

from gateway_service.domain import (
    InvalidTokenError,
    Principal,
    RateKey,
    RateLimit,
    RateLimitExceededError,
    Route,
)
from gateway_service.ports import JwtVerifier, RateLimiter
from veriditi_common.logging import get_logger

_EMAIL_HASH_CHARS: Final = 32
_EMAIL_KEYS: Final = frozenset({RateKey.IP_AND_EMAIL, RateKey.EMAIL})

log = get_logger(__name__)


def bearer_token(authorization: str | None) -> str:
    """Esquema case-insensitive e um espaço; nada além disso chega ao PyJWT"""
    if not authorization:
        raise InvalidTokenError("missing")
    scheme, sep, token = authorization.partition(" ")
    if not sep or scheme.lower() != "bearer" or not token or " " in token:
        raise InvalidTokenError("malformed")
    return token


def body_email(body: bytes | None) -> str:
    """Mesma normalização do auth; lixo vira "" e ainda conta no limite"""
    if not body:
        return ""
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return ""
    email = data.get("email") if isinstance(data, dict) else None
    return email.strip().lower() if isinstance(email, str) else ""


def needs_body(route: Route) -> bool:
    """Só rota com limite por e-mail precisa do corpo antes do upstream"""
    return any(limit.key in _EMAIL_KEYS for limit in route.rate_limits)


def _email_digest(body: bytes | None) -> str:
    """O hash limita o tamanho da chave e não guarda e-mail em claro na memória"""
    # surrogatepass: um \ud800 solto no JSON não pode virar 500 numa rota pública
    email = body_email(body).encode("utf-8", "surrogatepass")
    return hashlib.sha256(email).hexdigest()[:_EMAIL_HASH_CHARS]


def rate_key(limit: RateLimit, client_ip: str | None, body: bytes | None) -> str:
    base = client_ip or "unknown"
    if limit.key is RateKey.IP_AND_EMAIL:
        return f"{base}|{_email_digest(body)}"
    if limit.key is RateKey.EMAIL:
        return _email_digest(body)
    return base


class AdmitRequest:
    """Rate limit antes do JWT: uma rajada não gasta CPU de RS256

    Os limites rodam em ordem e param no primeiro que nega: o de IP vem antes e consome a
    ficha mesmo quando o de e-mail nega, e um IP já bloqueado não gasta a ficha do e-mail.
    """

    def __init__(self, limiter: RateLimiter, verifier: JwtVerifier) -> None:
        self._limiter = limiter
        self._verifier = verifier

    async def execute(
        self,
        route: Route,
        *,
        client_ip: str | None,
        authorization: str | None,
        body: bytes | None,
    ) -> Principal | None:
        for limit in route.rate_limits:
            decision = await self._limiter.hit(rate_key(limit, client_ip, body), limit)
            if not decision.allowed:
                log.warning("rate_limited", policy=limit.name, retry_after=decision.retry_after)
                raise RateLimitExceededError(limit.name, decision.retry_after)
        if route.public:
            return None
        try:
            token = bearer_token(authorization)
        except InvalidTokenError as exc:
            log.info("jwt_rejected", reason=exc.reason)
            raise
        return self._verifier.verify(token)
