from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel

from veriditi_common.audit import AuditEvent


class AuditEventIn(AuditEvent):
    """Sem os defaults do produtor, que quebrariam a idempotência e a correlação"""

    event_id: UUID
    occurred_at: AwareDatetime
    request_id: UUID | None


class AcceptedResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
