from fastapi import status

from monitoring_service.dependencies import IngestDep
from monitoring_service.schemas import AcceptedResponse, AuditEventIn
from veriditi_common.security import internal_router

# Só POST e GET: a trilha é append-only e não tem rota de edição nem de remoção
router = internal_router(tags=["audit"])


@router.post("/events", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedResponse)
async def ingest_event(event: AuditEventIn, use_case: IngestDep) -> AcceptedResponse:
    """Mesma resposta para evento novo e reenvio, só depois do COMMIT"""
    await use_case.execute(event)
    return AcceptedResponse()
