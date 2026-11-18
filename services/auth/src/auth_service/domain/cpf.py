"""Value object do CPF: normaliza, valida os dígitos verificadores e mascara (#60)"""

import re
from dataclasses import dataclass, field
from typing import Self

from auth_service.domain.errors import InvalidCpfError

# Com ou sem máscara, mas sem misturar outros separadores
_FORMAT = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")


def _check_digit(digits: str) -> int:
    weights = range(len(digits) + 1, 1, -1)
    return sum(int(d) * w for d, w in zip(digits, weights, strict=True)) * 10 % 11 % 10


def _is_valid(digits: str) -> bool:
    if len(digits) != 11 or not digits.isdigit() or len(set(digits)) == 1:
        return False
    first = _check_digit(digits[:9])
    second = _check_digit(digits[:9] + str(first))
    return digits[9:] == f"{first}{second}"


@dataclass(frozen=True, slots=True, repr=False)
class Cpf:
    """CPF válido com 11 dígitos; repr e str mostram só a máscara"""

    digits: str = field(repr=False)

    def __post_init__(self) -> None:
        if not _is_valid(self.digits):
            raise InvalidCpfError()

    @classmethod
    def parse(cls, raw: object) -> Self:
        """Aceita `529.982.247-25` ou `52998224725`; qualquer outra coisa é `InvalidCpfError`"""
        if not isinstance(raw, str) or not _FORMAT.fullmatch(cleaned := raw.strip()):
            raise InvalidCpfError()
        return cls(cleaned.replace(".", "").replace("-", ""))

    @property
    def masked(self) -> str:
        """`***.982.247-**`: o meio identifica o CPF para o dono sem expor o número inteiro"""
        return f"***.{self.digits[3:6]}.{self.digits[6:9]}-**"

    def __repr__(self) -> str:
        return f"Cpf({self.masked})"

    def __str__(self) -> str:
        return self.masked
