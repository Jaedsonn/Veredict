"""Eventos de auditoria desacoplados do transporte (ADR-016); o monitoring os grava no #5"""

from datetime import UTC, datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Any, Final, Protocol
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, Request
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    IPvAnyAddress,
    JsonValue,
    SecretStr,
    field_validator,
    model_validator,
)

from veriditi_common.logging import get_logger
from veriditi_common.middleware import (
    MAX_IP_LENGTH,
    REQUEST_ID_HEADER,
    current_request_id,
    try_defer,
)
from veriditi_common.security import INTERNAL_TOKEN_HEADER

AUDIT_EVENTS_PATH: Final = "/internal/events"

_SEGMENT = r"[a-z][a-z0-9_]*"

log = get_logger(__name__)


def _request_id_from_context() -> UUID | None:
    """O evento carrega o request_id da requisição sem o caso de uso precisar passá-lo"""
    rid = current_request_id()
    if rid is None:
        return None
    try:
        return UUID(rid)
    except ValueError:
        return None


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditEvent(BaseModel):
    """Espelha o DDL de veriditi_logs.audit_events (docs/banco-de-dados.md §5.5)"""

    # O erro de validação não repete o metadata, que pode trazer senha
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    service: str = Field(min_length=1, max_length=40, pattern=rf"^{_SEGMENT}$")
    # <serviço>.<entidade>.<verbo_passado>, ex.: auth.user.registered
    action: str = Field(max_length=80, pattern=rf"^{_SEGMENT}\.{_SEGMENT}\.{_SEGMENT}$")
    outcome: AuditOutcome
    actor_id: int | None = Field(default=None, ge=1, le=2**63 - 1)
    actor_ip: IPvAnyAddress | None = None
    request_id: UUID | None = Field(default_factory=_request_id_from_context)
    resource_type: str | None = Field(default=None, min_length=1, max_length=40)
    resource_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("actor_ip")
    @classmethod
    def _ip_fits_column(
        cls, value: IPv4Address | IPv6Address | None
    ) -> IPv4Address | IPv6Address | None:
        """IPv6 com scope id (fe80::1%eth0) pode passar de VARCHAR(45)"""
        if value is not None and len(str(value)) > MAX_IP_LENGTH:
            raise ValueError(f"actor_ip passa de {MAX_IP_LENGTH} caracteres")
        return value

    @model_validator(mode="after")
    def _action_belongs_to_service(self) -> "AuditEvent":
        if self.action.split(".", 1)[0] != self.service:
            raise ValueError("action precisa começar com o service que emite o evento")
        return self


class AuditLogger(Protocol):
    async def record(self, event: AuditEvent) -> None: ...


class HttpAuditLogger:
    """Fire-and-forget: falha nunca sobe, o evento vai inteiro para o log (replay no #37)"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: SecretStr,
        *,
        timeout: float = 2.0,
    ) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}{AUDIT_EVENTS_PATH}"
        self._token = token
        self._timeout = timeout

    async def record(self, event: AuditEvent) -> None:
        try:
            # frozen não congela o dict de metadata: o dump pode falhar
            payload = event.model_dump(mode="json")
            headers = {INTERNAL_TOKEN_HEADER: self._token.get_secret_value()}
            if request_id := payload["request_id"] or current_request_id():
                headers[REQUEST_ID_HEADER] = request_id
            response = await self._client.post(
                self._url, json=payload, headers=headers, timeout=self._timeout
            )
            response.raise_for_status()
        # Também cobre client fechado no shutdown; CancelledError continua propagando
        except Exception as exc:
            extra: dict[str, Any] = {}
            if isinstance(exc, httpx.HTTPStatusError):
                extra["status_code"] = exc.response.status_code
            # Aninhado: espalhado, colidiria com service, request_id e event do próprio log
            log.error(
                "audit_delivery_failed",
                audit_fallback=True,
                error_type=type(exc).__name__,
                audit_event=_fallback_dump(event),
                **extra,
            )


def _fallback_dump(event: AuditEvent) -> dict[str, Any]:
    """Nunca levanta: metadata circular ou exótico cai num resumo com o event_id"""
    try:
        return event.model_dump(mode="json", fallback=repr, warnings=False)
    except Exception:
        return {
            "event_id": str(event.event_id),
            "service": event.service,
            "action": event.action,
            "outcome": event.outcome.value,
            "occurred_at": event.occurred_at.isoformat(),
        }


class InMemoryAuditLogger:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)

    def actions(self) -> list[str]:
        return [event.action for event in self.events]


class BackgroundAuditLogger:
    """Adia o envio para depois da resposta, mesmo de erro, sem o caso de uso saber disso"""

    def __init__(self, inner: AuditLogger, request: Request) -> None:
        self._inner = inner
        self._request = request

    async def record(self, event: AuditEvent) -> None:
        # Chamado depois da drenagem (ex.: task solta), envia já: o inner nunca levanta
        if not try_defer(self._request, self._inner.record, event):
            await self._inner.record(event)


def get_audit_logger(request: Request) -> AuditLogger:
    inner: AuditLogger | None = getattr(request.app.state, "audit_logger", None)
    if inner is None:
        raise RuntimeError("app.state.audit_logger não foi definido no lifespan")
    return BackgroundAuditLogger(inner, request)


AuditLoggerDep = Annotated[AuditLogger, Depends(get_audit_logger)]
