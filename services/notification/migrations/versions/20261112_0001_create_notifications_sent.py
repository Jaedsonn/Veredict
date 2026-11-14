"""create notifications_sent table

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

# Sem DELETE: a deduplicação é permanente até a limpeza do #35/#37 (§7)
PRIVILEGES = ["SELECT", "INSERT", "UPDATE"]


def upgrade() -> None:
    op.create_table(
        "notifications_sent",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "idempotency_key",
            mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("template", mysql.VARCHAR(64), nullable=False),
        sa.Column(
            "status",
            mysql.ENUM("pending", "sent", "failed"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", mysql.TINYINT(), nullable=False, server_default=sa.text("0")),
        sa.Column("message_id", mysql.VARCHAR(255), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column("sent_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications_sent")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_notifications_sent_idempotency_key")),
        sa.CheckConstraint(
            "attempts >= 0", name=op.f("ck_notifications_sent_attempts_non_negative")
        ),
        sa.CheckConstraint(
            "status <> 'sent' OR sent_at IS NOT NULL",
            name=op.f("ck_notifications_sent_sent_requires_sent_at"),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    grant_table_privileges(
        op.get_bind(),
        table="notifications_sent",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )


def downgrade() -> None:
    # Antes do DROP: o MySQL não revoga GRANT de tabela removida
    revoke_table_privileges(
        op.get_bind(),
        table="notifications_sent",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    op.drop_table("notifications_sent")
