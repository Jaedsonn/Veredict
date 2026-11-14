from typing import Annotated, Final

from fastapi import Depends, Query, status
from fastapi.exceptions import RequestValidationError

from monitoring_service.dependencies import IngestDep, ListDep
from monitoring_service.domain import AuditEventFilter
from monitoring_service.schemas import (
    AcceptedResponse,
    AuditEventIn,
    AuditEventOut,
    AuditEventsPage,
)
from veriditi_common.audit import StorableDatetime
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


def _filters(
    actor_id: Annotated[int | None, Query(ge=1, le=_MAX_BIGINT)] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    occurred_from: Annotated[StorableDatetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[StorableDatetime | None, Query(alias="to")] = None,
) -> AuditEventFilter:
    """Janela invertida é erro de entrada, no mesmo formato dos demais 422"""
    if occurred_from is not None and occurred_to is not None and occurred_from > occurred_to:
        raise RequestValidationError(
            [
                {
                    "type": "invalid_time_range",
                    "loc": ("query", "from"),
                    "msg": "from precisa ser anterior ou igual a to",
                }
            ]
        )
    return AuditEventFilter(
        actor_id=actor_id,
        action=action,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )


@router.get("/events", response_model=AuditEventsPage)
async def list_events(
    use_case: ListDep,
    filters: Annotated[AuditEventFilter, Depends(_filters)],
    after_id: Annotated[int | None, Query(ge=0, le=_MAX_BIGINT)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> AuditEventsPage:
    """Ordem do id com cursor after_id; use Z ou %2B no fuso, um + cru vira espaço"""
    page = await use_case.execute(filters, after_id=after_id, limit=limit)
    return AuditEventsPage(
        items=[AuditEventOut.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
    )
