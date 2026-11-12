from typing import Any

from monitoring_service.ports import AuditEventRepository, Clock
from veriditi_common.audit import AuditEvent
from veriditi_common.db_types import utcnow
from veriditi_common.logging import get_logger, redact

log = get_logger(__name__)


class IngestAuditEvent:
    """Grava o evento uma única vez, com o relógio do monitoring e sem segredos no metadata"""

    def __init__(self, events: AuditEventRepository, clock: Clock = utcnow) -> None:
        self._events = events
        self._clock = clock

    async def execute(self, event: AuditEvent) -> bool:
        # producer, não service: o processor _add_service sobrescreve essa chave
        fields: dict[str, Any] = {
            "event_id": str(event.event_id),
            "action": event.action,
            "producer": event.service,
        }
        metadata = redact(event.metadata)
        if metadata != event.metadata:
            log.warning("audit_metadata_redacted", **fields)
            event = event.model_copy(update={"metadata": metadata})

        created = await self._events.add(event, received_at=self._clock())
        log.info("audit_event_ingested" if created else "audit_event_duplicate", **fields)
        return created
