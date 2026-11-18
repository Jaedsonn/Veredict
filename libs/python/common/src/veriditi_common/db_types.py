"""Tipos de coluna portáveis entre MySQL e SQLite (convenções em docs/banco-de-dados.md)"""

import enum
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import TypeDecorator, TypeEngine

# Só `INTEGER PRIMARY KEY` autoincrementa no SQLite
BigIntPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """DATETIME(6) que só grava e só devolve datetimes aware em UTC"""

    impl = sa.DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(sa.DateTime())

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        # O MySQL não guarda fuso em DATETIME: um valor naive seria ambíguo
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime recusa datetime naive; use utcnow() ou um datetime aware")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class UtcNow(FunctionElement[datetime]):
    """server_default com a data atual em UTC e fração de segundo"""

    type = sa.DateTime()
    inherit_cache = True
    name = "utcnow"


@compiles(UtcNow, "mysql")
def _utcnow_mysql(element: UtcNow, compiler: SQLCompiler, **kw: Any) -> str:
    return "CURRENT_TIMESTAMP(6)"


@compiles(UtcNow, "sqlite")
def _utcnow_sqlite(element: UtcNow, compiler: SQLCompiler, **kw: Any) -> str:
    return "(STRFTIME('%Y-%m-%d %H:%M:%f', 'now'))"


@compiles(UtcNow)
def _utcnow_default(element: UtcNow, compiler: SQLCompiler, **kw: Any) -> str:
    return "CURRENT_TIMESTAMP"


def ascii_string(length: int, *, fixed: bool = False) -> TypeEngine[str]:
    """Texto gerado por código (hash, UUID, chave) em ascii_bin: tamanho fixo e comparação exata"""
    if fixed:
        return sa.CHAR(length).with_variant(
            mysql.CHAR(length, charset="ascii", collation="ascii_bin"), "mysql"
        )
    return sa.String(length).with_variant(
        mysql.VARCHAR(length, charset="ascii", collation="ascii_bin"), "mysql"
    )


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class HashHex(TypeDecorator[str]):
    """SHA-256 em hex minúsculo, já que ascii_bin diferencia maiúsculas"""

    impl = sa.CHAR(64)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        return dialect.type_descriptor(ascii_string(64, fixed=True))

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if not _HEX64.match(normalized):
            raise ValueError("HashHex espera 64 caracteres hexadecimais (SHA-256)")
        return normalized


class _UnhexOnMySql(FunctionElement[bytes]):
    type = sa.LargeBinary()
    inherit_cache = True
    name = "unhex_on_mysql"


@compiles(_UnhexOnMySql, "mysql")
def _unhex_mysql(element: _UnhexOnMySql, compiler: SQLCompiler, **kw: Any) -> str:
    return f"UNHEX({compiler.process(element.clauses, **kw)})"


@compiles(_UnhexOnMySql)
def _unhex_default(element: _UnhexOnMySql, compiler: SQLCompiler, **kw: Any) -> str:
    return compiler.process(element.clauses, **kw)


class VarBinary(TypeDecorator[bytes]):
    """VARBINARY(n); no MySQL o valor viaja em hex e o UNHEX volta aos bytes

    O aiomysql 0.3.2 quebra ao escapar bytes com o PyMySQL 1.2 (PyMySQL#1274); hex é texto
    """

    impl = sa.LargeBinary
    cache_ok = True

    def __init__(self, length: int) -> None:
        super().__init__(length)
        self.length = length

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.VARBINARY(self.length))
        return dialect.type_descriptor(sa.LargeBinary(self.length))

    def bind_expression(self, bindvalue: Any) -> Any:
        return _UnhexOnMySql(bindvalue)

    def process_bind_param(self, value: bytes | None, dialect: Dialect) -> bytes | str | None:
        if value is None:
            return None
        if len(value) > self.length:
            raise ValueError(f"VarBinary aceita até {self.length} bytes")
        return value.hex() if dialect.name == "mysql" else value

    def bind_processor(self, dialect: Dialect) -> Callable[[Any], Any]:
        # Sem o processor do impl: o Binary() do DBAPI recusaria o hex (str) do MySQL
        def process(value: Any) -> Any:
            return self.process_bind_param(value, dialect)

        return process

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> bytes | None:
        return bytes(value) if value is not None else None


class UUIDStr(TypeDecorator[uuid.UUID]):
    """UUID como CHAR(36) com hífens; o sa.Uuid gravaria CHAR(32) no MySQL"""

    impl = sa.CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        return dialect.type_descriptor(ascii_string(36, fixed=True))

    def process_bind_param(self, value: uuid.UUID | str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return str(value if isinstance(value, uuid.UUID) else uuid.UUID(value))

    def process_result_value(self, value: str | None, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        return uuid.UUID(value)

    @property
    def python_type(self) -> type[uuid.UUID]:
        return uuid.UUID


def str_enum(enum_cls: type[enum.Enum], name: str) -> sa.Enum:
    """ENUM nativo no MySQL; VARCHAR + CHECK `ck_<tabela>_<name>` no SQLite"""
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=True,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [m.value for m in members],  # grava "active", não "ACTIVE"
    )
