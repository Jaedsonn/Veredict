"""Configurações do serviço de Autenticação (IAM)."""

from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from veriditi_common.settings import ServiceSettings


@lru_cache(maxsize=1)
def _generate_dev_rsa_keypair() -> tuple[str, str]:
    """Gera um par de chaves RSA-2048 efêmero para desenvolvimento/testes locais."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return priv_pem, pub_pem


class Settings(ServiceSettings):
    """Configurações de ambiente do `auth-service`."""

    service_name: str = "auth"
    db_user: str = "auth_svc"
    db_password: SecretStr | None = SecretStr("change-me-auth")

    internal_api_token: SecretStr = SecretStr("dev-internal-token-change-me")
    monitoring_url: str = "http://monitoring:8000"
    notification_url: str = "http://notification:8000"

    verification_pepper: SecretStr = SecretStr("dev-verification-pepper-change-me")
    verification_code_ttl_minutes: int = 15
    verification_max_attempts: int = 5
    verification_resend_cooldown_seconds: int = 60
    verification_max_resends_per_hour: int = 5

    jwt_private_key: SecretStr | None = None
    jwt_public_key: str | None = None
    jwt_issuer: str = "veriditi-auth"
    jwt_audience: str = "veriditi"
    access_token_ttl_seconds: int = 900  # 15 min (#9)
    refresh_token_ttl_days: int = 7  # 7 dias (#9)

    def resolved_jwt_private_key(self) -> str:
        if self.jwt_private_key is not None and self.jwt_private_key.get_secret_value().strip():
            return self.jwt_private_key.get_secret_value().replace("\\n", "\n")
        priv_pem, _ = _generate_dev_rsa_keypair()
        return priv_pem

    def resolved_jwt_public_key(self) -> str:
        if self.jwt_public_key is not None and self.jwt_public_key.strip():
            return self.jwt_public_key.replace("\\n", "\n")
        _, pub_pem = _generate_dev_rsa_keypair()
        return pub_pem


@lru_cache
def get_settings() -> Settings:
    return Settings()
