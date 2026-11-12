import pytest
import sqlalchemy as sa

from veriditi_common.migrations import (
    grant_sql,
    grant_table_privileges,
    revoke_sql,
    revoke_table_privileges,
)


def test_grant_sql_orders_privileges_and_quotes_identifiers() -> None:
    sql = grant_sql(
        ["insert", "SELECT"],
        schema="veriditi_logs",
        table="audit_events",
        user="veriditi_logs_writer",
    )

    assert sql == (
        "GRANT SELECT, INSERT ON `veriditi_logs`.`audit_events` TO 'veriditi_logs_writer'@'%'"
    )


def test_revoke_sql_is_idempotent() -> None:
    sql = revoke_sql(["SELECT"], schema="veriditi", table="users", user="auth_svc")

    assert sql == (
        "REVOKE IF EXISTS SELECT ON `veriditi`.`users` FROM 'auth_svc'@'%' IGNORE UNKNOWN USER"
    )


@pytest.mark.parametrize("privileges", [["DROP"], ["ALL"], ["SELECT", "CREATE"], []])
def test_only_dml_privileges_are_allowed(privileges: list[str]) -> None:
    with pytest.raises(ValueError):
        grant_sql(privileges, schema="veriditi", table="users", user="auth_svc")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user", "auth_svc'@'%'; DROP TABLE users; --"),
        ("user", "auth svc"),
        ("user", "a" * 65),
        ("table", "users`; DROP TABLE x"),
        ("schema", ""),
        ("host", "localhost'; --"),
    ],
)
def test_identifiers_are_validated(field: str, value: str) -> None:
    kwargs = {"schema": "veriditi", "table": "users", "user": "auth_svc", field: value}

    with pytest.raises(ValueError):
        grant_sql(["SELECT"], **kwargs)


def test_helpers_are_noop_outside_mysql() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        grant_table_privileges(conn, table="users", privileges=["SELECT"], user="auth_svc")
        revoke_table_privileges(conn, table="users", privileges=["SELECT"], user="auth_svc")
