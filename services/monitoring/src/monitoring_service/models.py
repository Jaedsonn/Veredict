import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import JSON, BigInteger, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from veriditi_common.audit import AuditOutcome
from veriditi_common.db import make_metadata
from veriditi_common.db_types import BigIntPK, UTCDateTime, UtcNow, UUIDStr, str_enum

EVENT_ID_UNIQUE: Final = "uq_audit_events_event_id"


class Base(DeclarativeBase):
    """MetaData próprio do monitoring com a naming_convention do contrato"""

    metadata = make_metadata()


class AuditEventRecord(Base):
    """Trilha append-only (docs/banco-de-dados.md §5.5); prev_hash e hash entram no #34"""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index(None, "actor_id", "occurred_at"),
        Index(None, "action", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUIDStr(), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=UtcNow())
    service: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[AuditOutcome] = mapped_column(str_enum(AuditOutcome, "outcome"))
    actor_id: Mapped[int | None] = mapped_column(BigInteger())
    actor_ip: Mapped[str | None] = mapped_column(String(45))
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUIDStr())
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    # metadata é reservado no declarativo; none_as_null grava NULL de SQL, não o JSON null
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON(none_as_null=True))
