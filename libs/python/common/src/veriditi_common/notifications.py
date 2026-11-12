"""Pedidos de e-mail desacoplados do transporte (ADR-016); o notification os envia no #6"""

from enum import StrEnum
from typing import Annotated, Any, Final, Protocol

import httpx
from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, JsonValue, SecretStr

from veriditi_common.logging import get_logger, mask_email
from veriditi_common.middleware import REQUEST_ID_HEADER, current_request_id, defer
from veriditi_common.security import INTERNAL_TOKEN_HEADER

NOTIFICATIONS_PATH: Final = "/internal/notifications"

log = get_logger(__name__)


class NotificationTemplate(StrEnum):
    """Catálogo conhecido; quem valida contra o registry de templates é o #6"""

    EMAIL_VERIFICATION = "email_verification"
    WELCOME = "welcome"


class NotificationRequest(BaseModel):
    """Espelha veriditi.notifications_sent (§5.4); to e data ficam fora do repr"""

    # O erro de validação não repete o data, que leva o código
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    template: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    # O email-validator já recusa endereço com mais de 254 caracteres
    to: EmailStr = Field(repr=False)
    data: dict[str, JsonValue] = Field(default_factory=dict, repr=False)


class Notifier(Protocol):
    async def send(self, request: NotificationRequest) -> None: ...


class HttpNotifier:
    """Fire-and-forget: falha nunca sobe e o log não leva data nem o e-mail em claro"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: SecretStr,
        *,
        timeout: float = 2.0,
    ) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}{NOTIFICATIONS_PATH}"
        self._token = token
        self._timeout = timeout

    async def send(self, request: NotificationRequest) -> None:
        try:
            headers = {INTERNAL_TOKEN_HEADER: self._token.get_secret_value()}
            if request_id := current_request_id():
                headers[REQUEST_ID_HEADER] = request_id
            response = await self._client.post(
                self._url,
                json=request.model_dump(mode="json"),
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            extra: dict[str, Any] = {}
            if isinstance(exc, httpx.HTTPStatusError):
                extra["status_code"] = exc.response.status_code
            # Sem data (tem o código) não dá para reenviar pelo log; a web tem o reenvio (#13)
            log.error(
                "notification_delivery_failed",
                notification_fallback=True,
                template=request.template,
                idempotency_key=request.idempotency_key,
                to_masked=mask_email(request.to),
                error_type=type(exc).__name__,
                **extra,
            )


class InMemoryNotifier:
    def __init__(self) -> None:
        self.sent: list[NotificationRequest] = []

    async def send(self, request: NotificationRequest) -> None:
        self.sent.append(request)


class BackgroundNotifier:
    """Adia o envio para depois da resposta, mesmo de erro, sem o caso de uso saber disso"""

    def __init__(self, inner: Notifier, http_request: Request) -> None:
        self._inner = inner
        self._http_request = http_request

    async def send(self, request: NotificationRequest) -> None:
        defer(self._http_request, self._inner.send, request)


def get_notifier(request: Request) -> Notifier:
    inner: Notifier | None = getattr(request.app.state, "notifier", None)
    if inner is None:
        raise RuntimeError("app.state.notifier não foi definido no lifespan")
    return BackgroundNotifier(inner, request)


NotifierDep = Annotated[Notifier, Depends(get_notifier)]
