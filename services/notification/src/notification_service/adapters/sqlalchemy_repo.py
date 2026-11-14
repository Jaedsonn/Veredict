from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification_service.domain import NotificationStatus, StoredNotification
from notification_service.models import IDEMPOTENCY_KEY_UNIQUE, NotificationRecord
from veriditi_common.logging import get_logger

MYSQL_DUPLICATE_ENTRY: Final = 1062
# Só deadlock: o InnoDB desfaz a vítima na hora. Repetir um 1205 seguraria o POST mais 50 s
MYSQL_DEADLOCK: Final = 1213

log = get_logger(__name__)
_SQLITE_DUPLICATE: Final = "UNIQUE constraint failed: notifications_sent.idempotency_key"


def is_duplicate_idempotency_key(exc: IntegrityError) -> bool:
    """Só a uq_notifications_sent_idempotency_key é repetição; outra violação é bug e sobe"""
    args: tuple[object, ...] = getattr(exc.orig, "args", ())
    if len(args) >= 2 and args[0] == MYSQL_DUPLICATE_ENTRY:
        return IDEMPOTENCY_KEY_UNIQUE in str(args[1])
    return _SQLITE_DUPLICATE in str(exc.orig)


def _is_deadlock(exc: OperationalError) -> bool:
    args: tuple[object, ...] = getattr(exc.orig, "args", ())
    return bool(args) and args[0] == MYSQL_DEADLOCK


class SqlAlchemyNotificationRepository:
    """Uma sessão curta por operação: o envio adiado vive depois da sessão da requisição"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, idempotency_key: str, template: str, *, created_at: datetime) -> int | None:
        try:
            return await self._insert(idempotency_key, template, created_at)
        except OperationalError as exc:
            # Repetições concorrentes esperando a 1ª reserva entram em deadlock se ela desfizer
            if not _is_deadlock(exc):
                raise
            log.warning(
                "notification_insert_retried",
                idempotency_key=idempotency_key,
                db_errno=MYSQL_DEADLOCK,
            )
            return await self._insert(idempotency_key, template, created_at)

    async def _insert(
        self, idempotency_key: str, template: str, created_at: datetime
    ) -> int | None:
        """INSERT simples: IGNORE rebaixaria outros erros e ON DUPLICATE exigiria UPDATE"""
        async with self._sessions() as session:
            record = NotificationRecord(
                idempotency_key=idempotency_key,
                template=template,
                status=NotificationStatus.PENDING,
                attempts=0,
                created_at=created_at,
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                if is_duplicate_idempotency_key(exc):
                    return None
                raise
            except OperationalError:
                await session.rollback()
                raise
            return record.id

    async def get(self, idempotency_key: str) -> StoredNotification | None:
        stmt = select(NotificationRecord).where(
            NotificationRecord.idempotency_key == idempotency_key
        )
        async with self._sessions() as session:
            record = await session.scalar(stmt)
        return _to_domain(record) if record is not None else None

    async def mark_sent(
        self, notification_id: int, *, attempts: int, message_id: str, sent_at: datetime
    ) -> bool:
        return await self._finish(
            notification_id,
            status=NotificationStatus.SENT,
            attempts=attempts,
            message_id=message_id,
            sent_at=sent_at,
        )

    async def mark_failed(self, notification_id: int, *, attempts: int) -> bool:
        return await self._finish(
            notification_id, status=NotificationStatus.FAILED, attempts=attempts
        )

    async def _finish(self, notification_id: int, **values: Any) -> bool:
        """UPDATE condicional: nunca regride sent ou failed"""
        stmt = (
            update(NotificationRecord)
            .where(
                NotificationRecord.id == notification_id,
                NotificationRecord.status == NotificationStatus.PENDING,
            )
            .values(**values)
        )
        async with self._sessions() as session:
            result = await session.execute(stmt)
            await session.commit()
        return cast("CursorResult[Any]", result).rowcount == 1


def _to_domain(record: NotificationRecord) -> StoredNotification:
    return StoredNotification(
        id=record.id,
        idempotency_key=record.idempotency_key,
        template=record.template,
        status=record.status,
        attempts=record.attempts,
        message_id=record.message_id,
        created_at=record.created_at,
        sent_at=record.sent_at,
    )
