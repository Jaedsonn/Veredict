"""Schemas de data de cada e-mail; um template novo entra aqui e em templates/<nome>/"""

import unicodedata
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
)

from notification_service.registry import TemplateRegistry, TemplateSpec
from veriditi_common.notifications import NotificationTemplate


def _no_control_chars(value: str) -> str:
    """CR/LF e afins quebrariam o texto do e-mail e não existem num nome real"""
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("texto com caractere de controle")
    return value


# 120 é o tamanho de users.name (docs/banco-de-dados.md §5.1)
DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_no_control_chars),
]


class TemplateData(BaseModel):
    """Base dos schemas: campo extra é erro e o 422 não repete o valor recebido"""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class EmailVerificationData(TemplateData):
    name: DisplayName
    # Texto com 6 dígitos: int perderia o zero à esquerda (§5.2)
    code: Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
    expires_in_minutes: Annotated[StrictInt, Field(ge=1, le=1440)]


class WelcomeData(TemplateData):
    name: DisplayName


def build_registry() -> TemplateRegistry:
    return TemplateRegistry(
        [
            TemplateSpec(NotificationTemplate.EMAIL_VERIFICATION.value, EmailVerificationData),
            TemplateSpec(NotificationTemplate.WELCOME.value, WelcomeData),
        ]
    )
