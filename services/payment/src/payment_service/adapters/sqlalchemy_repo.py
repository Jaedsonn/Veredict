"""Repositórios SQLAlchemy do payment, todos na mesma sessão (UnitOfWork)"""

import uuid
from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, Row, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.domain import (
    BillingSnapshot,
    CreditPackage,
    LedgerEntry,
    LedgerReason,
    Order,
    OrderStatus,
    PixCharge,
)
from payment_service.models import (
    LEDGER_REFERENCE_UNIQUE,
    ORDER_IDEMPOTENCY_UNIQUE,
    CreditLedgerRecord,
    CreditPackageRecord,
    CreditWalletRecord,
    OrderRecord,
)
from payment_service.ports import (
    DuplicateLedgerEntryError,
    DuplicateOrderError,
    OrderRepository,
    PackageRepository,
    WalletRepository,
)
from veriditi_common.db_types import utcnow

MYSQL_DUPLICATE_ENTRY: Final = 1062


def _is_duplicate(exc: IntegrityError, constraint: str, sqlite_marker: str) -> bool:
    """Só a UNIQUE esperada é repetição; outra violação é bug e sobe"""
    args: tuple[object, ...] = getattr(exc.orig, "args", ())
    if len(args) >= 2 and args[0] == MYSQL_DUPLICATE_ENTRY:
        return constraint in str(args[1])
    return sqlite_marker in str(exc.orig)


def _package(record: CreditPackageRecord) -> CreditPackage:
    return CreditPackage(
        id=record.id,
        code=record.code,
        name=record.name,
        credits=record.credits,
        unit_price_cents=record.unit_price_cents,
        price_cents=record.price_cents,
        currency=record.currency,
        benefits=record.benefits,
        highlight=record.highlight,
    )


def _order(record: OrderRecord, package_code: str, package_name: str) -> Order:
    return Order(
        id=record.id,
        user_id=record.user_id,
        package_id=record.package_id,
        package_code=package_code,
        package_name=package_name,
        credits=record.credits,
        amount_cents=record.amount_cents,
        status=record.status,
        provider=record.provider,
        provider_payment_id=record.provider_payment_id,
        pix_copy_paste=record.pix_copy_paste,
        idempotency_key=record.idempotency_key,
        billing=BillingSnapshot(
            name=record.billing_name,
            email=record.billing_email,
            phone=record.billing_phone,
            cpf_masked=record.billing_cpf_masked,
            cep=record.billing_cep,
            street=record.billing_street,
            number=record.billing_number,
            complement=record.billing_complement,
            district=record.billing_district,
            city=record.billing_city,
            state=record.billing_state,
        ),
        expires_at=record.expires_at,
        paid_at=record.paid_at,
        created_at=record.created_at,
    )


def _entry(record: CreditLedgerRecord) -> LedgerEntry:
    return LedgerEntry(
        id=record.id,
        delta=record.delta,
        reason=record.reason,
        reference_id=record.reference_id,
        balance_after=record.balance_after,
        created_at=record.created_at,
    )


class SqlAlchemyPackageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[CreditPackage]:
        stmt = (
            select(CreditPackageRecord)
            .where(CreditPackageRecord.active.is_(True))
            .order_by(CreditPackageRecord.price_cents, CreditPackageRecord.id)
        )
        return [_package(r) for r in (await self._session.scalars(stmt)).all()]

    async def get_active_by_code(self, code: str) -> CreditPackage | None:
        stmt = select(CreditPackageRecord).where(
            CreditPackageRecord.code == code, CreditPackageRecord.active.is_(True)
        )
        record = (await self._session.scalars(stmt)).one_or_none()
        return _package(record) if record else None


class SqlAlchemyOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _select(self) -> Any:
        return select(OrderRecord, CreditPackageRecord.code, CreditPackageRecord.name).join(
            CreditPackageRecord, CreditPackageRecord.id == OrderRecord.package_id
        )

    @staticmethod
    def _from_row(row: Row[OrderRecord, str, str] | None) -> Order | None:
        if row is None:
            return None
        record, code, name = row
        return _order(record, code, name)

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
        record = OrderRecord(
            id=order_id,
            user_id=user_id,
            package_id=package.id,
            credits=package.credits,
            amount_cents=package.price_cents,
            status=OrderStatus.PENDING,
            provider=provider,
            idempotency_key=idempotency_key,
            billing_name=billing.name,
            billing_email=billing.email,
            billing_phone=billing.phone,
            billing_cpf_masked=billing.cpf_masked,
            billing_cep=billing.cep,
            billing_street=billing.street,
            billing_number=billing.number,
            billing_complement=billing.complement,
            billing_district=billing.district,
            billing_city=billing.city,
            billing_state=billing.state,
            expires_at=expires_at,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_duplicate(
                exc, ORDER_IDEMPOTENCY_UNIQUE, "UNIQUE constraint failed: orders.user_id"
            ):
                raise DuplicateOrderError from exc
            raise
        return _order(record, package.code, package.name)

    async def get(self, order_id: uuid.UUID) -> Order | None:
        stmt = self._select().where(OrderRecord.id == order_id)
        return self._from_row((await self._session.execute(stmt)).one_or_none())

    async def get_by_idempotency_key(self, user_id: int, key: str) -> Order | None:
        stmt = self._select().where(
            OrderRecord.user_id == user_id, OrderRecord.idempotency_key == key
        )
        return self._from_row((await self._session.execute(stmt)).one_or_none())

    async def attach_charge(self, order_id: uuid.UUID, charge: PixCharge) -> None:
        await self._session.execute(
            update(OrderRecord)
            .where(OrderRecord.id == order_id)
            .values(
                provider_payment_id=charge.provider_payment_id,
                pix_copy_paste=charge.copy_paste,
                updated_at=utcnow(),
            )
        )

    async def transition(
        self,
        order_id: uuid.UUID,
        *,
        from_status: OrderStatus,
        to_status: OrderStatus,
        paid_at: datetime | None = None,
    ) -> bool:
        values: dict[str, Any] = {"status": to_status, "updated_at": utcnow()}
        if paid_at is not None:
            values["paid_at"] = paid_at
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(OrderRecord)
                .where(OrderRecord.id == order_id, OrderRecord.status == from_status)
                .values(**values)
            ),
        )
        return result.rowcount == 1


class SqlAlchemyWalletRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure(self, user_id: int) -> None:
        """Transação própria: a carteira existe antes da confirmação travar o pedido"""
        exists = await self._session.scalar(
            select(CreditWalletRecord.user_id).where(CreditWalletRecord.user_id == user_id)
        )
        if exists is not None:
            return
        self._session.add(CreditWalletRecord(user_id=user_id, balance=0))
        try:
            await self._session.commit()
        except IntegrityError:
            # Outra confirmação criou a mesma carteira ao mesmo tempo
            await self._session.rollback()

    async def balance(self, user_id: int) -> int:
        value = await self._session.scalar(
            select(CreditWalletRecord.balance).where(CreditWalletRecord.user_id == user_id)
        )
        return int(value or 0)

    async def credit(
        self, user_id: int, amount: int, *, reason: LedgerReason, reference_id: str
    ) -> LedgerEntry:
        # UPDATE relativo: o InnoDB trava a linha até o commit, sem ler e regravar o saldo
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(CreditWalletRecord)
                .where(CreditWalletRecord.user_id == user_id)
                .values(balance=CreditWalletRecord.balance + amount, updated_at=utcnow())
            ),
        )
        if result.rowcount != 1:
            raise RuntimeError("Carteira inexistente: chame ensure antes de creditar")
        balance = await self._session.scalar(
            select(CreditWalletRecord.balance).where(CreditWalletRecord.user_id == user_id)
        )
        record = CreditLedgerRecord(
            user_id=user_id,
            delta=amount,
            reason=reason,
            reference_id=reference_id,
            balance_after=int(balance or 0),
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_duplicate(
                exc, LEDGER_REFERENCE_UNIQUE, "UNIQUE constraint failed: credit_ledger.reason"
            ):
                raise DuplicateLedgerEntryError from exc
            raise
        return _entry(record)

    async def statement(self, user_id: int, *, limit: int) -> list[LedgerEntry]:
        stmt = (
            select(CreditLedgerRecord)
            .where(CreditLedgerRecord.user_id == user_id)
            .order_by(CreditLedgerRecord.id.desc())
            .limit(limit)
        )
        return [_entry(r) for r in (await self._session.scalars(stmt)).all()]


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.packages: PackageRepository = SqlAlchemyPackageRepository(session)
        self.orders: OrderRepository = SqlAlchemyOrderRepository(session)
        self.wallets: WalletRepository = SqlAlchemyWalletRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
