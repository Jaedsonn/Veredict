from typing import Protocol

from gateway_service.domain import Principal


class JwtVerifier(Protocol):
    def verify(self, token: str) -> Principal:
        """Levanta InvalidTokenError; síncrono porque RS256 custa microssegundos"""
        ...
