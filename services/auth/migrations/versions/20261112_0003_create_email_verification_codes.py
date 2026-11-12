"""create email_verification_codes table ([S1-08], docs/banco-de-dados.md §5.2)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
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

PRIVILEGES = ["SELECT", "INSERT", "UPDATE", "DELETE"]


def upgrade() -> None:
    op.create_table(
        "email_verification_codes",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.BIGINT(), nullable=False),
        sa.Column(
            "purpose",
            mysql.ENUM("email_verification", "mfa"),
            server_default="email_verification",
            nullable=False,
        ),
        sa.Column(
            "code_hash",
            mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("attempts", mysql.TINYINT(), server_default="0", nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("consumed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_verification_codes")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_verification_codes_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_email_verification_codes_attempts_non_negative"),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_email_verification_codes_user_id_consumed_at",
        "email_verification_codes",
        ["user_id", "consumed_at"],
    )
    grant_table_privileges(
        op.get_bind(),
        table="email_verification_codes",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )


def downgrade() -> None:
    revoke_table_privileges(
        op.get_bind(),
        table="email_verification_codes",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    op.drop_index(
        "ix_email_verification_codes_user_id_consumed_at",
        table_name="email_verification_codes",
    )
    op.drop_table("email_verification_codes")
