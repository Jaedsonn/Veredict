"""GRANT/REVOKE do usuário de runtime, chamados pela migration que cria a tabela"""

import re
from collections.abc import Callable, Iterable

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Ordem fixa deixa o SQL gerado estável entre execuções
_PRIVILEGE_ORDER = ("SELECT", "INSERT", "UPDATE", "DELETE")
ALLOWED_PRIVILEGES = frozenset(_PRIVILEGE_ORDER)  # DDL é exclusivo do `migrator`

# GRANT não aceita bind parameters em nomes: whitelist evita injeção
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_HOST = re.compile(r"^[A-Za-z0-9_.%-]{1,255}$")


def _check(kind: str, value: str, pattern: re.Pattern[str] = _IDENTIFIER) -> None:
    if not pattern.match(value):
        raise ValueError(f"{kind} inválido para GRANT/REVOKE: {value!r}")


def _privilege_list(privileges: Iterable[str]) -> str:
    requested = {p.upper() for p in privileges}
    if not requested:
        raise ValueError("Informe ao menos um privilégio")
    if invalid := requested - ALLOWED_PRIVILEGES:
        raise ValueError(
            f"Privilégios não permitidos: {sorted(invalid)}; use {sorted(ALLOWED_PRIVILEGES)}"
        )
    return ", ".join(p for p in _PRIVILEGE_ORDER if p in requested)


def _target(schema: str, table: str, user: str, host: str) -> tuple[str, str]:
    _check("schema", schema)
    _check("tabela", table)
    _check("usuário", user)
    _check("host", host, _HOST)
    return f"`{schema}`.`{table}`", f"'{user}'@'{host}'"


def grant_sql(
    privileges: Iterable[str], *, schema: str, table: str, user: str, host: str = "%"
) -> str:
    obj, account = _target(schema, table, user, host)
    return f"GRANT {_privilege_list(privileges)} ON {obj} TO {account}"


def revoke_sql(
    privileges: Iterable[str], *, schema: str, table: str, user: str, host: str = "%"
) -> str:
    """Idempotente: o downgrade pode rodar mesmo sem o GRANT ou o usuário existirem"""
    obj, account = _target(schema, table, user, host)
    return (
        f"REVOKE IF EXISTS {_privilege_list(privileges)} ON {obj} "
        f"FROM {account} IGNORE UNKNOWN USER"
    )


def _execute(
    build: Callable[..., str],
    bind: Connection,
    *,
    table: str,
    privileges: Iterable[str],
    user: str,
    schema: str | None,
    host: str,
) -> None:
    # No SQLite dos testes não existem usuários nem privilégios
    if bind.dialect.name != "mysql":
        return
    schema = schema or str(bind.execute(text("SELECT DATABASE()")).scalar_one())
    # text() escapa o '%' do host para o paramstyle pyformat do driver
    bind.execute(text(build(privileges, schema=schema, table=table, user=user, host=host)))


def grant_table_privileges(
    bind: Connection,
    *,
    table: str,
    privileges: Iterable[str],
    user: str,
    schema: str | None = None,
    host: str = "%",
) -> None:
    _execute(
        grant_sql, bind, table=table, privileges=privileges, user=user, schema=schema, host=host
    )


def revoke_table_privileges(
    bind: Connection,
    *,
    table: str,
    privileges: Iterable[str],
    user: str,
    schema: str | None = None,
    host: str = "%",
) -> None:
    """Chamar no downgrade antes do DROP: o MySQL não revoga GRANT de tabela removida"""
    _execute(
        revoke_sql, bind, table=table, privileges=privileges, user=user, schema=schema, host=host
    )
