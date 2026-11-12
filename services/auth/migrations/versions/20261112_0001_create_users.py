"""create users table

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

from veriditi_common.migrations import grant_table_privileges, revoke_table_privileges

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sem DELETE: usuário removido vira blocked (docs/banco-de-dados.md §7)
PRIVILEGES = ["SELECT", "INSERT", "UPDATE"]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("email", mysql.VARCHAR(255), nullable=False),
        sa.Column("name", mysql.VARCHAR(120), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    grant_table_privileges(
        op.get_bind(),
        table="users",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )


def downgrade() -> None:
    revoke_table_privileges(
        op.get_bind(),
        table="users",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    op.drop_table("users")
