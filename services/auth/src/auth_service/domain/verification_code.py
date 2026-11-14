"""Serviço de domínio para geração, hash HMAC-SHA256 e validação de códigos de 6 dígitos"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta


class VerificationCodeService:
    """Gera códigos numéricos de 6 dígitos e calcula/compara HMAC-SHA256 em tempo constante

    Separado de `VerifyEmail`: cuida só da criptografia e do formato do código (ADR-007 / #8).
    """

    def __init__(
        self,
        pepper: str,
        *,
        ttl_minutes: int = 15,
        max_attempts: int = 5,
    ) -> None:
        if not pepper:
            raise ValueError("VERIFICATION_PEPPER não pode ser vazio.")
        self._pepper_bytes = pepper.encode("utf-8")
        self.ttl_minutes = ttl_minutes
        self.max_attempts = max_attempts

    def generate_code(self) -> str:
        """Gera um código numérico de 6 dígitos criptograficamente seguro (`secrets.randbelow`)"""
        return f"{secrets.randbelow(1_000_000):06d}"

    def hash_code(self, code: str) -> str:
        """Calcula o HMAC-SHA256 (hex minúsculo de 64 caracteres) usando `VERIFICATION_PEPPER`"""
        return hmac.new(
            self._pepper_bytes,
            code.strip().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_code(self, candidate_code: str, expected_hash: str) -> bool:
        """Compara o código candidato contra o hash esperado (`hmac.compare_digest`)"""
        candidate_hash = self.hash_code(candidate_code)
        return hmac.compare_digest(candidate_hash, expected_hash.lower())

    def compute_expiry(self, now: datetime) -> datetime:
        """Retorna a data/hora de expiração a partir do instante atual"""
        return now + timedelta(minutes=self.ttl_minutes)
