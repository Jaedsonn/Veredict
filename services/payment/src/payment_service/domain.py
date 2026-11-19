"""Regras puras do pagamento: pacotes, pedidos, faturamento e carteira (sem banco nem HTTP)"""

import enum
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

# As 27 unidades da federação, aceitas no estado do faturamento
UFS: Final = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
)  # fmt: skip

_CPF_FORMAT: Final = re.compile(r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$")
_CEP_FORMAT: Final = re.compile(r"^\d{5}-?\d{3}$")
_PHONE_DIGITS: Final = re.compile(r"^\d{10,11}$")
_PHONE_ALLOWED: Final = re.compile(r"^[\d\s()+-]+$")


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"


class LedgerReason(enum.StrEnum):
    PURCHASE = "purchase"
    # Débito e estorno da captura entram na #24
    CAPTURE = "capture"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


@dataclass(frozen=True, slots=True)
class CreditPackage:
    """Pacote do Apêndice A: nome, créditos, valor por crédito e benefícios (D2)"""

    id: int
    code: str
    name: str
    credits: int
    unit_price_cents: int
    price_cents: int
    currency: str
    benefits: str
    highlight: bool


@dataclass(frozen=True, slots=True)
class Billing:
    """Dados da compra do Apêndice A; o CPF completo só existe em memória"""

    name: str
    email: str
    phone: str
    cpf: str = field(repr=False)
    cep: str
    street: str
    number: str
    complement: str | None
    district: str
    city: str
    state: str

    @property
    def cpf_masked(self) -> str:
        return mask_cpf(self.cpf)


@dataclass(frozen=True, slots=True)
class BillingSnapshot:
    """O que fica gravado no pedido: o CPF só mascarado (ADR-013, ADR-024)"""

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

    @classmethod
    def of(cls, billing: Billing) -> "BillingSnapshot":
        return cls(
            name=billing.name,
            email=billing.email,
            phone=billing.phone,
            cpf_masked=billing.cpf_masked,
            cep=billing.cep,
            street=billing.street,
            number=billing.number,
            complement=billing.complement,
            district=billing.district,
            city=billing.city,
            state=billing.state,
        )


@dataclass(frozen=True, slots=True)
class Order:
    id: uuid.UUID
    user_id: int
    package_id: int
    package_code: str
    package_name: str
    credits: int
    amount_cents: int
    status: OrderStatus
    provider: str
    provider_payment_id: str | None
    pix_copy_paste: str | None
    idempotency_key: str
    billing: BillingSnapshot
    expires_at: datetime
    paid_at: datetime | None
    created_at: datetime

    def is_overdue(self, now: datetime) -> bool:
        return self.status is OrderStatus.PENDING and now >= self.expires_at


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    id: int
    delta: int
    reason: LedgerReason
    reference_id: str
    balance_after: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PixCharge:
    """Resposta do provedor: só o necessário para exibir e conciliar o PIX"""

    provider_payment_id: str
    copy_paste: str


@dataclass(frozen=True, slots=True)
class PixChargeRequest:
    order_id: uuid.UUID
    amount_cents: int
    description: str
    payer: Billing


# Erros de domínio: o main.py traduz cada um para HTTP


class PaymentError(Exception):
    code: str = "payment_error"
    message: str = "Não foi possível concluir o pagamento."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class PackageNotFoundError(PaymentError):
    code = "package_not_found"
    message = "Pacote de créditos não encontrado."


class OrderNotFoundError(PaymentError):
    code = "order_not_found"
    message = "Pedido não encontrado."


class IdempotencyKeyReusedError(PaymentError):
    code = "idempotency_key_reused"
    message = "Esta chave de idempotência já foi usada em outro pedido."


class OrderNotPayableError(PaymentError):
    code = "order_not_payable"
    message = "Este pedido não aceita mais pagamento."


class ProviderUnavailableError(PaymentError):
    code = "payment_provider_unavailable"
    message = "Serviço de pagamento indisponível. Tente novamente em instantes."


class ProviderError(Exception):
    """Falha do adapter do provedor; o caso de uso marca o pedido como failed"""


# Validações do faturamento, as mesmas da web (apps/web/src/lib/validation/billing.ts)


def _check_digit(digits: str) -> int:
    total = sum(int(d) * (len(digits) + 1 - i) for i, d in enumerate(digits))
    return (total * 10) % 11 % 10


def cpf_digits(raw: str) -> str | None:
    """Os 11 dígitos de um CPF válido, ou None se o formato ou os verificadores falharem"""
    cleaned = raw.strip()
    if not _CPF_FORMAT.fullmatch(cleaned):
        return None
    digits = re.sub(r"[.-]", "", cleaned)
    if len(set(digits)) == 1:
        return None
    first = _check_digit(digits[:9])
    second = _check_digit(digits[:9] + str(first))
    return digits if digits[9:] == f"{first}{second}" else None


def mask_cpf(digits: str) -> str:
    """`***.982.247-**`, o mesmo formato do cpf_masked do auth"""
    return f"***.{digits[3:6]}.{digits[6:9]}-**"


def cep_digits(raw: str) -> str | None:
    cleaned = raw.strip()
    return cleaned.replace("-", "") if _CEP_FORMAT.fullmatch(cleaned) else None


def phone_digits(raw: str) -> str | None:
    """DDD + número, fixo (10) ou celular (11), aceitando máscara e +55"""
    cleaned = raw.strip()
    if not cleaned or not _PHONE_ALLOWED.fullmatch(cleaned):
        return None
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    if not _PHONE_DIGITS.fullmatch(digits) or digits[0] == "0":
        return None
    return digits
