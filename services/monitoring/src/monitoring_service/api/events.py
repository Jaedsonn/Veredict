from typing import Annotated, Final

from fastapi import Query, status
from pydantic import AwareDatetime

from monitoring_service.dependencies import IngestDep, ListDep
from monitoring_service.domain import AuditEventFilter
from monitoring_service.schemas import (
    AcceptedResponse,
    AuditEventIn,
    AuditEventOut,
    AuditEventsPage,
)
from veriditi_common.security import internal_router

DEFAULT_LIMIT: Final = 50
MAX_LIMIT: Final = 200
_MAX_BIGINT: Final = 2**63 - 1

# Só POST e GET: a trilha é append-only e não tem rota de edição nem de remoção
router = internal_router(tags=["audit"])


@router.post("/events", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedResponse)
async def ingest_event(event: AuditEventIn, use_case: IngestDep) -> AcceptedResponse:
    """Mesma resposta para evento novo e reenvio, só depois do COMMIT"""
    await use_case.execute(event)
    return AcceptedResponse()


@router.get("/events", response_model=AuditEventsPage)
async def list_events(
    use_case: ListDep,
    actor_id: Annotated[int | None, Query(ge=1, le=_MAX_BIGINT)] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    occurred_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    after_id: Annotated[int | None, Query(ge=0, le=_MAX_BIGINT)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> AuditEventsPage:
    """Ordem de inserção (id) com cursor after_id; use Z ou %2B no fuso, um + cru vira espaço"""
    filters = AuditEventFilter(
        actor_id=actor_id,
        action=action,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )
    page = await use_case.execute(filters, after_id=after_id, limit=limit)
    return AuditEventsPage(
        items=[AuditEventOut.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
    )
