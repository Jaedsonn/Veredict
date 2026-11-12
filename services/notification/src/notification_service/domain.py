from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NotificationStatus(StrEnum):
    """pending na reserva; sent e failed só por UPDATE condicional a partir de pending"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


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
