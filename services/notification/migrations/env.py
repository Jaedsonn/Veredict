import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from notification_service.config import get_settings
from notification_service.models import Base
from veriditi_common.db import connect_args_for

config = context.config
target_metadata = Base.metadata
settings = get_settings()

# Banco compartilhado: cada serviço guarda a própria revisão (docs/banco-de-dados.md §11)
VERSION_TABLE = "alembic_version_notification"

# A migration que cria a tabela concede o GRANT a este usuário
config.attributes["runtime_db_user"] = settings.db_user


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """Ignora tabelas de outros serviços, que o autogenerate leria como drop_table"""
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.migration_database_url,
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
    url = settings.migration_database_url
    engine = create_async_engine(url, poolclass=pool.NullPool, connect_args=connect_args_for(url))
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
