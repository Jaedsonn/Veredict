"""Portas do pagamento: os casos de uso só conhecem estas interfaces (DIP)"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from payment_service.domain import (
    BillingSnapshot,
    CreditPackage,
    LedgerEntry,
    LedgerReason,
    Order,
    OrderStatus,
    PixCharge,
    PixChargeRequest,
)

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


class PackageRepository(Protocol):
    async def list_active(self) -> list[CreditPackage]:
        """Ordenados por preço"""
        ...

    async def get_active_by_code(self, code: str) -> CreditPackage | None: ...


class OrderRepository(Protocol):
    async def add(
        self,
        *,
        order_id: uuid.UUID,
        user_id: int,
        package: CreditPackage,
        provider: str,
        idempotency_key: str,
        billing: BillingSnapshot,
        expires_at: datetime,
    ) -> Order:
        """Levanta DuplicateOrderError se (user_id, idempotency_key) já existir"""
        ...

    async def get(self, order_id: uuid.UUID) -> Order | None: ...

    async def get_by_idempotency_key(self, user_id: int, key: str) -> Order | None: ...

    async def attach_charge(self, order_id: uuid.UUID, charge: PixCharge) -> None: ...

    async def transition(
        self,
        order_id: uuid.UUID,
        *,
        from_status: OrderStatus,
        to_status: OrderStatus,
        paid_at: datetime | None = None,
    ) -> bool:
        """UPDATE condicional; False quando o pedido já não estava em from_status"""
        ...


class WalletRepository(Protocol):
    async def ensure(self, user_id: int) -> None:
        """Cria a carteira zerada se não existir (fora da transação da compra)"""
        ...

    async def balance(self, user_id: int) -> int:
        """Zero para quem não tem carteira"""
        ...

    async def credit(
        self, user_id: int, amount: int, *, reason: LedgerReason, reference_id: str
    ) -> LedgerEntry:
        """Soma no saldo e grava o movimento; DuplicateLedgerEntryError se a referência repetir"""
        ...

    async def statement(self, user_id: int, *, limit: int) -> list[LedgerEntry]:
        """Do mais recente para o mais antigo"""
        ...


class UnitOfWork(Protocol):
    """Pedidos, carteira e catálogo na mesma sessão: a confirmação é uma transação só"""

    packages: PackageRepository
    orders: OrderRepository
    wallets: WalletRepository

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class PaymentProvider(Protocol):
    """Provedor de PIX (ADR-013); o sandbox e o real são trocados só na composição"""

    name: str

    async def create_pix_charge(self, request: PixChargeRequest) -> PixCharge:
        """Levanta ProviderError quando o provedor falha"""
        ...


class QrRenderer(Protocol):
    def svg(self, payload: str) -> str: ...


class DuplicateOrderError(Exception):
    """Mesma chave de idempotência gravada por uma requisição concorrente"""


class DuplicateLedgerEntryError(Exception):
    """Movimento repetido (UNIQUE reason + reference_id): o crédito já foi lançado"""
