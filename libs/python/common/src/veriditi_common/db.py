from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Nota: não há `Base` declarativa aqui de propósito. Cada serviço define a sua com
# `metadata = make_metadata()`, garantindo um `MetaData` isolado por serviço

# Toda CHECK precisa de `name=`: ele vira o sufixo de `ck_<tabela>_<name>`
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

MYSQL_UTC_INIT_COMMAND = "SET time_zone = '+00:00'"


def make_metadata() -> MetaData:
    """MetaData por serviço com nomes de constraint previsíveis para o Alembic"""
    return MetaData(naming_convention=NAMING_CONVENTION)


def connect_args_for(url: str) -> dict[str, Any]:
    """Sessão MySQL em UTC, independente do fuso configurado no servidor"""
    if url.startswith("mysql"):
        return {"init_command": MYSQL_UTC_INIT_COMMAND}
    return {}


def create_service_engine(url: str, *, echo: bool = False, **kwargs: Any) -> AsyncEngine:
    engine = create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,  # descarta conexões mortas (MySQL fecha após wait_timeout)
        pool_recycle=1800,
        connect_args=connect_args_for(url),
        **kwargs,
    )
    if engine.dialect.name == "sqlite":
        # SQLite ignora FK por padrão; sem isso os testes aceitariam o que o MySQL recusa
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_fks(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


class Database:
    """Encapsula engine + fábrica de sessões de um serviço

    Um objeto por processo: o pool de conexões vive no engine e deve ser
    reaproveitado entre requisições (criar engine por request esgota o MySQL)
    """

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_service_engine(url, echo=echo)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Dependência FastAPI: uma sessão por request, sempre fechada no final"""
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
