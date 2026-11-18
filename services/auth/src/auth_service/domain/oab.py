"""Value object da inscrição na OAB, validada só pelo formato (#60; consulta ao CNA na #64)"""

import re
from dataclasses import dataclass
from typing import Self

from auth_service.domain.errors import InvalidOabError
from auth_service.models import OabKind, OabUf, UserType

OAB_NUMBER_MESSAGE = "Informe o número da OAB com até 6 dígitos."
OAB_UF_MESSAGE = "Escolha a UF da seccional."
OAB_KIND_MESSAGE = "Escolha o tipo de inscrição."
OAB_REQUIRED_MESSAGE = "Informe a inscrição na OAB."
OAB_NOT_ALLOWED_MESSAGE = "Só advogados informam OAB."

_NUMBER = re.compile(r"\d{1,6}")


def _parse_uf(raw: object) -> OabUf:
    cleaned = raw.strip().upper() if isinstance(raw, str) else ""
    if cleaned not in OabUf.__members__:
        raise InvalidOabError(OAB_UF_MESSAGE, field="oab.uf")
    return OabUf(cleaned)


def _parse_kind(raw: object) -> OabKind:
    cleaned = raw.strip().lower() if isinstance(raw, str) else ""
    if cleaned not in {kind.value for kind in OabKind}:
        raise InvalidOabError(OAB_KIND_MESSAGE, field="oab.kind")
    return OabKind(cleaned)


@dataclass(frozen=True, slots=True)
class Oab:
    """Número sem zeros à esquerda, para `001234/BA` e `1234/BA` serem a mesma inscrição"""

    number: str
    uf: OabUf
    kind: OabKind

    @classmethod
    def parse(cls, *, number: object, uf: object, kind: object) -> Self:
        if not isinstance(number, str) or not _NUMBER.fullmatch(cleaned := number.strip()):
            raise InvalidOabError(OAB_NUMBER_MESSAGE, field="oab.number")
        if int(cleaned) == 0:
            raise InvalidOabError(OAB_NUMBER_MESSAGE, field="oab.number")
        return cls(number=str(int(cleaned)), uf=_parse_uf(uf), kind=_parse_kind(kind))

    def __str__(self) -> str:
        return f"{self.number}/{self.uf}"


def check_oab_matches_type(user_type: UserType, oab: Oab | None) -> None:
    """Advogado precisa de OAB e conta comum não pode ter; o CHECK do banco repete a regra"""
    if user_type is UserType.LAWYER and oab is None:
        raise InvalidOabError(OAB_REQUIRED_MESSAGE)
    if user_type is UserType.COMMON and oab is not None:
        raise InvalidOabError(OAB_NOT_ALLOWED_MESSAGE)
