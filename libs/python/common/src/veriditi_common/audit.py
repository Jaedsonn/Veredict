"""Contratos e clientes de auditoria estruturada (ADR-001, ADR-012, ADR-016)."""

import enum
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import httpx
import structlog
from pydantic import BaseModel, Field, field_validator

from veriditi_common.db_types import utcnow

log = structlog.get_logger(__name__)

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "password_hash",
        "token",
        "refresh_token",
        "access_token",
        "code",
        "secret",
        "totp_secret",
    }
)


def sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Remove recursivamente chaves sensíveis de metadados antes de gravar ou enviar."""
    if metadata is None:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized_key = str(key).lower()
        if normalized_key in SENSITIVE_KEYS or any(
            secret in normalized_key for secret in ("password", "token", "secret", "code")
        ):
            continue
        if isinstance(value, Mapping):
            cleaned[str(key)] = sanitize_metadata(value)
        else:
            cleaned[str(key)] = value
    return cleaned


class AuditOutcome(enum.StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditEvent(BaseModel):
    """Evento imutável de auditoria emitido pelos serviços (ADR-001 / RF18)."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    occurred_at: datetime = Field(default_factory=utcnow)
    service: str = Field(min_length=1, max_length=40)
    action: str = Field(min_length=1, max_length=80)
    outcome: AuditOutcome
    actor_id: int | None = None
    actor_ip: str | None = Field(default=None, max_length=45)
    request_id: uuid.UUID | None = None
    resource_type: str | None = Field(default=None, max_length=40)
    resource_id: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] | None = None

    @field_validator("metadata", mode="before")
    @classmethod
    def _strip_sensitive_fields(cls, value: Any) -> dict[str, Any] | None:
        if isinstance(value, Mapping):
            return sanitize_metadata(value)
        return None


@runtime_checkable
class AuditLogger(Protocol):
    """Porta de saída (DIP/ISP) para emissão de eventos de auditoria."""

    async def record(self, event: AuditEvent) -> None:
        """Registra um evento de auditoria sem interromper o fluxo de negócio."""


class HttpAuditLogger:
    """Adaptador HTTP para o serviço de Monitoramento (ADR-016).

    Respeita RNF02 (Confiabilidade): falhas de rede ou indisponibilidade do
    Monitoramento nunca derrubam a requisição do usuário; o evento é gravado
    no log estruturado com `audit_fallback=True`.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: str,
        *,
        timeout: float = 2.0,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    async def record(self, event: AuditEvent) -> None:
        payload = event.model_dump(mode="json")
        try:
            response = await self._client.post(
                f"{self._base_url}/internal/events",
                json=payload,
                headers={"X-Internal-Token": self._token},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error(
                "audit_delivery_failed",
                audit_fallback=True,
                error=str(exc),
                **payload,
            )


class InMemoryAuditLogger:
    """Adaptador em memória (LSP) para testes unitários e de integração rápida."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)

    def find(self, action: str) -> list[AuditEvent]:
        return [event for event in self.events if event.action == action]
