"""Schemas Pydantic (contratos de entrada e saída HTTP) do serviço de Autenticação"""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from auth_service.domain.cpf import Cpf
from auth_service.domain.errors import InvalidFieldError
from auth_service.domain.oab import (
    OAB_NOT_ALLOWED_MESSAGE,
    OAB_REQUIRED_MESSAGE,
    parse_oab_kind,
    parse_oab_number,
    parse_oab_uf,
)
from auth_service.models import OabKind, OabUf, UserStatus, UserType

_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_DIGITS_6_RE = re.compile(r"^\d{6}$")


def _validate_and_normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Informe um e-mail válido.")
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("Informe seu e-mail.")
    try:
        _EMAIL_ADAPTER.validate_python(cleaned)
    except ValidationError as exc:
        raise ValueError("Informe um e-mail válido.") from exc
    return cleaned


def _domain_rule[T](parse: Callable[[object], T], value: object) -> T:
    """Roda a regra do domínio e devolve o erro dela com a mensagem exata, sem o valor"""
    try:
        return parse(value)
    except InvalidFieldError as exc:
        raise PydanticCustomError(exc.code, exc.message) from None


def _parse_user_type(raw: object) -> UserType:
    if isinstance(raw, str) and raw in {kind.value for kind in UserType}:
        return UserType(raw)
    raise PydanticCustomError("invalid_user_type", "Escolha o tipo de conta.")


class OabRequest(BaseModel):
    """Inscrição na OAB aninhada no cadastro; cada parte com o seu `loc` no 422 (#60)"""

    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    number: str = Field(default="", validate_default=True)
    uf: OabUf = Field(default=None, validate_default=True)
    kind: OabKind = Field(default=None, validate_default=True)

    @field_validator("number", mode="plain")
    @classmethod
    def _validate_number(cls, value: object) -> str:
        return _domain_rule(parse_oab_number, value)

    @field_validator("uf", mode="plain")
    @classmethod
    def _validate_uf(cls, value: object) -> OabUf:
        return _domain_rule(parse_oab_uf, value)

    @field_validator("kind", mode="plain")
    @classmethod
    def _validate_kind(cls, value: object) -> OabKind:
        return _domain_rule(parse_oab_kind, value)


class RegisterRequest(BaseModel):
    """Contrato de entrada de `POST /auth/register` ([S1-07], RF01; tipo, CPF e OAB na #60)"""

    # O CPF não aparece no repr nem volta no 422 (veriditi_common.errors já tira o input)
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    name: str
    email: str
    password: str = Field(repr=False)
    user_type: UserType = Field(default=None, validate_default=True)
    # Dígitos já normalizados; a máscara é só da web
    cpf: str = Field(default="", repr=False, validate_default=True)
    oab: OabRequest | None = Field(default=None, validate_default=True)

    @field_validator("user_type", mode="plain")
    @classmethod
    def _validate_user_type(cls, value: object) -> UserType:
        return _parse_user_type(value)

    @field_validator("cpf", mode="plain")
    @classmethod
    def _validate_cpf(cls, value: object) -> str:
        return _domain_rule(Cpf.parse, value).digits

    @field_validator("oab", mode="before")
    @classmethod
    def _oab_must_be_object(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, dict):
            raise PydanticCustomError("invalid_oab", OAB_REQUIRED_MESSAGE)
        return value

    @field_validator("oab")
    @classmethod
    def _oab_matches_type(cls, value: OabRequest | None, info: ValidationInfo) -> OabRequest | None:
        user_type = info.data.get("user_type")
        if user_type is UserType.LAWYER and value is None:
            raise PydanticCustomError("invalid_oab", OAB_REQUIRED_MESSAGE)
        if user_type is UserType.COMMON and value is not None:
            raise PydanticCustomError("invalid_oab", OAB_NOT_ALLOWED_MESSAGE)
        return value

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Informe seu nome.")
        if len(cleaned) > 120:
            raise ValueError("O nome deve ter no máximo 120 caracteres.")
        return cleaned

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _validate_and_normalize_email(value)


class RegisterResponse(BaseModel):
    """Contrato de saída de `POST /auth/register` (`201 Created`)"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    status: UserStatus
    user_type: UserType


class VerifyEmailRequest(BaseModel):
    """Contrato de entrada de `POST /auth/verify-email` ([S1-08], RF02)"""

    model_config = ConfigDict(extra="ignore")

    email: str
    code: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _validate_and_normalize_email(value)

    @field_validator("code")
    @classmethod
    def _validate_code(cls, value: str) -> str:
        cleaned = value.strip()
        if not _DIGITS_6_RE.match(cleaned):
            raise ValueError("Digite os 6 dígitos do código.")
        return cleaned


class VerifyEmailResponse(BaseModel):
    """Contrato de saída de `POST /auth/verify-email` (`200 OK`)"""

    status: UserStatus


class ResendVerificationRequest(BaseModel):
    """Contrato de entrada de `POST /auth/verify-email/resend` ([S1-08])"""

    model_config = ConfigDict(extra="ignore")

    email: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _validate_and_normalize_email(value)


class ResendVerificationResponse(BaseModel):
    """Contrato de saída de `POST /auth/verify-email/resend` (`202 Accepted`)"""

    status: str = "accepted"


class LoginRequest(BaseModel):
    """Contrato de entrada de `POST /auth/login` ([S1-09], RF03)"""

    model_config = ConfigDict(extra="ignore")

    email: str
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _validate_and_normalize_email(value)


class TokenPairResponse(BaseModel):
    """Contrato de saída de `POST /auth/login` e `POST /auth/refresh` (`200 OK`)"""

    access_token: str
    refresh_token: str
    expires_in: int


class RefreshRequest(BaseModel):
    """Contrato de entrada de `POST /auth/refresh` ([S1-09])"""

    model_config = ConfigDict(extra="ignore")

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """Contrato de entrada de `POST /auth/logout` ([S1-09], REQ 04)"""

    model_config = ConfigDict(extra="ignore")

    refresh_token: str = ""


class ForgotPasswordRequest(BaseModel):
    """Contrato de entrada de `POST /auth/password/forgot` ([S2-02], RF05)"""

    model_config = ConfigDict(extra="ignore")

    email: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _validate_and_normalize_email(value)


class ForgotPasswordResponse(BaseModel):
    """Contrato de saída de `POST /auth/password/forgot` (`202 Accepted`, exista a conta ou não)"""

    status: str = "accepted"


class ResetPasswordRequest(BaseModel):
    """Contrato de entrada de `POST /auth/password/reset` ([S2-02], RF05)"""

    # O 422 já não repete a entrada (veriditi_common.errors); o token fica fora do repr
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    token: str = Field(repr=False)
    # Sem min_length: a PasswordPolicy dá a mensagem em PT-BR também para a senha vazia
    new_password: str = Field(repr=False)


class OabRead(BaseModel):
    """Inscrição como foi informada no cadastro; sem consulta ao CNA ainda (#64)"""

    model_config = ConfigDict(from_attributes=True)

    number: str
    uf: OabUf
    kind: OabKind


class ProfileRead(BaseModel):
    """Contrato de saída de `GET /me` e `PATCH /me` ([S1-10], RF06; tipo, CPF e OAB na #60)"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    status: UserStatus
    email_verified_at: datetime | None
    created_at: datetime
    user_type: UserType
    cpf_masked: str
    oab: OabRead | None


class ProfileUpdate(BaseModel):
    """Contrato de entrada de `PATCH /me` ([S1-10], RF06)

    `extra="ignore"` descarta silenciosamente campos não editáveis como `email`, `status`,
    `user_type`, `cpf` e `oab`, prevenindo vulnerabilidades de *mass assignment*.
    """

    model_config = ConfigDict(extra="ignore")

    name: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Informe seu nome.")
        if len(cleaned) > 120:
            raise ValueError("O nome deve ter no máximo 120 caracteres.")
        return cleaned


class PasswordChange(BaseModel):
    """Contrato de entrada de `POST /me/password` ([S1-10], RF06)"""

    model_config = ConfigDict(extra="ignore")

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
    refresh_token: str | None = None
