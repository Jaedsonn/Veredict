from datetime import datetime
from typing import Final

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.models import EVENT_ID_UNIQUE, AuditEventRecord
from veriditi_common.audit import AuditEvent

MYSQL_DUPLICATE_ENTRY: Final = 1062
_SQLITE_DUPLICATE: Final = "UNIQUE constraint failed: audit_events.event_id"


def is_duplicate_event_id(exc: IntegrityError) -> bool:
    """Só a uq_audit_events_event_id é reenvio; outra violação é bug e precisa subir"""
    args: tuple[object, ...] = getattr(exc.orig, "args", ())
    if len(args) >= 2 and args[0] == MYSQL_DUPLICATE_ENTRY:
        return EVENT_ID_UNIQUE in str(args[1])
    return _SQLITE_DUPLICATE in str(exc.orig)


class SqlAlchemyAuditEventRepository:
    """INSERT simples: IGNORE rebaixaria outros erros e ON DUPLICATE exigiria UPDATE"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent, *, received_at: datetime) -> bool:
        self._session.add(
            AuditEventRecord(
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
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            if is_duplicate_event_id(exc):
                return False
            raise
        return True
