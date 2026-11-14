from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel

from notification_service.domain import OutgoingEmail, RenderedEmail, StoredNotification

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]
MessageIdFactory = Callable[[], str]
DeliveryTask = Callable[[], Awaitable[None]]


class EmailRenderer(Protocol):
    def render(self, template: str, data: BaseModel) -> RenderedEmail:
        """Assunto, texto e HTML a partir do data já validado pelo registry"""
        ...


class EmailSender(Protocol):
    async def send(self, email: OutgoingEmail) -> None:
        """Levanta EmailDeliveryError; permanent=True dispensa novas tentativas"""
        ...


class NotificationRepository(Protocol):
    async def add(self, idempotency_key: str, template: str, *, created_at: datetime) -> int | None:
        """id da reserva pending; None se a chave já existe (1062), sem SELECT antes"""
        ...

    async def get(self, idempotency_key: str) -> StoredNotification | None:
        """Só no caminho raro da duplicata, para o log dizer em que status ela está"""
        ...

    async def mark_sent(
        self, notification_id: int, *, attempts: int, message_id: str, sent_at: datetime
    ) -> bool:
        """Só sai de pending; False se a linha já não estava pending"""
        ...

    async def mark_failed(self, notification_id: int, *, attempts: int) -> bool:
        """Só sai de pending; False se a linha já não estava pending"""
        ...


class Scheduler(Protocol):
    def schedule(self, task: DeliveryTask) -> None:
        """Roda a tarefa depois da resposta; o caso de uso não sabe como"""
        ...
