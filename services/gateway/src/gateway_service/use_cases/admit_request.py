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

log = get_logger(__name__)


def bearer_token(authorization: str | None) -> str:
    """Esquema case-insensitive e um espaço; nada além disso chega ao PyJWT"""
    if not authorization:
        raise InvalidTokenError("missing")
    scheme, sep, token = authorization.partition(" ")
    if not sep or scheme.lower() != "bearer" or not token or " " in token:
        raise InvalidTokenError("malformed")
    return token


def login_email(body: bytes | None) -> str:
    """Mesma normalização do auth; lixo vira "" e ainda conta no limite"""
    if not body:
        return ""
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return ""
    email = data.get("email") if isinstance(data, dict) else None
    return email.strip().lower() if isinstance(email, str) else ""


def rate_key(limit: RateLimit, client_ip: str | None, body: bytes | None) -> str:
    """O hash limita o tamanho da chave e não guarda e-mail em claro na memória"""
    base = client_ip or "unknown"
    if limit.key is RateKey.IP_AND_EMAIL:
        # surrogatepass: um \ud800 solto no JSON não pode virar 500 numa rota pública
        email = login_email(body).encode("utf-8", "surrogatepass")
        digest = hashlib.sha256(email).hexdigest()[:_EMAIL_HASH_CHARS]
        return f"{base}|{digest}"
    return base


class AdmitRequest:
    """Rate limit antes do JWT: uma rajada não gasta CPU de RS256"""

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
        if route.rate_limit is not None:
            limit = route.rate_limit
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
