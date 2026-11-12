import asyncio
import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

from notification_service.domain import EmailDeliveryError, OutgoingEmail
from notification_service.ports import (
    Clock,
    EmailRenderer,
    EmailSender,
    MessageIdFactory,
    NotificationRepository,
    Scheduler,
    Sleep,
)
from notification_service.registry import TemplateRegistry
from veriditi_common.audit import AuditEvent, AuditLogger, AuditOutcome
from veriditi_common.db_types import utcnow
from veriditi_common.logging import get_logger, mask_email
from veriditi_common.notifications import NotificationRequest

SERVICE: Final = "notification"
RESOURCE_TYPE: Final = "notification"

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Esperas entre tentativas; sem espera depois da última"""

    delays: tuple[float, ...] = (1.0, 2.0)

    @property
    def max_attempts(self) -> int:
        return len(self.delays) + 1


# Constante de módulo: RetryPolicy() no default do __init__ dispararia o B008
DEFAULT_RETRY: Final = RetryPolicy()


class SendNotification:
    """Valida, renderiza e reserva a chave na requisição; o SMTP roda depois da resposta"""

    def __init__(
        self,
        *,
        registry: TemplateRegistry,
        renderer: EmailRenderer,
        notifications: NotificationRepository,
        sender: EmailSender,
        audit: AuditLogger,
        scheduler: Scheduler,
        message_ids: MessageIdFactory,
        clock: Clock = utcnow,
        sleep: Sleep = asyncio.sleep,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        self._registry = registry
        self._renderer = renderer
        self._notifications = notifications
        self._sender = sender
        self._audit = audit
        self._scheduler = scheduler
        self._message_ids = message_ids
        self._clock = clock
        self._sleep = sleep
        self._retry = retry

    async def execute(self, request: NotificationRequest) -> bool:
        """True se reservou e agendou; False para chave já conhecida, em qualquer status"""
        data = self._registry.parse(request.template, request.data)
        # Antes da reserva: um bug de template vira 500 sem queimar a chave
        rendered = self._renderer.render(request.template, data)
        context: dict[str, Any] = {
            "template": request.template,
            "idempotency_key": request.idempotency_key,
            "to_masked": mask_email(str(request.to)),
        }
        notification_id = await self._notifications.add(
            request.idempotency_key, request.template, created_at=self._clock()
        )
        if notification_id is None:
            existing = await self._notifications.get(request.idempotency_key)
            log.info(
                "notification_duplicate",
                **context,
                status=existing.status.value if existing else None,
            )
            return False
        email = OutgoingEmail(
            to=str(request.to),
            subject=rendered.subject,
            text=rendered.text,
            html=rendered.html,
            message_id=self._message_ids(),
        )
        self._scheduler.schedule(functools.partial(self._deliver, notification_id, email, context))
        log.info("notification_accepted", **context, notification_id=notification_id)
        return True

    async def _deliver(
        self, notification_id: int, email: OutgoingEmail, context: dict[str, Any]
    ) -> None:
        """Nunca levanta, exceto no cancelamento: a linha fica pending"""
        context = {**context, "notification_id": notification_id}
        error = EmailDeliveryError("NotAttempted")
        attempt = 0
        delivered = False
        try:
            for attempt in range(1, self._retry.max_attempts + 1):
                try:
                    await self._sender.send(email)
                except EmailDeliveryError as exc:
                    error = exc
                except Exception as exc:
                    # Bug no adapter conta como falha transitória; o tipo basta, a mensagem não
                    error = EmailDeliveryError(type(exc).__name__)
                else:
                    delivered = True
                    break
                log.warning(
                    "notification_email_attempt_failed",
                    **context,
                    attempt=attempt,
                    max_attempts=self._retry.max_attempts,
                    error_type=error.reason,
                    smtp_code=error.smtp_code,
                    permanent=error.permanent,
                )
                if error.permanent or attempt == self._retry.max_attempts:
                    break
                await self._sleep(self._retry.delays[attempt - 1])
        except asyncio.CancelledError:
            log.warning("notification_delivery_interrupted", **context, attempts=attempt)
            raise
        # Fora do except acima: cancelado aqui, o SMTP já terminou e o log diz se entregou
        try:
            if delivered:
                await self._finish_sent(email, context, attempt)
            else:
                await self._finish_failed(context, attempt, error)
        except asyncio.CancelledError:
            log.warning(
                "notification_finish_interrupted", **context, attempts=attempt, delivered=delivered
            )
            raise

    async def _finish_sent(
        self, email: OutgoingEmail, context: dict[str, Any], attempts: int
    ) -> None:
        notification_id: int = context["notification_id"]
        await self._update_status(
            functools.partial(
                self._notifications.mark_sent,
                notification_id,
                attempts=attempts,
                message_id=email.message_id,
                sent_at=self._clock(),
            ),
            context,
        )
        log.info(
            "notification_email_sent", **context, attempts=attempts, message_id=email.message_id
        )
        await self._record(
            "notification.email.sent",
            AuditOutcome.SUCCESS,
            notification_id,
            {
                "template": context["template"],
                "to_masked": context["to_masked"],
                "message_id": email.message_id,
                "attempts": attempts,
                "idempotency_key": context["idempotency_key"],
            },
        )

    async def _finish_failed(
        self, context: dict[str, Any], attempts: int, error: EmailDeliveryError
    ) -> None:
        notification_id: int = context["notification_id"]
        await self._update_status(
            functools.partial(self._notifications.mark_failed, notification_id, attempts=attempts),
            context,
        )
        log.error(
            "notification_email_failed",
            **context,
            attempts=attempts,
            error_type=error.reason,
            smtp_code=error.smtp_code,
            permanent=error.permanent,
        )
        await self._record(
            "notification.email.failed",
            AuditOutcome.FAILURE,
            notification_id,
            {
                "template": context["template"],
                "to_masked": context["to_masked"],
                "attempts": attempts,
                "idempotency_key": context["idempotency_key"],
                "error_type": error.reason,
                "smtp_code": error.smtp_code,
                "permanent": error.permanent,
            },
        )

    async def _update_status(
        self, update: Callable[[], Awaitable[bool]], context: dict[str, Any]
    ) -> None:
        """Falha do banco não impede a auditoria, que reflete o que aconteceu no SMTP"""
        try:
            updated = await update()
        except Exception as exc:
            log.error("notification_status_update_failed", **context, error_type=type(exc).__name__)
            return
        if not updated:
            log.warning("notification_status_conflict", **context)

    async def _record(
        self,
        action: str,
        outcome: AuditOutcome,
        notification_id: int,
        metadata: dict[str, Any],
    ) -> None:
        """Sem destinatário em claro, sem data e sem corpo; actor nulo porque é ação do sistema"""
        await self._audit.record(
            AuditEvent(
                occurred_at=self._clock(),
                service=SERVICE,
                action=action,
                outcome=outcome,
                resource_type=RESOURCE_TYPE,
                resource_id=str(notification_id),
                metadata=metadata,
            )
        )
