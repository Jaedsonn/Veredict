from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from monitoring_service.domain import AuditEventFilter, StoredAuditEvent
from veriditi_common.audit import AuditEvent

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


class AuditEventRepository(Protocol):
    async def add(self, event: AuditEvent, *, received_at: datetime) -> bool:
        """False quando o event_id já existe: o reenvio não duplica nem sobrescreve"""
        ...

    async def search(
        self, filters: AuditEventFilter, *, after_id: int | None, limit: int
    ) -> list[StoredAuditEvent]:
        """Em ordem de id crescente, só com id maior que after_id"""
        ...
