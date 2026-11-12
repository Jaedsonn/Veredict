"""Tipos de coluna portáveis entre MySQL (produção) e SQLite (testes unitários).

Cada tipo aqui materializa uma convenção de `docs/banco-de-dados.md`:

- datas sempre em UTC e com microssegundos (`DATETIME(6)`);
- hashes e UUIDs como texto ASCII de tamanho fixo, comparado byte a byte;
- status como `ENUM` nativo no MySQL (e `VARCHAR` + `CHECK` no SQLite).

Os services importam estes tipos nos *models*. As *migrations* NÃO os importam:
elas descrevem o tipo físico explícito (ex.: `mysql.DATETIME(fsp=6)`), para que
uma migration antiga continue igual mesmo se este módulo mudar no futuro.
"""

import enum
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import TypeDecorator, TypeEngine

# BIGINT no MySQL; INTEGER no SQLite (só `INTEGER PRIMARY KEY` autoincrementa lá).
BigIntPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def utcnow() -> datetime:
    """Agora, em UTC e *aware*. Use como `default=`/`onupdate=` no lado Python."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """`DATETIME(6)` que só aceita e só devolve datetimes em UTC.

    O MySQL não guarda fuso em `DATETIME`. Então a regra fica na aplicação:
    - na escrita, recusa datetime *naive* (sem fuso), porque seria ambíguo, e
      converte qualquer fuso para UTC antes de gravar;
    - na leitura, devolve o valor marcado como UTC (*aware*).
    """

    impl = sa.DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(sa.DateTime())

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "UTCDateTime recusa datetime sem fuso (naive); use utcnow() ou um datetime aware"
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class UtcNow(FunctionElement[datetime]):
    """`server_default` portável: o banco preenche a data atual com microssegundos.

    - MySQL: `CURRENT_TIMESTAMP(6)`. A sessão está em UTC (ver `connect_args_for`).
    - SQLite: `STRFTIME` com milissegundos, sempre em UTC.
    """

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
    """Texto ASCII comparado byte a byte (`ascii_bin`) no MySQL.

    Serve para identificadores gerados por código (hashes, UUIDs, chaves de
    idempotência). Em `utf8mb4`, um `CHAR(64)` pode reservar até 256 bytes; em
    `ascii`, ocupa 64. E `ascii_bin` não confunde maiúsculas com minúsculas.
    """
    if fixed:
        return sa.CHAR(length).with_variant(
            mysql.CHAR(length, charset="ascii", collation="ascii_bin"), "mysql"
        )
    return sa.String(length).with_variant(
        mysql.VARCHAR(length, charset="ascii", collation="ascii_bin"), "mysql"
    )


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class HashHex(TypeDecorator[str]):
    """SHA-256/HMAC-SHA256 em hexadecimal minúsculo: `CHAR(64)` ASCII.

    Normaliza para minúsculas e valida o formato na escrita. Com `ascii_bin`,
    um hash gravado em maiúsculas nunca bateria numa busca em minúsculas.
    """

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


class UUIDStr(TypeDecorator[uuid.UUID]):
    """UUID como `CHAR(36)` ASCII (formato canônico com hífens).

    O `sa.Uuid` do SQLAlchemy grava `CHAR(32)` sem hífens no MySQL, o que diverge
    do contrato (`CHAR(36)`) e do formato que aparece em URLs e logs.
    """

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
    """`ENUM` nativo no MySQL; `VARCHAR` + `CHECK` nomeado (`ck_<tabela>_<name>`) no SQLite.

    Grava o *valor* do membro (`"active"`), não o nome (`"ACTIVE"`), e recusa
    strings fora do enum já na aplicação (`validate_strings=True`).
    """
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=True,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [m.value for m in members],
    )
