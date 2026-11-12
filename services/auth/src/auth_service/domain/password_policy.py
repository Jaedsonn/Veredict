"""Política de validação de senhas e regras de cadastro (SRP / OCP).

Aplica o Single Responsibility Principle (SRP) isolando a política de força de
senha e validação cadastral, e o Open/Closed Principle (OCP) ao permitir que
novas regras (`PasswordRule`) sejam adicionadas sem modificar `PasswordPolicy`.
"""

import re
from collections.abc import Sequence
from typing import Protocol

from auth_service.domain.errors import InvalidRegistrationDataError, WeakPasswordError
from auth_service.models import UserRole

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

_CPF_DIGITS_RE = re.compile(r"\D+")
_OAB_RE = re.compile(r"^[A-Za-z]{2}\s*-?\s*\d{3,10}[A-Za-z]?$|^\d{3,10}$")


class PasswordRule(Protocol):
    """Contrato de uma regra individual de validação de senha (OCP)."""

    def check(self, password: str) -> str | None:
        """Retorna mensagem de erro em PT-BR se a senha violar a regra, ou `None` se válida."""


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
    """Validador de força de senha composto por regras extensíveis (SRP + OCP)."""

    def __init__(self, rules: Sequence[PasswordRule] = DEFAULT_PASSWORD_RULES) -> None:
        self._rules = tuple(rules)

    def validate(self, password: str, *, field: str = "password") -> None:
        """Valida a senha contra todas as regras configuradas, levantando `WeakPasswordError`."""
        for rule in self._rules:
            error_msg = rule.check(password)
            if error_msg is not None:
                raise WeakPasswordError(error_msg, field=field)


def normalize_and_validate_cpf(raw_cpf: str | None) -> str | None:
    """Normaliza e valida o CPF (Apêndice A do Documento de Requisitos) quando informado."""
    if raw_cpf is None:
        return None
    cleaned = _CPF_DIGITS_RE.sub("", raw_cpf.strip())
    if not cleaned:
        return None
    if len(cleaned) != 11 or len(set(cleaned)) == 1:
        raise InvalidRegistrationDataError("Informe um CPF válido com 11 dígitos.", field="cpf")

    # Validação dos dígitos verificadores módulo 11
    for pos in (9, 10):
        total = sum(int(cleaned[idx]) * ((pos + 1) - idx) for idx in range(pos))
        digit = (total * 10 % 11) % 10
        if digit != int(cleaned[pos]):
            raise InvalidRegistrationDataError("Informe um CPF válido.", field="cpf")
    return cleaned


def validate_registration_profile(
    *,
    role: str | UserRole,
    cpf: str | None,
    oab_number: str | None,
) -> tuple[UserRole, str | None, str | None]:
    """Aplica a Decisão D1 e o Apêndice A do Documento de Requisitos (REQ 01).

    - D1: Na primeira versão do sistema, apenas advogados (`lawyer`) e usuários
      comuns (`common`) são cadastrados (empresas são recusadas).
    - Apêndice A: Advogado possui número da OAB obrigatório; CPF é validado quando
      informado.
    """
    normalized_role_str = role.value if isinstance(role, UserRole) else str(role).strip().lower()
    if normalized_role_str == "company":
        raise InvalidRegistrationDataError(
            "Na primeira versão do sistema, apenas advogados e usuários comuns "
            "podem ser cadastrados (Decisão D1).",
            field="role",
        )
    try:
        parsed_role = UserRole(normalized_role_str)
    except ValueError as exc:
        raise InvalidRegistrationDataError(
            "Tipo de conta inválido. Escolha entre usuário comum ou advogado.",
            field="role",
        ) from exc

    normalized_cpf = normalize_and_validate_cpf(cpf)
    normalized_oab = oab_number.strip().upper() if oab_number and oab_number.strip() else None

    if parsed_role == UserRole.LAWYER:
        if not normalized_oab:
            raise InvalidRegistrationDataError(
                "O número da OAB é obrigatório para o cadastro de advogados.",
                field="oab_number",
            )
        if not _OAB_RE.match(normalized_oab):
            raise InvalidRegistrationDataError(
                "Informe um número da OAB válido (ex.: BA12345).",
                field="oab_number",
            )
    elif normalized_oab is not None:
        # Caso o cliente envie oab_number sem especificar role="lawyer", promove para advogado
        if not _OAB_RE.match(normalized_oab):
            raise InvalidRegistrationDataError(
                "Informe um número da OAB válido (ex.: BA12345).",
                field="oab_number",
            )
        parsed_role = UserRole.LAWYER

    return parsed_role, normalized_cpf, normalized_oab
