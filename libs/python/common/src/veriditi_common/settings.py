from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Configuração base de qualquer serviço, lida de variáveis de ambiente.

    Um único servidor MySQL guarda dois bancos: `veriditi` (central) e
    `veriditi_logs` (só o monitoring). Cada serviço conecta com DOIS usuários
    (ver `docs/banco-de-dados.md`, seção "Usuários e privilégios"):

    - runtime (`DB_USER`/`DB_PASSWORD`): exclusivo do serviço, só com DML nas
      tabelas que ele possui (ex.: `auth_svc`);
    - migração (`DB_MIGRATOR_USER`/`DB_MIGRATOR_PASSWORD`): `migrator`, com DDL,
      usado apenas pelo Alembic.

    Cada container recebe as próprias variáveis `DB_*`; o compose faz o
    mapeamento (ex.: `AUTH_DB_PASSWORD` -> `DB_PASSWORD` do container auth).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str
    debug: bool = False

    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "veriditi"
    db_user: str
    db_password: SecretStr | None = None
    db_migrator_user: str | None = None
    db_migrator_password: SecretStr | None = None

    def _url(self, user: str, password: SecretStr) -> str:
        pwd = password.get_secret_value()
        return (
            f"mysql+aiomysql://{user}:{pwd}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def database_url(self) -> str:
        """URL do usuário de runtime (o que a aplicação usa em cada request)."""
        if self.db_password is None:
            raise RuntimeError("DB_PASSWORD não definido para o usuário de runtime")
        return self._url(self.db_user, self.db_password)

    @property
    def migration_database_url(self) -> str:
        """URL do usuário `migrator` (DDL), usada somente pelo `env.py` do Alembic."""
        if self.db_migrator_user is None or self.db_migrator_password is None:
            raise RuntimeError("DB_MIGRATOR_USER e DB_MIGRATOR_PASSWORD são obrigatórios")
        return self._url(self.db_migrator_user, self.db_migrator_password)
