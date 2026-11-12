"""create refresh_tokens table ([S1-09], docs/banco-de-dados.md §5.3)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

from veriditi_common.migrations import grant_table_privileges, revoke_table_privileges

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIVILEGES = ["SELECT", "INSERT", "UPDATE", "DELETE"]


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.BIGINT(), nullable=False),
        sa.Column(
            "token_hash",
            mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column(
            "family_id",
            mysql.CHAR(36, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column(
            "revoke_reason",
            mysql.ENUM("rotated", "logout", "reuse_detected"),
            nullable=True,
        ),
        sa.Column("created_ip", mysql.VARCHAR(45), nullable=True),
        sa.Column("user_agent", mysql.VARCHAR(255), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoke_reason IS NULL)",
            name=op.f("ck_refresh_tokens_revocation_consistent"),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    # Criado antes da FK para o InnoDB usar o índice composto (prefixo user_id) sem índice extra
    op.create_index(
        op.f("ix_refresh_tokens_user_id_revoked_at"),
        "refresh_tokens",
        ["user_id", "revoked_at"],
    )
    op.create_foreign_key(
        op.f("fk_refresh_tokens_user_id_users"),
        "refresh_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    grant_table_privileges(
        op.get_bind(),
        table="refresh_tokens",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )


def downgrade() -> None:
    revoke_table_privileges(
        op.get_bind(),
        table="refresh_tokens",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    op.drop_table("refresh_tokens")
