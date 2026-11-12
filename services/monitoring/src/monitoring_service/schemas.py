import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue, field_validator

from veriditi_common.audit import AuditEvent, AuditOutcome

MAX_METADATA_BYTES: Final = 16 * 1024
MAX_METADATA_DEPTH: Final = 8


def _children(node: object) -> Iterable[object] | None:
    if isinstance(node, dict):
        return node.values()
    if isinstance(node, list | tuple):
        return node
    return None


def _depth(value: object) -> int:
    """Iterativa: um JSON aninhado de propósito não estoura a pilha do Python"""
    deepest = 0
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending and deepest <= MAX_METADATA_DEPTH:
        node, level = pending.pop()
        children = _children(node)
        if children is None:
            continue
        deepest = max(deepest, level)
        pending.extend((child, level + 1) for child in children)
    return deepest


class AuditEventIn(AuditEvent):
    """Sem os defaults do produtor, que quebrariam a idempotência e a correlação"""

    event_id: UUID
    occurred_at: AwareDatetime
    request_id: UUID | None

    @field_validator("metadata", mode="before")
    @classmethod
    def _metadata_depth(cls, value: Any) -> Any:
        if _depth(value) > MAX_METADATA_DEPTH:
            raise ValueError(f"metadata passa de {MAX_METADATA_DEPTH} níveis")
        return value

    @field_validator("metadata")
    @classmethod
    def _metadata_size(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8", "surrogatepass")) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata passa de {MAX_METADATA_BYTES} bytes em JSON")
        return value


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
