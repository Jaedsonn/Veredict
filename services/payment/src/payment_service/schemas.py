"""Contratos HTTP do payment; mensagens em PT-BR por campo (a web as mostra no formulário)"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from pydantic_core import PydanticCustomError

from payment_service.domain import (
    UFS,
    Billing,
    CreditPackage,
    LedgerEntry,
    LedgerReason,
    Order,
    OrderStatus,
    cep_digits,
    cpf_digits,
    phone_digits,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True)]
_EMAIL = TypeAdapter(EmailStr)


def _invalid(message: str) -> PydanticCustomError:
    """Sem o prefixo "Value error, " do ValueError: a web mostra a mensagem como está"""
    return PydanticCustomError("invalid", message)


def _required(value: str, message: str, max_length: int) -> str:
    if not value:
        raise _invalid(message)
    if len(value) > max_length:
        raise _invalid(f"Use no máximo {max_length} caracteres.")
    return value


class BillingIn(BaseModel):
    """Dados da compra do Apêndice A"""

    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    name: Text
    email: Text
    phone: Text
    cpf: Text = Field(repr=False)
    cep: Text
    street: Text
    number: Text
    complement: Text | None = None
    district: Text
    city: Text
    state: Text

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _required(value, "Informe o nome completo.", 120)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        cleaned = value.lower()
        try:
            _EMAIL.validate_python(cleaned)
        except ValidationError:
            raise _invalid("Informe um e-mail válido.") from None
        if len(cleaned) > 255:
            raise _invalid("Use no máximo 255 caracteres.")
        return cleaned

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        digits = phone_digits(value)
        if digits is None:
            raise _invalid("Informe o telefone com DDD.")
        return digits

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, value: str) -> str:
        digits = cpf_digits(value)
        if digits is None:
            raise _invalid("CPF inválido.")
        return digits

    @field_validator("cep")
    @classmethod
    def _cep(cls, value: str) -> str:
        digits = cep_digits(value)
        if digits is None:
            raise _invalid("Informe o CEP com 8 dígitos.")
        return digits

    @field_validator("street")
    @classmethod
    def _street(cls, value: str) -> str:
        return _required(value, "Informe o endereço.", 120)

    @field_validator("number")
    @classmethod
    def _number(cls, value: str) -> str:
        return _required(value, "Informe o número (ou S/N).", 10)

    @field_validator("complement")
    @classmethod
    def _complement(cls, value: str | None) -> str | None:
        if not value:
            return None
        return _required(value, "", 60)

    @field_validator("district")
    @classmethod
    def _district(cls, value: str) -> str:
        return _required(value, "Informe o bairro.", 60)

    @field_validator("city")
    @classmethod
    def _city(cls, value: str) -> str:
        return _required(value, "Informe a cidade.", 60)

    @field_validator("state")
    @classmethod
    def _state(cls, value: str) -> str:
        uf = value.upper()
        if uf not in UFS:
            raise _invalid("Escolha o estado.")
        return uf

    def to_domain(self) -> Billing:
        return Billing(
            name=self.name,
            email=self.email,
            phone=self.phone,
            cpf=self.cpf,
            cep=self.cep,
            street=self.street,
            number=self.number,
            complement=self.complement,
            district=self.district,
            city=self.city,
            state=self.state,
        )


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    package_code: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    billing: BillingIn


class PackageOut(BaseModel):
    code: str
    name: str
    credits: int
    unit_price_cents: int
    price_cents: int
    currency: str
    benefits: str
    highlight: bool

    @classmethod
    def of(cls, package: CreditPackage) -> "PackageOut":
        return cls(
            code=package.code,
            name=package.name,
            credits=package.credits,
            unit_price_cents=package.unit_price_cents,
            price_cents=package.price_cents,
            currency=package.currency,
            benefits=package.benefits,
            highlight=package.highlight,
        )


class BillingOut(BaseModel):
    name: str
    email: str
    phone: str
    cpf_masked: str
    cep: str
    street: str
    number: str
    complement: str | None
    district: str
    city: str
    state: str


class OrderPackageOut(BaseModel):
    code: str
    name: str


class OrderOut(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    package: OrderPackageOut
    credits: int
    amount_cents: int
    currency: str = "BRL"
    provider: str
    pix_copy_paste: str | None
    # SVG do QR Code; só enquanto o pedido espera pagamento
    pix_qr_svg: str | None
    billing: BillingOut
    expires_at: datetime
    paid_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, order: Order, qr_svg: str | None) -> "OrderOut":
        b = order.billing
        return cls(
            id=order.id,
            status=order.status,
            package=OrderPackageOut(code=order.package_code, name=order.package_name),
            credits=order.credits,
            amount_cents=order.amount_cents,
            provider=order.provider,
            pix_copy_paste=order.pix_copy_paste,
            pix_qr_svg=qr_svg,
            billing=BillingOut(
                name=b.name,
                email=b.email,
                phone=b.phone,
                cpf_masked=b.cpf_masked,
                cep=b.cep,
                street=b.street,
                number=b.number,
                complement=b.complement,
                district=b.district,
                city=b.city,
                state=b.state,
            ),
            expires_at=order.expires_at,
            paid_at=order.paid_at,
            created_at=order.created_at,
        )


class ConfirmationOut(BaseModel):
    order: OrderOut
    balance: int


class BalanceOut(BaseModel):
    balance: int


class LedgerEntryOut(BaseModel):
    id: int
    delta: int
    reason: LedgerReason
    reference_id: str
    balance_after: int
    created_at: datetime

    @classmethod
    def of(cls, entry: LedgerEntry) -> "LedgerEntryOut":
        return cls(
            id=entry.id,
            delta=entry.delta,
            reason=entry.reason,
            reference_id=entry.reference_id,
            balance_after=entry.balance_after,
            created_at=entry.created_at,
        )


class StatementOut(BaseModel):
    balance: int
    entries: list[LedgerEntryOut]
