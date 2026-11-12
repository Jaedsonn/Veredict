from functools import lru_cache
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, NameEmail, SecretStr, field_validator, model_validator

from veriditi_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "notification"
    # Porta do make dev; o compose fixa http://monitoring:8000
    monitoring_url: str = "http://localhost:8003"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    # NameEmail recusa CR/LF: o valor vira o header From
    smtp_from: NameEmail = NameEmail("Veriditi", "no-reply@veriditi.app")
    # Mailpit em dev; o provedor do deploy (#17) na 587 exige true
    smtp_starttls: bool = False
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    web_url: str = "http://localhost:3000"

    @field_validator("smtp_user", "smtp_password", mode="before")
    @classmethod
    def _empty_is_missing(cls, value: object) -> object:
        """O compose manda ${SMTP_USER:-}: vazio conta como ausente"""
        return None if value == "" else value

    @field_validator("web_url")
    @classmethod
    def _http_url_without_trailing_slash(cls, value: str) -> str:
        """Base dos links dos e-mails: só http(s) e sem barra final para concatenar a rota"""
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("WEB_URL precisa ser uma URL http(s) absoluta")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _user_requires_password(self) -> Self:
        if self.smtp_user is not None and self.smtp_password is None:
            raise ValueError("SMTP_USER exige SMTP_PASSWORD")
        return self

    @property
    def smtp_from_domain(self) -> str:
        """Domínio do Message-ID: o mesmo do remetente"""
        return self.smtp_from.email.rpartition("@")[2]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
