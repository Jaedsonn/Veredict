from collections.abc import Callable
from typing import Protocol

from gateway_service.domain import Principal, RateDecision, RateLimit

Clock = Callable[[], float]


class JwtVerifier(Protocol):
    def verify(self, token: str) -> Principal:
        """Levanta InvalidTokenError; síncrono porque RS256 custa microssegundos"""
        ...


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: RateLimit) -> RateDecision:
        """Consome uma ficha se houver; assíncrono para o adapter Redis da Sprint 2"""
        ...
