import json
import math
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    JsonValue,
    field_validator,
)

from veriditi_common.audit import AuditEvent, AuditOutcome

MAX_METADATA_BYTES: Final = 16 * 1024
MAX_METADATA_DEPTH: Final = 8
# Faixa do BIGINT com sinal: o JSON do MySQL recusa inteiros que não cabem em 64 bits
MIN_JSON_INT: Final = -(2**63)
MAX_JSON_INT: Final = 2**63 - 1
# Faixa documentada do DATETIME do MySQL
MIN_YEAR: Final = 1000
MAX_YEAR: Final = 9999


def _storable_datetime(value: datetime) -> datetime:
    """Em UTC e dentro do DATETIME; fora disso o banco recusaria e a resposta seria 500"""
    try:
        utc = value.astimezone(UTC)
    except OverflowError:
        raise ValueError("data fora do intervalo representável em UTC") from None
    if not MIN_YEAR <= utc.year <= MAX_YEAR:
        raise ValueError(f"data precisa estar entre os anos {MIN_YEAR} e {MAX_YEAR} em UTC")
    return utc


StorableDatetime = Annotated[AwareDatetime, AfterValidator(_storable_datetime)]


def _check_text(value: str) -> None:
    """Surrogate solto (\\ud800 no JSON) não é codificável em UTF-8 e o MySQL o recusa"""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("texto com caractere inválido em UTF-8") from None


def _check_scalar(value: object) -> None:
    if isinstance(value, str):
        _check_text(value)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("metadata não aceita NaN nem Infinity")
    elif isinstance(value, int) and not MIN_JSON_INT <= value <= MAX_JSON_INT:
        raise ValueError("inteiro do metadata precisa caber em 64 bits com sinal")


def _children(node: object) -> Iterable[object] | None:
    if isinstance(node, dict):
        return node.values()
    if isinstance(node, list | tuple):
        return node
    return None


def _check_json(value: object) -> None:
    """Iterativa: um JSON aninhado de propósito não estoura a pilha do Python"""
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        node, level = pending.pop()
        children = _children(node)
        if children is None:
            _check_scalar(node)
            continue
        if level > MAX_METADATA_DEPTH:
            raise ValueError(f"metadata passa de {MAX_METADATA_DEPTH} níveis")
        if isinstance(node, dict):
            for key in node:
                if isinstance(key, str):
                    _check_text(key)
        pending.extend((child, level + 1) for child in children)


class AuditEventIn(AuditEvent):
    """Sem os defaults do produtor, que quebrariam a idempotência e a correlação"""

    event_id: UUID
    occurred_at: StorableDatetime
    request_id: UUID | None

    @field_validator("resource_type", "resource_id")
    @classmethod
    def _utf8_text(cls, value: str | None) -> str | None:
        if value is not None:
            _check_text(value)
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def _metadata_storable(cls, value: Any) -> Any:
        """Antes do Pydantic: profundidade, NaN, inteiros e UTF-8 que o MySQL recusaria"""
        _check_json(value)
        return value

    @field_validator("metadata")
    @classmethod
    def _metadata_size(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_METADATA_BYTES:
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
