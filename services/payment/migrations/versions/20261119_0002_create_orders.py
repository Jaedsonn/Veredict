"""create orders com o snapshot do pacote e do faturamento

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

from veriditi_common.migrations import grant_table_privileges, revoke_table_privileges

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sem DELETE: pedido muda de status, nunca some
PRIVILEGES = ["SELECT", "INSERT", "UPDATE"]


def _ascii(length: int, *, fixed: bool = False) -> mysql.CHAR | mysql.VARCHAR:
    if fixed:
        return mysql.CHAR(length, charset="ascii", collation="ascii_bin")
    return mysql.VARCHAR(length, charset="ascii", collation="ascii_bin")


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", _ascii(36, fixed=True), nullable=False),
        sa.Column("user_id", mysql.BIGINT(), nullable=False),
        sa.Column("package_id", mysql.INTEGER(), nullable=False),
        sa.Column("credits", mysql.INTEGER(), nullable=False),
        sa.Column("amount_cents", mysql.INTEGER(), nullable=False),
        sa.Column(
            "status",
            mysql.ENUM("pending", "paid", "expired", "failed"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("provider", _ascii(30), nullable=False),
        sa.Column("provider_payment_id", _ascii(80), nullable=True),
        sa.Column("pix_copy_paste", mysql.TEXT(), nullable=True),
        sa.Column("idempotency_key", _ascii(80), nullable=False),
        sa.Column("billing_name", mysql.VARCHAR(120), nullable=False),
        sa.Column("billing_email", mysql.VARCHAR(255), nullable=False),
        sa.Column("billing_phone", _ascii(11), nullable=False),
        sa.Column("billing_cpf_masked", _ascii(14, fixed=True), nullable=False),
        sa.Column("billing_cep", _ascii(8, fixed=True), nullable=False),
        sa.Column("billing_street", mysql.VARCHAR(120), nullable=False),
        sa.Column("billing_number", mysql.VARCHAR(10), nullable=False),
        sa.Column("billing_complement", mysql.VARCHAR(60), nullable=True),
        sa.Column("billing_district", mysql.VARCHAR(60), nullable=False),
        sa.Column("billing_city", mysql.VARCHAR(60), nullable=False),
        sa.Column("billing_state", _ascii(2, fixed=True), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("paid_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name=op.f("uq_orders_user_id_idempotency_key")
        ),
        sa.UniqueConstraint("provider_payment_id", name=op.f("uq_orders_provider_payment_id")),
        sa.CheckConstraint("credits > 0", name=op.f("ck_orders_credits_positive")),
        sa.CheckConstraint("amount_cents > 0", name=op.f("ck_orders_amount_positive")),
        sa.CheckConstraint(
            "status <> 'paid' OR paid_at IS NOT NULL", name=op.f("ck_orders_paid_requires_paid_at")
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(op.f("ix_orders_user_id_created_at"), "orders", ["user_id", "created_at"])
    op.create_index(op.f("ix_orders_package_id"), "orders", ["package_id"])
    op.create_foreign_key(
        op.f("fk_orders_package_id_credit_packages"),
        "orders",
        "credit_packages",
        ["package_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    grant_table_privileges(
        op.get_bind(),
        table="orders",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )


def downgrade() -> None:
    revoke_table_privileges(
        op.get_bind(),
        table="orders",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    op.drop_table("orders")
