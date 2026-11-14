from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.domain import AuditEventFilter, StoredAuditEvent
from monitoring_service.models import EVENT_ID_UNIQUE, AuditEventRecord
from veriditi_common.audit import AuditEvent
from veriditi_common.logging import get_logger

MYSQL_DUPLICATE_ENTRY: Final = 1062
# Só deadlock: o InnoDB desfaz a vítima na hora. Repetir um 1205 seguraria o POST mais 50 s
MYSQL_DEADLOCK: Final = 1213

log = get_logger(__name__)
_SQLITE_DUPLICATE: Final = "UNIQUE constraint failed: audit_events.event_id"


def is_duplicate_event_id(exc: IntegrityError) -> bool:
    """Só a uq_audit_events_event_id é reenvio; outra violação é bug e precisa subir"""
    args: tuple[object, ...] = getattr(exc.orig, "args", ())
    if len(args) >= 2 and args[0] == MYSQL_DUPLICATE_ENTRY:
        return EVENT_ID_UNIQUE in str(args[1])
    return _SQLITE_DUPLICATE in str(exc.orig)


def _is_deadlock(exc: OperationalError) -> bool:
    args: tuple[object, ...] = getattr(exc.orig, "args", ())
    return bool(args) and args[0] == MYSQL_DEADLOCK


def _record(event: AuditEvent, received_at: datetime) -> AuditEventRecord:
    return AuditEventRecord(
        event_id=event.event_id,
        occurred_at=event.occurred_at,
        received_at=received_at,
        service=event.service,
        action=event.action,
        outcome=event.outcome,
        actor_id=event.actor_id,
        actor_ip=str(event.actor_ip) if event.actor_ip is not None else None,
        request_id=event.request_id,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        metadata_=event.metadata or None,
    )


class SqlAlchemyAuditEventRepository:
    """INSERT simples: IGNORE rebaixaria outros erros e ON DUPLICATE exigiria UPDATE"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent, *, received_at: datetime) -> bool:
        try:
            return await self._insert(event, received_at)
        except OperationalError as exc:
            # Reenvios concorrentes esperando a 1ª escrita entram em deadlock se ela desfizer
            if not _is_deadlock(exc):
                raise
            log.warning(
                "audit_insert_retried", event_id=str(event.event_id), db_errno=MYSQL_DEADLOCK
            )
            return await self._insert(event, received_at)

    async def _insert(self, event: AuditEvent, received_at: datetime) -> bool:
        self._session.add(_record(event, received_at))
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            if is_duplicate_event_id(exc):
                return False
            raise
        except OperationalError:
            await self._session.rollback()
            raise
        return True

    async def get(self, event_id: UUID) -> StoredAuditEvent | None:
        stmt = select(AuditEventRecord).where(AuditEventRecord.event_id == event_id)
        record = await self._session.scalar(stmt)
        return _to_domain(record) if record is not None else None

    async def search(
        self, filters: AuditEventFilter, *, after_id: int | None, limit: int
    ) -> list[StoredAuditEvent]:
        stmt = select(AuditEventRecord).order_by(AuditEventRecord.id).limit(limit)
        if after_id is not None:
            stmt = stmt.where(AuditEventRecord.id > after_id)
        if filters.actor_id is not None:
            stmt = stmt.where(AuditEventRecord.actor_id == filters.actor_id)
        if filters.action is not None:
            stmt = stmt.where(AuditEventRecord.action == filters.action)
        if filters.occurred_from is not None:
            stmt = stmt.where(AuditEventRecord.occurred_at >= filters.occurred_from)
        if filters.occurred_to is not None:
            stmt = stmt.where(AuditEventRecord.occurred_at < filters.occurred_to)
        return [_to_domain(record) for record in await self._session.scalars(stmt)]


def _to_domain(record: AuditEventRecord) -> StoredAuditEvent:
    return StoredAuditEvent(
        id=record.id,
        event_id=record.event_id,
        occurred_at=record.occurred_at,
        received_at=record.received_at,
        service=record.service,
        action=record.action,
        outcome=record.outcome,
        actor_id=record.actor_id,
        actor_ip=record.actor_ip,
        request_id=record.request_id,
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        metadata=record.metadata_ or {},
    )
