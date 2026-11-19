"""Composition root: liga as portas aos adapters; os testes trocam via create_app/app.state"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.adapters.sqlalchemy_repo import SqlAlchemyUnitOfWork
from payment_service.config import Settings
from payment_service.ports import Clock, PaymentProvider, QrRenderer, UnitOfWork
from payment_service.use_cases.catalog import GetBalance, GetStatement, ListPackages
from payment_service.use_cases.orders import Actor, ConfirmPayment, CreateOrder, GetOrder
from veriditi_common.audit import AuditLoggerDep
from veriditi_common.middleware import client_ip
from veriditi_common.security import CurrentUserDep


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """O Database vive em app.state (criado no lifespan) para os testes poderem trocá-lo"""
    async for session in request.app.state.db.session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_provider(request: Request) -> PaymentProvider:
    provider: PaymentProvider = request.app.state.payment_provider
    return provider


def get_qr_renderer(request: Request) -> QrRenderer:
    renderer: QrRenderer = request.app.state.qr_renderer
    return renderer


def get_uow(session: SessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def get_actor(request: Request, user: CurrentUserDep) -> Actor:
    return Actor(user_id=user.id, ip=client_ip(request))


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ClockDep = Annotated[Clock, Depends(get_clock)]
ProviderDep = Annotated[PaymentProvider, Depends(get_provider)]
QrRendererDep = Annotated[QrRenderer, Depends(get_qr_renderer)]
UowDep = Annotated[UnitOfWork, Depends(get_uow)]
ActorDep = Annotated[Actor, Depends(get_actor)]


def get_list_packages(uow: UowDep) -> ListPackages:
    return ListPackages(uow.packages)


def get_balance(uow: UowDep) -> GetBalance:
    return GetBalance(uow.wallets)


def get_statement(uow: UowDep) -> GetStatement:
    return GetStatement(uow.wallets)


def get_create_order(
    uow: UowDep,
    provider: ProviderDep,
    audit: AuditLoggerDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> CreateOrder:
    return CreateOrder(uow, provider, audit, clock, ttl_minutes=settings.order_ttl_minutes)


def get_get_order(uow: UowDep, audit: AuditLoggerDep, clock: ClockDep) -> GetOrder:
    return GetOrder(uow, audit, clock)


def get_confirm_payment(uow: UowDep, audit: AuditLoggerDep, clock: ClockDep) -> ConfirmPayment:
    return ConfirmPayment(uow, audit, clock)


ListPackagesDep = Annotated[ListPackages, Depends(get_list_packages)]
GetBalanceDep = Annotated[GetBalance, Depends(get_balance)]
GetStatementDep = Annotated[GetStatement, Depends(get_statement)]
CreateOrderDep = Annotated[CreateOrder, Depends(get_create_order)]
GetOrderDep = Annotated[GetOrder, Depends(get_get_order)]
ConfirmPaymentDep = Annotated[ConfirmPayment, Depends(get_confirm_payment)]
