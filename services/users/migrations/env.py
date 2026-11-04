import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from users_service.config import get_settings
from users_service.models import Base

config = context.config
target_metadata = Base.metadata

# Banco único compartilhado: cada serviço registra seu histórico em uma tabela
# de versão PRÓPRIA. Com a padrão (alembic_version), um serviço sobrescreveria
# a revisão do outro.
VERSION_TABLE = "alembic_version_users"


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """No --autogenerate, considera só as tabelas deste serviço. Sem isso, as
    tabelas dos outros serviços apareceriam como 'removidas' -> drop_table!"""
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        version_table=VERSION_TABLE,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table=VERSION_TABLE,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
