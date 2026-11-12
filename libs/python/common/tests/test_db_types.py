import enum
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.schema import CreateTable

from veriditi_common.db import Database, make_metadata
from veriditi_common.db_types import (
    BigIntPK,
    HashHex,
    UTCDateTime,
    UtcNow,
    UUIDStr,
    ascii_string,
    str_enum,
    utcnow,
)


class Status(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"


metadata = make_metadata()

things = sa.Table(
    "things",
    metadata,
    sa.Column("id", BigIntPK, primary_key=True, autoincrement=True),
    sa.Column("at", UTCDateTime(), nullable=True),
    sa.Column("created_at", UTCDateTime(), nullable=False, server_default=UtcNow()),
    sa.Column("status", str_enum(Status, "status"), nullable=False, server_default="pending"),
    sa.Column("ref", UUIDStr(), nullable=True),
    sa.Column("digest", HashHex(), nullable=True),
    sa.Column("key", ascii_string(128), nullable=True),
)


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield database
    await database.dispose()


async def test_utc_datetime_converts_any_offset_to_utc_and_keeps_microseconds(
    db: Database,
) -> None:
    bahia = datetime(2026, 1, 1, 9, 0, 0, 123456, tzinfo=ZoneInfo("America/Bahia"))
    async with db.engine.begin() as conn:
        await conn.execute(things.insert().values(at=bahia))
        stored = (await conn.execute(sa.select(things.c.at))).scalar_one()

    assert stored == datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    assert stored.utcoffset() == timedelta(0)


async def test_utc_datetime_rejects_naive_datetime(db: Database) -> None:
    async with db.engine.begin() as conn:
        with pytest.raises(StatementError, match="naive"):
            await conn.execute(things.insert().values(at=datetime(2026, 1, 1, 9, 0)))


async def test_server_default_fills_created_at_in_utc(db: Database) -> None:
    before = utcnow() - timedelta(seconds=1)
    async with db.engine.begin() as conn:
        await conn.execute(things.insert().values())
        created_at = (await conn.execute(sa.select(things.c.created_at))).scalar_one()

    assert created_at.tzinfo is UTC
    assert before <= created_at <= utcnow() + timedelta(seconds=1)


async def test_str_enum_stores_value_and_check_rejects_unknown_value(db: Database) -> None:
    async with db.engine.begin() as conn:
        await conn.execute(things.insert().values(status=Status.ACTIVE))
        raw = (await conn.execute(sa.text("SELECT status FROM things"))).scalar_one()
    assert raw == "active"

    async with db.engine.begin() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(sa.text("INSERT INTO things (status) VALUES ('deleted')"))


async def test_uuid_str_roundtrip_in_canonical_format(db: Database) -> None:
    ref = uuid.uuid4()
    async with db.engine.begin() as conn:
        await conn.execute(things.insert().values(ref=ref))
        raw = (await conn.execute(sa.text("SELECT ref FROM things"))).scalar_one()
        loaded = (await conn.execute(sa.select(things.c.ref))).scalar_one()

    assert raw == str(ref) and len(raw) == 36
    assert loaded == ref


async def test_hash_hex_normalizes_to_lowercase_and_rejects_invalid(db: Database) -> None:
    digest = "AB" * 32
    async with db.engine.begin() as conn:
        await conn.execute(things.insert().values(digest=digest))
        stored = (await conn.execute(sa.select(things.c.digest))).scalar_one()
    assert stored == "ab" * 32

    async with db.engine.begin() as conn:
        with pytest.raises(StatementError, match="64 caracteres"):
            await conn.execute(things.insert().values(digest="not-a-hash"))


def test_mysql_ddl_uses_contract_physical_types() -> None:
    ddl = str(CreateTable(things).compile(dialect=mysql.dialect()))

    assert "id BIGINT NOT NULL AUTO_INCREMENT" in ddl
    assert "at DATETIME(6)" in ddl
    assert "created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)" in ddl
    assert "status ENUM('pending','active')" in ddl
    assert "ref CHAR(36) CHARACTER SET ascii COLLATE ascii_bin" in ddl
    assert "digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin" in ddl
    assert "`key` VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin" in ddl


def test_sqlite_ddl_uses_portable_fallbacks() -> None:
    ddl = str(CreateTable(things).compile(dialect=sqlite.dialect()))

    assert "id INTEGER NOT NULL" in ddl
    assert "STRFTIME" in ddl
    assert "CONSTRAINT ck_things_status CHECK" in ddl
