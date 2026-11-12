from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

_MIN_TOKEN_LENGTH = 16


class BaseServiceSettings(BaseSettings):
    """Configuração comum a todo serviço, inclusive os que não usam banco (gateway)"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str
    debug: bool = False
    log_level: LogLevel = "INFO"
    # Opcional aqui porque os *-migrate e o Alembic não o recebem; o create_app o exige
    internal_api_token: SecretStr | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("internal_api_token", mode="before")
    @classmethod
    def _empty_token_is_missing(cls, value: object) -> object:
        """INTERNAL_API_TOKEN= vazio conta como ausente, não como token curto"""
        return None if value == "" else value

    @field_validator("internal_api_token")
    @classmethod
    def _token_min_length(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < _MIN_TOKEN_LENGTH:
            raise ValueError(
                f"INTERNAL_API_TOKEN precisa de ao menos {_MIN_TOKEN_LENGTH} caracteres"
            )
        return value

    @property
    def internal_token(self) -> SecretStr:
        if self.internal_api_token is None:
            raise RuntimeError("INTERNAL_API_TOKEN não definido")
        return self.internal_api_token


class ServiceSettings(BaseServiceSettings):
    """Serviço com banco: runtime (DB_USER) só com DML e `migrator` com DDL para o Alembic"""

    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "veriditi"  # o monitoring usa "veriditi_logs"
    db_user: str
    db_password: SecretStr | None = None
    db_migrator_user: str | None = None
    db_migrator_password: SecretStr | None = None

    def _url(self, user: str, password: SecretStr) -> str:
        """URL.create escapa @, %, / e : da senha, que quebrariam uma f-string"""
        url = URL.create(
            drivername="mysql+aiomysql",
            username=user,
            password=password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )
        return url.render_as_string(hide_password=False)

    @property
    def database_url(self) -> str:
        if self.db_password is None:
            raise RuntimeError("DB_PASSWORD não definido para o usuário de runtime")
        return self._url(self.db_user, self.db_password)

    @property
    def migration_database_url(self) -> str:
        if self.db_migrator_user is None or self.db_migrator_password is None:
            raise RuntimeError("DB_MIGRATOR_USER e DB_MIGRATOR_PASSWORD são obrigatórios")
        return self._url(self.db_migrator_user, self.db_migrator_password)
