from fastapi import status
from fastapi.exceptions import RequestValidationError

from notification_service.dependencies import SendNotificationDep
from notification_service.domain import InvalidTemplateDataError, UnknownTemplateError
from notification_service.schemas import AcceptedResponse
from veriditi_common.notifications import NotificationRequest
from veriditi_common.security import internal_router

# Só POST: o serviço é interno e não tem rota de consulta (sem rota no gateway)
router = internal_router(tags=["notifications"])


@router.post(
    "/notifications", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedResponse
)
async def send_notification(
    body: NotificationRequest, use_case: SendNotificationDep
) -> AcceptedResponse:
    """Mesma resposta para chave nova e repetida, só depois do COMMIT da reserva"""
    try:
        await use_case.execute(body)
    except UnknownTemplateError as exc:
        # Formato de validação do FastAPI: o endpoint tem um único formato de 422
        raise RequestValidationError(
            [
                {
                    "type": "unknown_template",
                    "loc": ("body", "template"),
                    "msg": f"Template desconhecido. Válidos: {', '.join(exc.valid)}",
                }
            ]
        ) from None
    except InvalidTemplateDataError as exc:
        raise RequestValidationError(
            [{**error, "loc": ("body", "data", *error["loc"])} for error in exc.errors]
        ) from None
    return AcceptedResponse()
