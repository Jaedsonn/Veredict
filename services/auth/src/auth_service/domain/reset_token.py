"""Serviço de domínio do token de redefinição de senha: geração, formato e hash (ADR-008)"""

import hashlib
import re
import secrets
from datetime import datetime, timedelta
from typing import Final

# secrets.token_urlsafe(32): 32 bytes viram 43 caracteres base64url sem padding
TOKEN_BYTES: Final = 32
_TOKEN_RE: Final = re.compile(r"[A-Za-z0-9_-]{43}")


class ResetTokenService:
    """Token de 256 bits no link e só o SHA-256 no banco; tanta entropia dispensa pepper"""

    def __init__(self, *, ttl_minutes: int = 30) -> None:
        if ttl_minutes < 1:
            raise ValueError("PASSWORD_RESET_TTL_MINUTES precisa ser >= 1.")
        self.ttl_minutes = ttl_minutes

    def generate(self) -> tuple[str, str]:
        """Retorna `(token, sha256_hex)`; o token só existe no e-mail"""
        token = secrets.token_urlsafe(TOKEN_BYTES)
        return token, self.hash_token(token)

    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def is_well_formed(self, token: str) -> bool:
        """Recusa antes do banco o que nunca foi gerado aqui (tamanho, alfabeto)"""
        return _TOKEN_RE.fullmatch(token) is not None

    def compute_expiry(self, now: datetime) -> datetime:
        return now + timedelta(minutes=self.ttl_minutes)
