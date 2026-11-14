"""add auth columns to users ([S1-07], docs/banco-de-dados.md §5.1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", mysql.VARCHAR(255), nullable=False))
    op.add_column(
        "users",
        sa.Column(
            "status",
            mysql.ENUM("pending_verification", "active", "blocked"),
            server_default="pending_verification",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", mysql.DATETIME(fsp=6), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
    )
    if op.get_bind().dialect.name == "mysql":
        op.create_check_constraint(
            op.f("ck_users_active_requires_verified"),
            "users",
            "status <> 'active' OR email_verified_at IS NOT NULL",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.drop_constraint(op.f("ck_users_active_requires_verified"), "users", type_="check")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "status")
    op.drop_column("users", "password_hash")
