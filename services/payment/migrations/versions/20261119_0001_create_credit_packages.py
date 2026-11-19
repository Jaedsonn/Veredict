"""create credit_packages com os pacotes da D2

Revision ID: 0001
Revises:
Create Date: 2026-11-19
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

# O catálogo nasce aqui; o serviço só lê (§7)
PRIVILEGES = ["SELECT"]

# D2: básico, médio e premium; Apêndice A: nome, créditos, valor por crédito e benefícios
PACKAGES = [
    {
        "code": "basico",
        "name": "Básico",
        "credits": 5,
        "unit_price_cents": 500,
        "price_cents": 2500,
        "benefits": "Para registros pontuais: 5 capturas de tela ou 1 gravação de vídeo.",
        "highlight": False,
    },
    {
        "code": "medio",
        "name": "Médio",
        "credits": 20,
        "unit_price_cents": 400,
        "price_cents": 8000,
        "benefits": "Para quem registra com frequência: crédito 20% mais barato que no Básico.",
        "highlight": True,
    },
    {
        "code": "premium",
        "name": "Premium",
        "credits": 60,
        "unit_price_cents": 350,
        "price_cents": 21000,
        "benefits": (
            "Para escritórios e alto volume: o menor valor por crédito, 30% abaixo do Básico."
        ),
        "highlight": False,
    },
]


def upgrade() -> None:
    table = op.create_table(
        "credit_packages",
        sa.Column("id", mysql.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "code", mysql.VARCHAR(20, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("name", mysql.VARCHAR(60), nullable=False),
        sa.Column("credits", mysql.INTEGER(), nullable=False),
        sa.Column("unit_price_cents", mysql.INTEGER(), nullable=False),
        sa.Column("price_cents", mysql.INTEGER(), nullable=False),
        sa.Column(
            "currency",
            mysql.CHAR(3, charset="ascii", collation="ascii_bin"),
            server_default="BRL",
            nullable=False,
        ),
        sa.Column("benefits", mysql.VARCHAR(500), nullable=False),
        sa.Column("highlight", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_packages")),
        sa.UniqueConstraint("code", name=op.f("uq_credit_packages_code")),
        sa.CheckConstraint("credits > 0", name=op.f("ck_credit_packages_credits_positive")),
        sa.CheckConstraint(
            "unit_price_cents > 0", name=op.f("ck_credit_packages_unit_price_positive")
        ),
        sa.CheckConstraint(
            "price_cents = credits * unit_price_cents",
            name=op.f("ck_credit_packages_price_matches_unit"),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.bulk_insert(table, PACKAGES)
    grant_table_privileges(
        op.get_bind(),
        table="credit_packages",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )


def downgrade() -> None:
    revoke_table_privileges(
        op.get_bind(),
        table="credit_packages",
        privileges=PRIVILEGES,
        user=context.config.attributes["runtime_db_user"],
    )
    op.drop_table("credit_packages")
