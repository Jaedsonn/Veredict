from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from veriditi_common.db import (
    MYSQL_UTC_INIT_COMMAND,
    NAMING_CONVENTION,
    Database,
    connect_args_for,
    make_metadata,
)


def _sample_metadata() -> sa.MetaData:
    metadata = make_metadata()
    sa.Table("u", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "t",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("a", sa.Integer, unique=True),
        sa.Column("b", sa.Integer),
        sa.Column("u_id", sa.Integer, sa.ForeignKey("u.id")),
        sa.CheckConstraint("b >= 0", name="b_non_negative"),
        sa.Index(None, "a", "b"),
    )
    return metadata


def test_make_metadata_returns_isolated_metadata_with_convention() -> None:
    first, second = make_metadata(), make_metadata()

    assert first is not second
    assert NAMING_CONVENTION.items() <= dict(first.naming_convention).items()


def test_naming_convention_generates_contract_names() -> None:
    table = _sample_metadata().tables["t"]
    dialect = mysql.dialect()
    ddl = str(CreateTable(table).compile(dialect=dialect))
    index_ddl = " ".join(str(CreateIndex(ix).compile(dialect=dialect)) for ix in table.indexes)

    assert "CONSTRAINT pk_t PRIMARY KEY" in ddl
    assert "CONSTRAINT uq_t_a UNIQUE" in ddl
    assert "CONSTRAINT fk_t_u_id_u FOREIGN KEY" in ddl
    assert "CONSTRAINT ck_t_b_non_negative CHECK" in ddl
    assert "CREATE INDEX ix_t_a_b" in index_ddl


def test_check_constraint_without_name_is_rejected() -> None:
    metadata = make_metadata()
    table = sa.Table("t", metadata, sa.Column("x", sa.Integer))

    # Falha já ao anexar a CHECK na tabela, antes de qualquer DDL ser gerado.
    with pytest.raises(sa.exc.InvalidRequestError, match="explicitly named"):
        table.append_constraint(sa.CheckConstraint("x > 0"))


def test_connect_args_force_utc_session_only_on_mysql() -> None:
    assert connect_args_for("mysql+aiomysql://u:p@h:3306/veriditi") == {
        "init_command": MYSQL_UTC_INIT_COMMAND
    }
    assert MYSQL_UTC_INIT_COMMAND == "SET time_zone = '+00:00'"
    assert connect_args_for("sqlite+aiosqlite:///:memory:") == {}


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    yield database
    await database.dispose()


async def test_sqlite_enforces_foreign_keys(db: Database) -> None:
    metadata = _sample_metadata()
    async with db.engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    async with db.engine.begin() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(metadata.tables["t"].insert().values(id=1, u_id=999))
