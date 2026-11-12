from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class NotificationStatus(StrEnum):
    """pending na reserva; sent e failed só por UPDATE condicional a partir de pending"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StoredNotification:
    """Linha de notifications_sent: sem destinatário nem data, por desenho (§5.4)"""

    id: int
    idempotency_key: str
    template: str
    status: NotificationStatus
    attempts: int
    message_id: str | None
    created_at: datetime
    sent_at: datetime | None


class UnknownTemplateError(Exception):
    """Nome fora do registry; valid vai ordenado para a mensagem do 422"""

    def __init__(self, template: str, valid: tuple[str, ...]) -> None:
        super().__init__(f"Template desconhecido: {template}")
        self.template = template
        self.valid = valid


class InvalidTemplateDataError(Exception):
    """Erros do schema do template só com type, loc e msg: o valor recebido nunca volta"""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("data inválido para o template")
        self.errors = errors


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    """Corpo fora do repr: o texto leva o código de verificação"""

    subject: str
    text: str = field(repr=False)
    html: str = field(repr=False)


class TemplateRenderError(Exception):
    """Template que gera um e-mail inválido; é bug de template, não erro de entrada"""


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    """Mesmo objeto em todas as tentativas: o Message-ID repetido deixa o MTA deduplicar"""

    to: str = field(repr=False)
    subject: str
    text: str = field(repr=False)
    html: str = field(repr=False)
    message_id: str


class EmailDeliveryError(Exception):
    """Falha de envio sem o endereço: reason é o tipo do erro, nunca a mensagem do servidor"""

    def __init__(
        self, reason: str, *, permanent: bool = False, smtp_code: int | None = None
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.permanent = permanent
        self.smtp_code = smtp_code
