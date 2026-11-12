"""create audit_events table

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

# Append-only: sem UPDATE nem DELETE, nem para o próprio serviço (§7, ADR-015)
PRIVILEGES = ["SELECT", "INSERT"]


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "event_id", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("occurred_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column(
            "received_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column("service", mysql.VARCHAR(40), nullable=False),
        sa.Column("action", mysql.VARCHAR(80), nullable=False),
        sa.Column("outcome", mysql.ENUM("success", "failure"), nullable=False),
        sa.Column("actor_id", mysql.BIGINT(), nullable=True),
        sa.Column("actor_ip", mysql.VARCHAR(45), nullable=True),
        sa.Column(
            "request_id", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=True
        ),
        sa.Column("resource_type", mysql.VARCHAR(40), nullable=True),
        sa.Column("resource_id", mysql.VARCHAR(64), nullable=True),
        sa.Column("metadata", mysql.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_audit_events_event_id")),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        op.f("ix_audit_events_actor_id_occurred_at"), "audit_events", ["actor_id", "occurred_at"]
    )
    op.create_index(
        op.f("ix_audit_events_action_occurred_at"), "audit_events", ["action", "occurred_at"]
    )
    grant_table_privileges(
        op.get_bind(),
        table="audit_events",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )


def downgrade() -> None:
    # Antes do DROP: o MySQL não revoga GRANT de tabela removida
    revoke_table_privileges(
        op.get_bind(),
        table="audit_events",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    op.drop_table("audit_events")
