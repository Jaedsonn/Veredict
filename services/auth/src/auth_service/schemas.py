"""Schemas Pydantic (contratos de entrada e saída HTTP) do serviço de Autenticação."""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from auth_service.models import UserStatus

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


class RegisterRequest(BaseModel):
    """Contrato de entrada de `POST /auth/register` ([S1-07], RF01)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    email: str
    password: str

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
    """Contrato de saída de `POST /auth/register` (`201 Created`)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    status: UserStatus


class VerifyEmailRequest(BaseModel):
    """Contrato de entrada de `POST /auth/verify-email` ([S1-08], RF02)."""

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
    """Contrato de saída de `POST /auth/verify-email` (`200 OK`)."""

    status: UserStatus


class ResendVerificationRequest(BaseModel):
    """Contrato de entrada de `POST /auth/verify-email/resend` ([S1-08])."""

    model_config = ConfigDict(extra="ignore")

    email: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _validate_and_normalize_email(value)


class ResendVerificationResponse(BaseModel):
    """Contrato de saída de `POST /auth/verify-email/resend` (`202 Accepted`)."""

    status: str = "accepted"


class LoginRequest(BaseModel):
    """Contrato de entrada de `POST /auth/login` ([S1-09], RF03)."""

    model_config = ConfigDict(extra="ignore")

    email: str
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _validate_and_normalize_email(value)


class TokenPairResponse(BaseModel):
    """Contrato de saída de `POST /auth/login` e `POST /auth/refresh` (`200 OK`)."""

    access_token: str
    refresh_token: str
    expires_in: int


class RefreshRequest(BaseModel):
    """Contrato de entrada de `POST /auth/refresh` ([S1-09])."""

    model_config = ConfigDict(extra="ignore")

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """Contrato de entrada de `POST /auth/logout` ([S1-09], REQ 04)."""

    model_config = ConfigDict(extra="ignore")

    refresh_token: str = ""


class ProfileRead(BaseModel):
    """Contrato de saída de `GET /me` e `PATCH /me` ([S1-10], RF06)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    status: UserStatus
    email_verified_at: datetime | None
    created_at: datetime


class ProfileUpdate(BaseModel):
    """Contrato de entrada de `PATCH /me` ([S1-10], RF06).

    `extra="ignore"` descarta silenciosamente campos não editáveis como `email` ou `status`,
    prevenindo vulnerabilidades de *mass assignment*.
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
    """Contrato de entrada de `POST /me/password` ([S1-10], RF06)."""

    model_config = ConfigDict(extra="ignore")

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
    refresh_token: str | None = None
