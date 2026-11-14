from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class BaseServiceSettings(BaseSettings):
    """Configuração comum a todo serviço, inclusive os que não usam banco (gateway)"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str
    debug: bool = False


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
