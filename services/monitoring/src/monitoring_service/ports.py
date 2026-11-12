from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from veriditi_common.audit import AuditEvent

Clock = Callable[[], datetime]


class AuditEventRepository(Protocol):
    async def add(self, event: AuditEvent, *, received_at: datetime) -> bool:
        """False quando o event_id já existe: o reenvio não duplica nem sobrescreve"""
        ...
