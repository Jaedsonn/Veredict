"""Configurações do serviço de Autenticação (IAM)"""

from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from pydantic import SecretStr, field_validator

from veriditi_common.settings import ServiceSettings

_MIN_SECRET_LENGTH = 16


class Settings(ServiceSettings):
    """Configurações de ambiente do `auth-service`"""

    service_name: str = "auth"
    db_user: str = "auth_svc"

    # Portas do `make dev`; no compose são fixadas em http://monitoring:8000 e http://notification:8000
    monitoring_url: str = "http://localhost:8003"
    notification_url: str = "http://localhost:8002"

    verification_pepper: SecretStr = SecretStr("change-me-verification-pepper")
    verification_code_ttl_minutes: int = 15
    verification_max_attempts: int = 5
    verification_resend_cooldown_seconds: int = 60
    verification_max_resends_per_hour: int = 5

    # Opcionais na instanciação porque o container `auth-migrate` (Alembic) não recebe chaves JWT;
    # `create_app` exige `jwt_private_key_pem` em fail-fast na subida do serviço HTTP.
    jwt_private_key: SecretStr | None = None
    jwt_public_key: str | None = None
    jwt_issuer: str = "veriditi-auth"
    jwt_audience: str = "veriditi"
    access_token_ttl_seconds: int = 900  # 15 min (#9)
    refresh_token_ttl_days: int = 7  # 7 dias (#9)

    @field_validator("jwt_private_key", "jwt_public_key", "verification_pepper", mode="before")
    @classmethod
    def _empty_str_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def pepper(self) -> str:
        """Retorna o pepper do HMAC-SHA256 validando tamanho mínimo em fail-fast"""
        if self.verification_pepper is None:
            raise RuntimeError("VERIFICATION_PEPPER não definido")
        raw = self.verification_pepper.get_secret_value().strip()
        if len(raw) < _MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"VERIFICATION_PEPPER precisa de ao menos {_MIN_SECRET_LENGTH} caracteres"
            )
        return raw

    def resolved_jwt_private_key(self) -> str:
        """Retorna a chave privada RSA em formato PEM; falha na subida se ausente (#9)"""
        if self.jwt_private_key is None:
            raise RuntimeError("JWT_PRIVATE_KEY não definido (gere o par com `make keys`)")
        pem = self.jwt_private_key.get_secret_value().strip().replace("\\n", "\n")
        if not pem:
            raise RuntimeError("JWT_PRIVATE_KEY não definido (gere o par com `make keys`)")
        return pem

    def resolved_jwt_public_key(self) -> str:
        """Retorna a chave pública RSA em PEM (configurada ou derivada da chave privada)"""
        if self.jwt_public_key is not None and self.jwt_public_key.strip():
            return self.jwt_public_key.strip().replace("\\n", "\n")
        private_pem = self.resolved_jwt_private_key()
        private_key = serialization.load_pem_private_key(
            private_pem.encode("utf-8"),
            password=None,
        )
        return (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
