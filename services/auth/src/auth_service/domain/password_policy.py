"""Política de validação de senhas

Isola a política de força de senha: novas regras (`PasswordRule`) entram sem
modificar `PasswordPolicy`.
"""

from collections.abc import Sequence
from typing import Protocol

from auth_service.domain.errors import WeakPasswordError

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


class PasswordRule(Protocol):
    """Contrato de uma regra individual de validação de senha"""

    def check(self, password: str) -> str | None:
        """Retorna mensagem de erro em PT-BR se a senha violar a regra, ou `None` se válida"""


class MinLengthRule:
    def __init__(self, min_length: int = PASSWORD_MIN_LENGTH) -> None:
        self._min_length = min_length

    def check(self, password: str) -> str | None:
        if len(password) < self._min_length:
            return f"A senha deve ter pelo menos {self._min_length} caracteres."
        return None


class MaxLengthRule:
    def __init__(self, max_length: int = PASSWORD_MAX_LENGTH) -> None:
        self._max_length = max_length

    def check(self, password: str) -> str | None:
        if len(password) > self._max_length:
            return f"A senha deve ter no máximo {self._max_length} caracteres."
        return None


class ContainsLetterRule:
    def check(self, password: str) -> str | None:
        if not any(char.isalpha() for char in password):
            return "A senha deve conter pelo menos 1 letra."
        return None


class ContainsNumberRule:
    def check(self, password: str) -> str | None:
        if not any(char.isdigit() for char in password):
            return "A senha deve conter pelo menos 1 número."
        return None


DEFAULT_PASSWORD_RULES: tuple[PasswordRule, ...] = (
    MinLengthRule(),
    MaxLengthRule(),
    ContainsLetterRule(),
    ContainsNumberRule(),
)


class PasswordPolicy:
    """Validador de força de senha composto por regras extensíveis"""

    def __init__(self, rules: Sequence[PasswordRule] = DEFAULT_PASSWORD_RULES) -> None:
        self._rules = tuple(rules)

    def validate(self, password: str, *, field: str = "password") -> None:
        """Valida a senha contra todas as regras configuradas, levantando `WeakPasswordError`"""
        for rule in self._rules:
            error_msg = rule.check(password)
            if error_msg is not None:
                raise WeakPasswordError(error_msg, field=field)
