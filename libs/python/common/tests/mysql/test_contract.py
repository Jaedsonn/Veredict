"""Contrato do banco contra MySQL real: privilégios, UTC e tipos físicos"""

import enum
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from veriditi_common.db import Database, make_metadata
from veriditi_common.db_types import BigIntPK, HashHex, UTCDateTime, UtcNow, UUIDStr, str_enum
from veriditi_common.migrations import grant_table_privileges, revoke_table_privileges

pytestmark = pytest.mark.mysql

HOST = os.environ.get("CONTRACT_DB_HOST", "127.0.0.1")
PORT = os.environ.get("CONTRACT_DB_PORT", "3317")
PASSWORDS = {
    "migrator": os.environ.get("DB_MIGRATOR_PASSWORD", "m"),
    "auth_svc": os.environ.get("AUTH_DB_PASSWORD", "a"),
    "notification_svc": os.environ.get("NOTIFICATION_DB_PASSWORD", "n"),
    "veriditi_logs_writer": os.environ.get("LOGS_DB_PASSWORD", "l"),
}

# Errnos do MySQL que provam o bloqueio
TABLE_ACCESS_DENIED = 1142
DB_ACCESS_DENIED = 1044


class Status(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"


metadata = make_metadata()
probe = sa.Table(
    "contract_probe",
    metadata,
    sa.Column("id", BigIntPK, primary_key=True, autoincrement=True),
    sa.Column("at", UTCDateTime(), nullable=True),
    sa.Column("created_at", UTCDateTime(), nullable=False, server_default=UtcNow()),
    sa.Column("status", str_enum(Status, "status"), nullable=False, server_default="pending"),
    sa.Column("ref", UUIDStr(), nullable=True),
    sa.Column("digest", HashHex(), nullable=True),
)

# Tabela "própria" do notification: sem nenhum GRANT no banco ele nem conecta (1044)
own_probe = sa.Table(
    "contract_probe_notification",
    metadata,
    sa.Column("id", BigIntPK, primary_key=True, autoincrement=True),
)

logs_metadata = make_metadata()
logs_probe = sa.Table(
    "contract_probe_logs",
    logs_metadata,
    sa.Column("id", BigIntPK, primary_key=True, autoincrement=True),
    sa.Column("action", sa.String(80), nullable=False),
)


def _db(user: str, schema: str = "veriditi") -> Database:
    return Database(f"mysql+aiomysql://{user}:{PASSWORDS[user]}@{HOST}:{PORT}/{schema}")


def _errno(exc: pytest.ExceptionInfo[DBAPIError]) -> int:
    return int(exc.value.orig.args[0])  # type: ignore[union-attr]


GRANTS = [
    ("veriditi", "contract_probe", ["SELECT", "INSERT", "UPDATE"], "auth_svc"),
    ("veriditi", "contract_probe_notification", ["SELECT"], "notification_svc"),
    ("veriditi_logs", "contract_probe_logs", ["SELECT", "INSERT"], "veriditi_logs_writer"),
]


def _in_logs_db(conn: sa.Connection) -> sa.Connection:
    return conn.execution_options(schema_translate_map={None: "veriditi_logs"})


@pytest.fixture
async def schema() -> AsyncIterator[None]:
    migrator = _db("migrator")
    async with migrator.engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(lambda c: logs_metadata.create_all(_in_logs_db(c)))
        for schema_name, table, privileges, user in GRANTS:
            await conn.run_sync(
                grant_table_privileges,
                schema=schema_name,
                table=table,
                privileges=privileges,
                user=user,
            )
    yield
    async with migrator.engine.begin() as conn:
        for schema_name, table, privileges, user in GRANTS:
            await conn.run_sync(
                revoke_table_privileges,
                schema=schema_name,
                table=table,
                privileges=privileges,
                user=user,
            )
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(lambda c: logs_metadata.drop_all(_in_logs_db(c)))
    await migrator.dispose()


@pytest.fixture
async def auth() -> AsyncIterator[Database]:
    db = _db("auth_svc")
    yield db
    await db.dispose()


async def test_session_time_zone_is_utc(schema: None, auth: Database) -> None:
    async with auth.engine.connect() as conn:
        assert (await conn.execute(sa.text("SELECT @@session.time_zone"))).scalar_one() == "+00:00"


async def test_schemas_use_contract_collation() -> None:
    db = _db("migrator")
    async with db.engine.connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT SCHEMA_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA "
                "WHERE SCHEMA_NAME IN ('veriditi', 'veriditi_logs')"
            )
        )
        collations = {name: collation for name, collation in rows}
    await db.dispose()

    assert collations == {
        "veriditi": "utf8mb4_0900_ai_ci",
        "veriditi_logs": "utf8mb4_0900_ai_ci",
    }


async def test_runtime_user_without_any_grant_cannot_connect() -> None:
    # Antes da 1ª migration do serviço, o usuário de runtime não abre o banco
    db = _db("notification_svc")
    with pytest.raises(DBAPIError) as exc:
        async with db.engine.connect():
            pass
    await db.dispose()

    assert _errno(exc) == DB_ACCESS_DENIED


async def test_types_produce_contract_ddl(schema: None, auth: Database) -> None:
    async with auth.engine.connect() as conn:
        ddl = (await conn.execute(sa.text("SHOW CREATE TABLE contract_probe"))).one()[1]

    assert "`created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)" in ddl
    assert "enum('pending','active')" in ddl
    assert "`ref` char(36) CHARACTER SET ascii COLLATE ascii_bin" in ddl
    assert "`digest` char(64) CHARACTER SET ascii COLLATE ascii_bin" in ddl


async def test_utc_roundtrip_keeps_microseconds(schema: None, auth: Database) -> None:
    bahia = datetime(2026, 1, 1, 9, 0, 0, 123456, tzinfo=ZoneInfo("America/Bahia"))
    ref = uuid.uuid4()
    async with auth.engine.begin() as conn:
        await conn.execute(probe.insert().values(at=bahia, ref=ref, digest="AB" * 32))
        row = (await conn.execute(sa.select(probe))).one()

    assert row.at == datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    assert row.created_at.tzinfo is UTC
    assert row.ref == ref
    assert row.digest == "ab" * 32
    assert row.status == Status.PENDING


async def test_runtime_user_has_no_ddl(schema: None, auth: Database) -> None:
    async with auth.engine.begin() as conn:
        with pytest.raises(DBAPIError) as exc:
            await conn.execute(sa.text("CREATE TABLE intruder (id INT)"))

    assert _errno(exc) == TABLE_ACCESS_DENIED


async def test_runtime_user_has_no_delete_without_grant(schema: None, auth: Database) -> None:
    async with auth.engine.begin() as conn:
        with pytest.raises(DBAPIError) as exc:
            await conn.execute(probe.delete())

    assert _errno(exc) == TABLE_ACCESS_DENIED


async def test_other_service_cannot_read_table_it_does_not_own(schema: None) -> None:
    # Equivale ao "payment não lê refresh_tokens" do #41 até o payment_svc existir
    notification = _db("notification_svc")
    async with notification.engine.connect() as conn:
        await conn.execute(sa.select(own_probe))

    async with notification.engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc:
            await conn.execute(sa.select(probe))
    await notification.dispose()

    assert _errno(exc) == TABLE_ACCESS_DENIED


async def test_central_service_cannot_open_logs_database(schema: None) -> None:
    intruder = _db("auth_svc", "veriditi_logs")
    with pytest.raises(DBAPIError) as exc:
        async with intruder.engine.connect():
            pass
    await intruder.dispose()

    assert _errno(exc) == DB_ACCESS_DENIED


async def test_logs_writer_is_append_only(schema: None) -> None:
    writer = _db("veriditi_logs_writer", "veriditi_logs")
    async with writer.engine.begin() as conn:
        await conn.execute(logs_probe.insert().values(action="auth.user.registered"))

    for statement in (logs_probe.update().values(action="x"), logs_probe.delete()):
        async with writer.engine.begin() as conn:
            with pytest.raises(DBAPIError) as exc:
                await conn.execute(statement)
        assert _errno(exc) == TABLE_ACCESS_DENIED
    await writer.dispose()


async def test_revoke_removes_access_and_is_idempotent(schema: None, auth: Database) -> None:
    migrator = _db("migrator")
    for _ in range(2):
        async with migrator.engine.begin() as conn:
            await conn.run_sync(
                revoke_table_privileges,
                table="contract_probe",
                privileges=["SELECT"],
                user="auth_svc",
            )
    await migrator.dispose()

    async with auth.engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc:
            await conn.execute(sa.select(probe))

    assert _errno(exc) == TABLE_ACCESS_DENIED
