"""create password_reset_tokens and add password_reset to revoke_reason ([S2-02], §5.6)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

from veriditi_common.migrations import grant_table_privileges, revoke_table_privileges

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIVILEGES = ["SELECT", "INSERT", "UPDATE", "DELETE"]
OLD_REASONS = ("rotated", "logout", "reuse_detected")
NEW_REASONS = (*OLD_REASONS, "password_reset")


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.BIGINT(), nullable=False),
        sa.Column(
            "token_hash",
            mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("consumed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("requested_ip", mysql.VARCHAR(45), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    # Criado antes da FK para o InnoDB usar o índice composto (prefixo user_id) sem índice extra
    op.create_index(
        op.f("ix_password_reset_tokens_user_id_consumed_at"),
        "password_reset_tokens",
        ["user_id", "consumed_at"],
    )
    op.create_foreign_key(
        op.f("fk_password_reset_tokens_user_id_users"),
        "password_reset_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    grant_table_privileges(
        op.get_bind(),
        table="password_reset_tokens",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    # Valor novo no fim do ENUM: ALTER instantâneo, sem reescrever a tabela
    op.alter_column(
        "refresh_tokens",
        "revoke_reason",
        existing_type=mysql.ENUM(*OLD_REASONS),
        type_=mysql.ENUM(*NEW_REASONS),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Sem o valor no ENUM o ALTER falharia; logout é o motivo antigo mais próximo
    op.execute(
        "UPDATE refresh_tokens SET revoke_reason = 'logout' WHERE revoke_reason = 'password_reset'"
    )
    op.alter_column(
        "refresh_tokens",
        "revoke_reason",
        existing_type=mysql.ENUM(*NEW_REASONS),
        type_=mysql.ENUM(*OLD_REASONS),
        existing_nullable=True,
    )
    revoke_table_privileges(
        op.get_bind(),
        table="password_reset_tokens",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    op.drop_table("password_reset_tokens")
