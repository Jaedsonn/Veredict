from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import JsonValue

from veriditi_common.audit import AuditOutcome


@dataclass(frozen=True, slots=True)
class StoredAuditEvent:
    """Evento como gravado, com o id sequencial e o received_at do monitoring"""

    id: int
    event_id: UUID
    occurred_at: datetime
    received_at: datetime
    service: str
    action: str
    outcome: AuditOutcome
    actor_id: int | None
    actor_ip: str | None
    request_id: UUID | None
    resource_type: str | None
    resource_id: str | None
    metadata: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AuditEventFilter:
    """Janela semiaberta [occurred_from, occurred_to) para janelas vizinhas não repetirem evento"""

    actor_id: int | None = None
    action: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuditEventPage:
    items: list[StoredAuditEvent]
    next_cursor: int | None
