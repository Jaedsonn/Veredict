"""Segurança de comunicação interna entre o API Gateway e os serviços (RNF01, RF06)."""

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Identidade propagada pelo API Gateway após validação do JWT."""

    id: int
    email: str | None = None


def _expected_internal_token(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    if settings is not None and hasattr(settings, "internal_api_token"):
        token_attr = settings.internal_api_token
        return (
            token_attr.get_secret_value()
            if hasattr(token_attr, "get_secret_value")
            else str(token_attr)
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "internal_config_error", "message": "Token interno não configurado."},
    )


def require_internal_token(
    request: Request,
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    """Valida o header `X-Internal-Token` em tempo constante (`hmac.compare_digest`)."""
    expected = _expected_internal_token(request)
    if not x_internal_token or not hmac.compare_digest(
        x_internal_token.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Token interno ausente ou inválido."},
        )


def get_current_user(
    _: Annotated[None, Depends(require_internal_token)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_email: Annotated[str | None, Header(alias="X-User-Email")] = None,
) -> AuthenticatedUser:
    """Lê `X-User-Id` e `X-User-Email` injetados exclusivamente pelo API Gateway (#10, #11)."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Identidade do usuário não informada."},
        )
    try:
        user_id = int(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Identificador de usuário inválido."},
        ) from exc
    if user_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Identificador de usuário inválido."},
        )
    return AuthenticatedUser(
        id=user_id,
        email=x_user_email.strip().lower() if x_user_email else None,
    )
