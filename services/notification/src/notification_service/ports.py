from typing import Protocol

from pydantic import BaseModel

from notification_service.domain import RenderedEmail


class EmailRenderer(Protocol):
    def render(self, template: str, data: BaseModel) -> RenderedEmail:
        """Assunto, texto e HTML a partir do data já validado pelo registry"""
        ...
