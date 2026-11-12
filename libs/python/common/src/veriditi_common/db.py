from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Nota: não há `Base` declarativa aqui de propósito. Cada serviço define a sua,
# garantindo um `MetaData` isolado (o Alembic de um serviço só enxerga suas tabelas).
# O que é compartilhado é a CONVENÇÃO de nomes, via `make_metadata()`:
#
#     class Base(DeclarativeBase):
#         metadata = make_metadata()

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Nomes previsíveis de constraints/índices (ver `docs/banco-de-dados.md`).

Sem isso, o MySQL inventa nomes (`users_ibfk_1`) e o `alembic --autogenerate`
não consegue comparar nem remover constraints de forma confiável. Toda CHECK
precisa de `name=` explícito: ele vira o sufixo de `ck_<tabela>_<name>`.
"""

MYSQL_UTC_INIT_COMMAND = "SET time_zone = '+00:00'"


def make_metadata() -> MetaData:
    """`MetaData` novo (um por serviço) já com a convenção de nomes do projeto."""
    return MetaData(naming_convention=NAMING_CONVENTION)


def connect_args_for(url: str) -> dict[str, Any]:
    """Argumentos de conexão por driver.

    No MySQL, toda conexão nova roda `SET time_zone = '+00:00'`. Assim
    `CURRENT_TIMESTAMP(6)` e `NOW()` ficam em UTC mesmo que o servidor esteja
    configurado com outro fuso (é a camada "sessão" da garantia de UTC).
    """
    if url.startswith("mysql"):
        return {"init_command": MYSQL_UTC_INIT_COMMAND}
    return {}


def create_service_engine(url: str, *, echo: bool = False, **kwargs: Any) -> AsyncEngine:
    """Engine assíncrono com os padrões do projeto (pool, UTC e FKs no SQLite)."""
    engine = create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,  # descarta conexões mortas (MySQL fecha após wait_timeout)
        pool_recycle=1800,
        connect_args=connect_args_for(url),
        **kwargs,
    )
    if engine.dialect.name == "sqlite":
        # O SQLite ignora FOREIGN KEY por padrão. Sem isso, os testes passariam
        # com dados que o MySQL recusaria.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_fks(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


class Database:
    """Encapsula engine + fábrica de sessões de um serviço.

    Um objeto por processo: o pool de conexões vive no engine e deve ser
    reaproveitado entre requisições (criar engine por request esgota o MySQL).
    """

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_service_engine(url, echo=echo)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Dependência FastAPI: uma sessão por request, sempre fechada no final."""
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
