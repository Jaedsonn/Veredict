from datetime import datetime
from typing import Final

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from notification_service.domain import NotificationStatus
from veriditi_common.db import make_metadata
from veriditi_common.db_types import BigIntPK, UTCDateTime, UtcNow, ascii_string, str_enum

IDEMPOTENCY_KEY_UNIQUE: Final = "uq_notifications_sent_idempotency_key"

TinyInt = sa.SmallInteger().with_variant(mysql.TINYINT(), "mysql")


class Base(DeclarativeBase):
    """MetaData próprio do notification com a naming_convention do contrato"""

    metadata = make_metadata()


class NotificationRecord(Base):
    """Reserva idempotente por chave (docs/banco-de-dados.md §5.4); sem destinatário"""

    __tablename__ = "notifications_sent"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("status <> 'sent' OR sent_at IS NOT NULL", name="sent_requires_sent_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(ascii_string(128), unique=True)
    template: Mapped[str] = mapped_column(String(64))
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus, "status"),
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(TinyInt, default=0, server_default=sa.text("0"))
    message_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=UtcNow())
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
