from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue

from veriditi_common.audit import AuditEvent, AuditOutcome


class AuditEventIn(AuditEvent):
    """Sem os defaults do produtor, que quebrariam a idempotência e a correlação"""

    event_id: UUID
    occurred_at: AwareDatetime
    request_id: UUID | None


class AcceptedResponse(BaseModel):
    status: Literal["accepted"] = "accepted"


class AuditEventOut(BaseModel):
    """Sem as validações da entrada: uma regra mais estrita não esconde linhas antigas"""

    model_config = ConfigDict(from_attributes=True)

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


class AuditEventsPage(BaseModel):
    items: list[AuditEventOut]
    next_cursor: int | None
