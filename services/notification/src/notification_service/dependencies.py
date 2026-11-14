from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from notification_service.ports import DeliveryTask
from notification_service.use_cases.send_notification import SendNotification
from veriditi_common.middleware import defer


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """O Database vive em app.state (criado no lifespan) para os testes poderem trocá-lo"""
    async for session in request.app.state.db.session():
        yield session


class DeferredScheduler:
    """Fila do RequestContextMiddleware: roda depois da resposta e mantém o request_id"""

    def __init__(self, request: Request) -> None:
        self._request = request

    def schedule(self, task: DeliveryTask) -> None:
        defer(self._request, task)


def get_send_notification(request: Request) -> SendNotification:
    """Composition root: o audit_logger vai direto, porque a tarefa já roda depois da resposta"""
    state = request.app.state
    return SendNotification(
        registry=state.registry,
        renderer=state.renderer,
        notifications=state.notifications,
        sender=state.email_sender,
        audit=state.audit_logger,
        scheduler=DeferredScheduler(request),
        message_ids=state.message_ids,
        clock=state.clock,
        sleep=state.sleep,
    )


SendNotificationDep = Annotated[SendNotification, Depends(get_send_notification)]
