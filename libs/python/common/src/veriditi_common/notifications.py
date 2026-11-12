"""Contratos e clientes de disparo de notificações assíncronas (RF11, ADR-016)."""

from typing import Any, Protocol, runtime_checkable

import httpx
import structlog
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)


class NotificationRequest(BaseModel):
    """Trigger enviado ao serviço de Notificações (seção 4.2.3 do doc. arquitetural)."""

    template: str = Field(min_length=1, max_length=64)
    to: str = Field(min_length=3, max_length=255)
    data: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=128)


@runtime_checkable
class Notifier(Protocol):
    """Porta de saída (DIP/ISP) para envio de notificações."""

    async def send(self, request: NotificationRequest) -> None:
        """Envia uma solicitação de notificação."""


class HttpNotifier:
    """Adaptador HTTP para o serviço de Notificações (ADR-016, RNF02)."""

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

    async def send(self, request: NotificationRequest) -> None:
        payload = request.model_dump(mode="json")
        try:
            response = await self._client.post(
                f"{self._base_url}/internal/notifications",
                json=payload,
                headers={"X-Internal-Token": self._token},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error(
                "notification_delivery_failed",
                notification_fallback=True,
                error=str(exc),
                template=request.template,
                idempotency_key=request.idempotency_key,
            )


class InMemoryNotifier:
    """Adaptador em memória (LSP) para testes automatizados."""

    def __init__(self) -> None:
        self.sent: list[NotificationRequest] = []

    async def send(self, request: NotificationRequest) -> None:
        self.sent.append(request)

    def find_by_template(self, template: str) -> list[NotificationRequest]:
        return [item for item in self.sent if item.template == template]
