from typing import Any

from monitoring_service.domain import StoredAuditEvent
from monitoring_service.ports import AuditEventRepository, Clock, system_clock
from veriditi_common.audit import AuditEvent
from veriditi_common.logging import get_logger, redact

log = get_logger(__name__)


class IngestAuditEvent:
    """Grava o evento uma única vez, com o relógio do monitoring e sem segredos no metadata"""

    def __init__(self, events: AuditEventRepository, clock: Clock = system_clock) -> None:
        self._events = events
        self._clock = clock

    async def execute(self, event: AuditEvent) -> bool:
        # producer, não service: o processor _add_service sobrescreve essa chave
        context: dict[str, Any] = {
            "event_id": str(event.event_id),
            "action": event.action,
            "producer": event.service,
        }
        metadata = redact(event.metadata)
        if metadata != event.metadata:
            log.warning("audit_metadata_redacted", **context)
            event = event.model_copy(update={"metadata": metadata})

        created = await self._events.add(event, received_at=self._clock())
        log.info("audit_event_ingested" if created else "audit_event_duplicate", **context)
        if not created:
            await self._warn_on_conflict(event, context)
        return created

    async def _warn_on_conflict(self, event: AuditEvent, context: dict[str, Any]) -> None:
        stored = await self._events.get(event.event_id)
        if stored is not None and (diverging := _diverging_fields(event, stored)):
            # Só os nomes: os valores podem ser PII, e a 1ª escrita é a que vale
            log.warning("audit_event_conflict", **context, fields=diverging)


def _diverging_fields(event: AuditEvent, stored: StoredAuditEvent) -> list[str]:
    """Reenvio com o mesmo event_id e outro conteúdo indica bug no produtor"""
    incoming: dict[str, Any] = {
        "occurred_at": event.occurred_at,
        "service": event.service,
        "action": event.action,
        "outcome": event.outcome,
        "actor_id": event.actor_id,
        "actor_ip": str(event.actor_ip) if event.actor_ip is not None else None,
        "request_id": event.request_id,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "metadata": event.metadata,
    }
    return [name for name, value in incoming.items() if getattr(stored, name) != value]
