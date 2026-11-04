from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Nota: não há `Base` declarativa aqui de propósito. Cada serviço define a sua,
# garantindo um `MetaData` isolado (o Alembic de um serviço só enxerga suas tabelas).


class Database:
    """Encapsula engine + fábrica de sessões de um serviço.

    Um objeto por processo: o pool de conexões vive no engine e deve ser
    reaproveitado entre requisições (criar engine por request esgota o MySQL).
    """

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            pool_pre_ping=True,  # descarta conexões mortas (MySQL fecha após wait_timeout)
            pool_recycle=1800,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Dependência FastAPI: uma sessão por request, sempre fechada no final."""
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
