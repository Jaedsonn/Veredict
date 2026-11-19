"""Modelos ORM do `payment` (docs/banco-de-dados.md §5.7–§5.10)"""

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from payment_service.domain import LedgerReason, OrderStatus
from veriditi_common.db import make_metadata
from veriditi_common.db_types import (
    BigIntPK,
    UTCDateTime,
    UtcNow,
    UUIDStr,
    ascii_string,
    str_enum,
    utcnow,
)

ORDER_IDEMPOTENCY_UNIQUE: Final = "uq_orders_user_id_idempotency_key"
LEDGER_REFERENCE_UNIQUE: Final = "uq_credit_ledger_reason_reference_id"


class Base(DeclarativeBase):
    """MetaData próprio do payment com a naming_convention do contrato"""

    metadata = make_metadata()


class CreditPackageRecord(Base):
    """Catálogo da D2; o seed vem da migration e o runtime só lê"""

    __tablename__ = "credit_packages"
    __table_args__ = (
        CheckConstraint("credits > 0", name="credits_positive"),
        CheckConstraint("unit_price_cents > 0", name="unit_price_positive"),
        CheckConstraint("price_cents = credits * unit_price_cents", name="price_matches_unit"),
    )

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(ascii_string(20), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    credits: Mapped[int] = mapped_column(Integer())
    unit_price_cents: Mapped[int] = mapped_column(Integer())
    price_cents: Mapped[int] = mapped_column(Integer())
    currency: Mapped[str] = mapped_column(ascii_string(3, fixed=True), server_default="BRL")
    benefits: Mapped[str] = mapped_column(String(500))
    highlight: Mapped[bool] = mapped_column(Boolean(), server_default="0")
    active: Mapped[bool] = mapped_column(Boolean(), server_default="1")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=UtcNow())


class OrderRecord(Base):
    """Pedido com o snapshot do pacote e do faturamento; o CPF só mascarado"""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name=ORDER_IDEMPOTENCY_UNIQUE),
        Index(None, "user_id", "created_at"),
        # A FK exige índice no InnoDB; declarado para o `alembic check` não acusar diferença
        Index(None, "package_id"),
        CheckConstraint("credits > 0", name="credits_positive"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint("status <> 'paid' OR paid_at IS NOT NULL", name="paid_requires_paid_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDStr(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger())
    package_id: Mapped[int] = mapped_column(ForeignKey("credit_packages.id", ondelete="RESTRICT"))
    credits: Mapped[int] = mapped_column(Integer())
    amount_cents: Mapped[int] = mapped_column(Integer())
    status: Mapped[OrderStatus] = mapped_column(
        str_enum(OrderStatus, "status"), server_default=OrderStatus.PENDING.value
    )
    provider: Mapped[str] = mapped_column(ascii_string(30))
    provider_payment_id: Mapped[str | None] = mapped_column(ascii_string(80), unique=True)
    pix_copy_paste: Mapped[str | None] = mapped_column(Text())
    idempotency_key: Mapped[str] = mapped_column(ascii_string(80))
    billing_name: Mapped[str] = mapped_column(String(120))
    billing_email: Mapped[str] = mapped_column(String(255))
    billing_phone: Mapped[str] = mapped_column(ascii_string(11))
    billing_cpf_masked: Mapped[str] = mapped_column(ascii_string(14, fixed=True))
    billing_cep: Mapped[str] = mapped_column(ascii_string(8, fixed=True))
    billing_street: Mapped[str] = mapped_column(String(120))
    billing_number: Mapped[str] = mapped_column(String(10))
    billing_complement: Mapped[str | None] = mapped_column(String(60))
    billing_district: Mapped[str] = mapped_column(String(60))
    billing_city: Mapped[str] = mapped_column(String(60))
    billing_state: Mapped[str] = mapped_column(ascii_string(2, fixed=True))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=UtcNow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, server_default=UtcNow()
    )


class CreditWalletRecord(Base):
    """Saldo atual; é o cache do SUM(delta) do ledger"""

    __tablename__ = "credit_wallets"
    __table_args__ = (CheckConstraint("balance >= 0", name="balance_not_negative"),)

    user_id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=False)
    balance: Mapped[int] = mapped_column(Integer(), server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=UtcNow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, server_default=UtcNow()
    )


class CreditLedgerRecord(Base):
    """Append-only: toda mudança de saldo é uma linha nova (o payment_svc não tem UPDATE)"""

    __tablename__ = "credit_ledger"
    __table_args__ = (
        UniqueConstraint("reason", "reference_id", name=LEDGER_REFERENCE_UNIQUE),
        Index(None, "user_id", "id"),
        CheckConstraint("delta <> 0", name="delta_not_zero"),
        CheckConstraint("balance_after >= 0", name="balance_after_not_negative"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("credit_wallets.user_id", ondelete="RESTRICT"))
    delta: Mapped[int] = mapped_column(Integer())
    reason: Mapped[LedgerReason] = mapped_column(str_enum(LedgerReason, "reason"))
    reference_id: Mapped[str] = mapped_column(ascii_string(64))
    balance_after: Mapped[int] = mapped_column(Integer())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=UtcNow()
    )
