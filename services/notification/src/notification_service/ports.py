from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel

from notification_service.domain import OutgoingEmail, RenderedEmail

Clock = Callable[[], datetime]
MessageIdFactory = Callable[[], str]


class EmailRenderer(Protocol):
    def render(self, template: str, data: BaseModel) -> RenderedEmail:
        """Assunto, texto e HTML a partir do data já validado pelo registry"""
        ...


class EmailSender(Protocol):
    async def send(self, email: OutgoingEmail) -> None:
        """Levanta EmailDeliveryError; permanent=True dispensa novas tentativas"""
        ...
