"""Schemas de data de cada e-mail; um template novo entra aqui e em templates/<nome>/"""

import unicodedata
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
)

from notification_service.registry import TemplateRegistry, TemplateSpec
from veriditi_common.notifications import NotificationTemplate

# Controle (CR, LF, TAB, NUL, DEL) e separadores de linha e parágrafo (U+2028, U+2029)
_BREAKING_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})


def _normalize_name(value: object) -> object:
    """Normaliza em vez de recusar: o auth só apara, e um 422 aqui prenderia a conta em pending"""
    if not isinstance(value, str):
        return value
    spaced = "".join(
        " " if unicodedata.category(char) in _BREAKING_CATEGORIES else char for char in value
    )
    return " ".join(spaced.split())


# 120 é o tamanho de users.name (docs/banco-de-dados.md §5.1); o BeforeValidator roda antes
DisplayName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=120),
    BeforeValidator(_normalize_name),
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
