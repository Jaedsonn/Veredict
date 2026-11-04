from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Configuração base de qualquer serviço, lida de variáveis de ambiente.

    Todos os serviços compartilham o MESMO banco, então as variáveis DB_*
    são comuns (DB_HOST, DB_NAME, ...). Configs específicas de um serviço
    são declaradas na subclasse dele.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str
    debug: bool = False

    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str
    db_password: SecretStr
    db_name: str

    @property
    def database_url(self) -> str:
        pwd = self.db_password.get_secret_value()
        return (
            f"mysql+aiomysql://{self.db_user}:{pwd}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )
