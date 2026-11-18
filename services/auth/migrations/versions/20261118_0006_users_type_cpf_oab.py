"""add user_type, cpf and oab to users ([S1-20], docs/banco-de-dados.md §5.1)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
)  # fmt: skip
OAB_MATCHES_TYPE = (
    "(user_type = 'lawyer' AND oab_number IS NOT NULL AND oab_uf IS NOT NULL"
    " AND oab_kind IS NOT NULL) OR (user_type = 'common' AND oab_number IS NULL"
    " AND oab_uf IS NULL AND oab_kind IS NULL)"
)


def upgrade() -> None:
    # Sem ambiente implantado (#17): um usuário antigo não tem CPF para preencher, e um
    # ADD COLUMN NOT NULL gravaria '' e quebraria o UNIQUE a partir da 2ª linha
    pending = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM users")).scalar_one()
    if pending:
        raise RuntimeError(
            f"{pending} usuário(s) sem CPF em users; rode `make reset` para recriar o banco "
            "de dev (não há ambiente implantado, #17)"
        )
    op.add_column("users", sa.Column("user_type", mysql.ENUM("common", "lawyer"), nullable=False))
    op.add_column("users", sa.Column("cpf_enc", mysql.VARBINARY(64), nullable=False))
    op.add_column(
        "users",
        sa.Column(
            "cpf_hmac", mysql.CHAR(64, charset="ascii", collation="ascii_bin"), nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "oab_number", mysql.VARCHAR(6, charset="ascii", collation="ascii_bin"), nullable=True
        ),
    )
    op.add_column("users", sa.Column("oab_uf", mysql.ENUM(*UFS), nullable=True))
    op.add_column(
        "users",
        sa.Column("oab_kind", mysql.ENUM("principal", "suplementar", "transitoria"), nullable=True),
    )
    op.create_unique_constraint(op.f("uq_users_cpf_hmac"), "users", ["cpf_hmac"])
    op.create_unique_constraint(
        op.f("uq_users_oab_uf_oab_number"), "users", ["oab_uf", "oab_number"]
    )
    op.create_check_constraint(op.f("ck_users_oab_matches_type"), "users", OAB_MATCHES_TYPE)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_oab_matches_type"), "users", type_="check")
    op.drop_constraint(op.f("uq_users_oab_uf_oab_number"), "users", type_="unique")
    op.drop_constraint(op.f("uq_users_cpf_hmac"), "users", type_="unique")
    op.drop_column("users", "oab_kind")
    op.drop_column("users", "oab_uf")
    op.drop_column("users", "oab_number")
    op.drop_column("users", "cpf_hmac")
    op.drop_column("users", "cpf_enc")
    op.drop_column("users", "user_type")
