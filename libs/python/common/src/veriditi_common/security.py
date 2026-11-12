"""Autenticação das chamadas internas: token compartilhado e usuário injetado pelo gateway"""

import hmac
import re
import uuid
from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import Depends, FastAPI, Header, Request
from pydantic import SecretStr

from veriditi_common.errors import UnauthorizedError
from veriditi_common.logging import get_logger

INTERNAL_TOKEN_HEADER: Final = "X-Internal-Token"
USER_ID_HEADER: Final = "X-User-Id"
USER_EMAIL_HEADER: Final = "X-User-Email"
SESSION_ID_HEADER: Final = "X-Session-Id"
# O gateway (#11) remove estes headers do cliente e injeta os próprios
INTERNAL_HEADERS: Final[frozenset[str]] = frozenset(
    h.lower() for h in (INTERNAL_TOKEN_HEADER, USER_ID_HEADER, USER_EMAIL_HEADER, SESSION_ID_HEADER)
)

_USER_ID: Final = re.compile(r"[1-9][0-9]{0,18}")
_MAX_BIGINT: Final = 2**63 - 1
_MAX_EMAIL_LENGTH: Final = 255

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: int
    email: str
    session_id: str | None


def install_internal_auth(app: FastAPI, token: SecretStr) -> None:
    if not token.get_secret_value():
        raise ValueError("Token interno vazio")
    app.state.internal_api_token = token


async def require_internal_token(
    request: Request,
    x_internal_token: Annotated[str | None, Header(alias=INTERNAL_TOKEN_HEADER)] = None,
) -> None:
    """Fail closed: sem install_internal_auth a rota responde 500, nunca libera"""
    expected: SecretStr | None = getattr(request.app.state, "internal_api_token", None)
    if expected is None:
        raise RuntimeError("install_internal_auth não foi chamado no create_app")
    if not x_internal_token:
        log.warning("internal_token_rejected", reason="missing")
        raise UnauthorizedError()
    # Em bytes: compare_digest com str não ASCII levanta TypeError (500)
    if not hmac.compare_digest(x_internal_token.encode(), expected.get_secret_value().encode()):
        log.warning("internal_token_rejected", reason="invalid")
        raise UnauthorizedError()


async def get_current_user(
    _token: Annotated[None, Depends(require_internal_token)],
    user_id: Annotated[str | None, Header(alias=USER_ID_HEADER)] = None,
    email: Annotated[str | None, Header(alias=USER_EMAIL_HEADER)] = None,
    session_id: Annotated[str | None, Header(alias=SESSION_ID_HEADER)] = None,
) -> CurrentUser:
    """Só confia nos headers de usuário quando o token prova que vieram do gateway"""
    if user_id is None or not _USER_ID.fullmatch(user_id) or int(user_id) > _MAX_BIGINT:
        raise UnauthorizedError()
    if not email or len(email) > _MAX_EMAIL_LENGTH:
        raise UnauthorizedError()
    sid: str | None = None
    if session_id:
        try:
            sid = str(uuid.UUID(session_id))
        except ValueError:
            raise UnauthorizedError() from None
    return CurrentUser(id=int(user_id), email=email, session_id=sid)


InternalTokenDep = Annotated[None, Depends(require_internal_token)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
