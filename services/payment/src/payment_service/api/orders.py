"""Pedidos de compra de créditos (REQ05, RF08): faturamento, PIX e confirmação"""

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Header, Response, status

from payment_service.dependencies import (
    ActorDep,
    ConfirmPaymentDep,
    CreateOrderDep,
    GetOrderDep,
    QrRendererDep,
    SettingsDep,
)
from payment_service.domain import Order, OrderNotFoundError, OrderStatus
from payment_service.ports import QrRenderer
from payment_service.schemas import ConfirmationOut, OrderCreate, OrderOut
from veriditi_common.errors import AppError

router = APIRouter(prefix="/orders", tags=["orders"])

# Gerada pela web a cada envio do formulário (#25): só ASCII visível, sem espaço
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
]
_SANDBOX_SOURCE: Final = "sandbox"


def _out(order: Order, qr: QrRenderer) -> OrderOut:
    # O QR só faz sentido enquanto o pedido espera pagamento
    svg = (
        qr.svg(order.pix_copy_paste)
        if order.status is OrderStatus.PENDING and order.pix_copy_paste
        else None
    )
    return OrderOut.of(order, svg)


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    response: Response,
    actor: ActorDep,
    use_case: CreateOrderDep,
    qr: QrRendererDep,
    idempotency_key: IdempotencyKey,
) -> OrderOut:
    order, created = await use_case.execute(
        actor,
        package_code=payload.package_code,
        billing=payload.billing.to_domain(),
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return _out(order, qr)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID, actor: ActorDep, use_case: GetOrderDep, qr: QrRendererDep
) -> OrderOut:
    return _out(await use_case.execute(actor, order_id), qr)


@router.post("/{order_id}/simulate-payment", response_model=ConfirmationOut)
async def simulate_payment(
    order_id: uuid.UUID,
    actor: ActorDep,
    use_case: ConfirmPaymentDep,
    qr: QrRendererDep,
    settings: SettingsDep,
) -> ConfirmationOut:
    """Só no sandbox: faz o papel do provedor avisando que o PIX foi pago"""
    if not settings.sandbox:
        raise AppError(404, OrderNotFoundError.code, OrderNotFoundError.message)
    confirmation = await use_case.execute(actor, order_id, source=_SANDBOX_SOURCE)
    return ConfirmationOut(order=_out(confirmation.order, qr), balance=confirmation.balance)
