from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.adapters.sqlalchemy_repo import SqlAlchemyAuditEventRepository
from monitoring_service.ports import AuditEventRepository
from monitoring_service.use_cases.ingest_event import IngestAuditEvent


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """O Database vive em app.state (criado no lifespan) para os testes poderem trocá-lo"""
    async for session in request.app.state.db.session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_audit_event_repository(session: SessionDep) -> AuditEventRepository:
    return SqlAlchemyAuditEventRepository(session)


AuditEventRepositoryDep = Annotated[AuditEventRepository, Depends(get_audit_event_repository)]


def get_ingest_audit_event(request: Request, events: AuditEventRepositoryDep) -> IngestAuditEvent:
    return IngestAuditEvent(events, clock=request.app.state.clock)


IngestDep = Annotated[IngestAuditEvent, Depends(get_ingest_audit_event)]
