import copy
from datetime import datetime
from uuid import UUID

from monitoring_service.domain import AuditEventFilter, StoredAuditEvent
from veriditi_common.audit import AuditEvent


class InMemoryAuditEventRepository:
    """Fake com a semântica do adapter SQL: UNIQUE por event_id e id sequencial"""

    def __init__(self) -> None:
        self.rows: list[StoredAuditEvent] = []

    async def add(self, event: AuditEvent, *, received_at: datetime) -> bool:
        if any(row.event_id == event.event_id for row in self.rows):
            return False
        self.rows.append(
            StoredAuditEvent(
                id=len(self.rows) + 1,
                event_id=event.event_id,
                occurred_at=event.occurred_at,
                received_at=received_at,
                service=event.service,
                action=event.action,
                outcome=event.outcome,
                actor_id=event.actor_id,
                actor_ip=str(event.actor_ip) if event.actor_ip is not None else None,
                request_id=event.request_id,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                metadata=copy.deepcopy(event.metadata),
            )
        )
        return True

    async def get(self, event_id: UUID) -> StoredAuditEvent | None:
        return next((row for row in self.rows if row.event_id == event_id), None)

    async def search(
        self, filters: AuditEventFilter, *, after_id: int | None, limit: int
    ) -> list[StoredAuditEvent]:
        found = [row for row in self.rows if _matches(row, filters, after_id)]
        return sorted(found, key=lambda row: row.id)[:limit]


def _matches(row: StoredAuditEvent, filters: AuditEventFilter, after_id: int | None) -> bool:
    return (
        (after_id is None or row.id > after_id)
        and (filters.actor_id is None or row.actor_id == filters.actor_id)
        and (filters.action is None or row.action == filters.action)
        and (filters.occurred_from is None or row.occurred_at >= filters.occurred_from)
        and (filters.occurred_to is None or row.occurred_at < filters.occurred_to)
    )
