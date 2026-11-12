import copy
from datetime import datetime

from monitoring_service.domain import StoredAuditEvent
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
