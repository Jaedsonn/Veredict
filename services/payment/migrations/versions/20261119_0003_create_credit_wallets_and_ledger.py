"""create credit_wallets e credit_ledger (append-only)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

from veriditi_common.migrations import grant_table_privileges, revoke_table_privileges

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WALLET_PRIVILEGES = ["SELECT", "INSERT", "UPDATE"]
# Append-only: um movimento nunca é editado nem apagado (§7)
LEDGER_PRIVILEGES = ["SELECT", "INSERT"]


def upgrade() -> None:
    op.create_table(
        "credit_wallets",
        sa.Column("user_id", mysql.BIGINT(), autoincrement=False, nullable=False),
        sa.Column("balance", mysql.INTEGER(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_credit_wallets")),
        sa.CheckConstraint("balance >= 0", name=op.f("ck_credit_wallets_balance_not_negative")),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "credit_ledger",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.BIGINT(), nullable=False),
        sa.Column("delta", mysql.INTEGER(), nullable=False),
        sa.Column(
            "reason", mysql.ENUM("purchase", "capture", "refund", "adjustment"), nullable=False
        ),
        sa.Column(
            "reference_id",
            mysql.VARCHAR(64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("balance_after", mysql.INTEGER(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_ledger")),
        sa.UniqueConstraint(
            "reason", "reference_id", name=op.f("uq_credit_ledger_reason_reference_id")
        ),
        sa.CheckConstraint("delta <> 0", name=op.f("ck_credit_ledger_delta_not_zero")),
        sa.CheckConstraint(
            "balance_after >= 0", name=op.f("ck_credit_ledger_balance_after_not_negative")
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    # O índice (user_id, id) atende o extrato e serve à FK, sem índice extra
    op.create_index(op.f("ix_credit_ledger_user_id_id"), "credit_ledger", ["user_id", "id"])
    op.create_foreign_key(
        op.f("fk_credit_ledger_user_id_credit_wallets"),
        "credit_ledger",
        "credit_wallets",
        ["user_id"],
        ["user_id"],
        ondelete="RESTRICT",
    )
    bind = op.get_bind()
    user = context.config.attributes["runtime_db_user"]
    grant_table_privileges(bind, table="credit_wallets", privileges=WALLET_PRIVILEGES, user=user)
    grant_table_privileges(bind, table="credit_ledger", privileges=LEDGER_PRIVILEGES, user=user)


def downgrade() -> None:
    bind = op.get_bind()
    user = context.config.attributes["runtime_db_user"]
    revoke_table_privileges(bind, table="credit_ledger", privileges=LEDGER_PRIVILEGES, user=user)
    revoke_table_privileges(bind, table="credit_wallets", privileges=WALLET_PRIVILEGES, user=user)
    op.drop_table("credit_ledger")
    op.drop_table("credit_wallets")
