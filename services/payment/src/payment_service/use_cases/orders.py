"""Compra de créditos (REQ05): pedido com faturamento, cobrança PIX e confirmação"""

import ipaddress
import uuid
from dataclasses import dataclass
from datetime import timedelta

from payment_service.domain import (
    Billing,
    BillingSnapshot,
    IdempotencyKeyReusedError,
    LedgerReason,
    Order,
    OrderNotFoundError,
    OrderNotPayableError,
    OrderStatus,
    PackageNotFoundError,
    PixChargeRequest,
    ProviderError,
    ProviderUnavailableError,
)
from payment_service.ports import (
    Clock,
    DuplicateLedgerEntryError,
    DuplicateOrderError,
    PaymentProvider,
    UnitOfWork,
)
from veriditi_common.audit import AuditEvent, AuditLogger, AuditOutcome
from veriditi_common.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: int
    ip: str | None


async def _audit(
    audit: AuditLogger,
    actor: Actor,
    action: str,
    *,
    resource_type: str,
    resource_id: str,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    metadata: dict[str, str | int] | None = None,
) -> None:
    await audit.record(
        AuditEvent(
            service="payment",
            action=action,
            outcome=outcome,
            actor_id=actor.user_id,
            actor_ip=ipaddress.ip_address(actor.ip) if actor.ip else None,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=dict(metadata or {}),
        )
    )


def _order_metadata(order: Order) -> dict[str, str | int]:
    return {
        "package": order.package_code,
        "credits": order.credits,
        "amount_cents": order.amount_cents,
        "provider": order.provider,
    }


async def _load_owned(uow: UnitOfWork, actor: Actor, order_id: uuid.UUID) -> Order:
    """Pedido de outra pessoa é 404, sem revelar que existe (IDOR)"""
    order = await uow.orders.get(order_id)
    if order is None or order.user_id != actor.user_id:
        raise OrderNotFoundError()
    return order


async def _expire_if_overdue(
    uow: UnitOfWork, audit: AuditLogger, clock: Clock, actor: Actor, order: Order
) -> Order:
    """Expiração preguiçosa: quem lê o pedido vencido o marca, sem job"""
    if not order.is_overdue(clock()):
        return order
    if await uow.orders.transition(
        order.id, from_status=OrderStatus.PENDING, to_status=OrderStatus.EXPIRED
    ):
        await uow.commit()
        await _audit(
            audit,
            actor,
            "payment.order.expired",
            resource_type="order",
            resource_id=str(order.id),
            metadata=_order_metadata(order),
        )
    else:
        await uow.rollback()
    return await _load_owned(uow, actor, order.id)


class CreateOrder:
    def __init__(
        self,
        uow: UnitOfWork,
        provider: PaymentProvider,
        audit: AuditLogger,
        clock: Clock,
        *,
        ttl_minutes: int,
    ) -> None:
        self._uow = uow
        self._provider = provider
        self._audit = audit
        self._clock = clock
        self._ttl = timedelta(minutes=ttl_minutes)

    async def _replay(self, actor: Actor, key: str, package_code: str) -> Order | None:
        existing = await self._uow.orders.get_by_idempotency_key(actor.user_id, key)
        if existing is None:
            return None
        if existing.package_code != package_code:
            raise IdempotencyKeyReusedError()
        return existing

    async def execute(
        self, actor: Actor, *, package_code: str, billing: Billing, idempotency_key: str
    ) -> tuple[Order, bool]:
        """(pedido, criado agora); repetir a chave devolve o mesmo pedido sem nova cobrança"""
        if replay := await self._replay(actor, idempotency_key, package_code):
            return replay, False

        package = await self._uow.packages.get_active_by_code(package_code)
        if package is None:
            raise PackageNotFoundError()

        order_id = uuid.uuid4()
        try:
            order = await self._uow.orders.add(
                order_id=order_id,
                user_id=actor.user_id,
                package=package,
                provider=self._provider.name,
                idempotency_key=idempotency_key,
                billing=BillingSnapshot.of(billing),
                expires_at=self._clock() + self._ttl,
            )
        except DuplicateOrderError:
            # Clique duplo: a outra requisição gravou a mesma chave primeiro
            replay = await self._replay(actor, idempotency_key, package_code)
            if replay is None:
                raise
            return replay, False
        await self._uow.commit()

        try:
            charge = await self._provider.create_pix_charge(
                PixChargeRequest(
                    order_id=order.id,
                    amount_cents=order.amount_cents,
                    description=f"Veriditi – pacote {package.name} ({package.credits} créditos)",
                    payer=billing,
                )
            )
        except ProviderError as exc:
            log.error("payment_provider_failed", order_id=str(order.id), error=str(exc))
            await self._uow.orders.transition(
                order.id, from_status=OrderStatus.PENDING, to_status=OrderStatus.FAILED
            )
            await self._uow.commit()
            await _audit(
                self._audit,
                actor,
                "payment.order.failed",
                outcome=AuditOutcome.FAILURE,
                resource_type="order",
                resource_id=str(order.id),
                metadata={**_order_metadata(order), "reason": "provider_unavailable"},
            )
            raise ProviderUnavailableError() from exc

        await self._uow.orders.attach_charge(order.id, charge)
        await self._uow.commit()
        await _audit(
            self._audit,
            actor,
            "payment.order.created",
            resource_type="order",
            resource_id=str(order.id),
            metadata=_order_metadata(order),
        )
        return await _load_owned(self._uow, actor, order.id), True


class GetOrder:
    def __init__(self, uow: UnitOfWork, audit: AuditLogger, clock: Clock) -> None:
        self._uow = uow
        self._audit = audit
        self._clock = clock

    async def execute(self, actor: Actor, order_id: uuid.UUID) -> Order:
        order = await _load_owned(self._uow, actor, order_id)
        return await _expire_if_overdue(self._uow, self._audit, self._clock, actor, order)


@dataclass(frozen=True, slots=True)
class Confirmation:
    order: Order
    balance: int
    credited_now: bool


class ConfirmPayment:
    """Pedido pago e créditos lançados na mesma transação, uma vez só (#73)"""

    def __init__(self, uow: UnitOfWork, audit: AuditLogger, clock: Clock) -> None:
        self._uow = uow
        self._audit = audit
        self._clock = clock

    async def _already_paid(self, actor: Actor, order_id: uuid.UUID) -> Confirmation:
        order = await _load_owned(self._uow, actor, order_id)
        if order.status is not OrderStatus.PAID:
            raise OrderNotPayableError()
        balance = await self._uow.wallets.balance(actor.user_id)
        return Confirmation(order=order, balance=balance, credited_now=False)

    async def execute(self, actor: Actor, order_id: uuid.UUID, *, source: str) -> Confirmation:
        order = await _load_owned(self._uow, actor, order_id)
        if order.status is OrderStatus.PAID:
            return await self._already_paid(actor, order_id)
        order = await _expire_if_overdue(self._uow, self._audit, self._clock, actor, order)
        if order.status is not OrderStatus.PENDING:
            raise OrderNotPayableError()

        await self._uow.wallets.ensure(actor.user_id)
        paid = await self._uow.orders.transition(
            order.id,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.PAID,
            paid_at=self._clock(),
        )
        if not paid:
            # Outra confirmação chegou antes e já creditou
            await self._uow.rollback()
            return await self._already_paid(actor, order_id)
        try:
            entry = await self._uow.wallets.credit(
                actor.user_id,
                order.credits,
                reason=LedgerReason.PURCHASE,
                reference_id=str(order.id),
            )
        except DuplicateLedgerEntryError:
            return await self._already_paid(actor, order_id)
        await self._uow.commit()

        await _audit(
            self._audit,
            actor,
            "payment.order.paid",
            resource_type="order",
            resource_id=str(order.id),
            metadata={**_order_metadata(order), "source": source},
        )
        await _audit(
            self._audit,
            actor,
            "payment.credits.credited",
            resource_type="wallet",
            resource_id=str(actor.user_id),
            metadata={
                "delta": entry.delta,
                "balance_after": entry.balance_after,
                "reason": entry.reason.value,
                "order_id": str(order.id),
            },
        )
        return Confirmation(
            order=await _load_owned(self._uow, actor, order.id),
            balance=entry.balance_after,
            credited_now=True,
        )
