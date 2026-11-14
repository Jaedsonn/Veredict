from typing import Final

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.requests import ClientDisconnect

from gateway_service.client_ip import resolve_client_ip
from gateway_service.dependencies import GatewayDep
from gateway_service.domain import RateKey
from gateway_service.routing import is_safe_path
from veriditi_common.logging import get_logger
from veriditi_common.middleware import set_log_fields

# Todos para o 405 sair da tabela com o Allow certo
_ALL_METHODS: Final = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
# O login real tem menos de 1 KiB
BUFFERED_BODY_MAX: Final = 16 * 1024

log = get_logger(__name__)
router = APIRouter()


async def read_bounded(request: Request, limit: int) -> bytes:
    """Só o login bufferiza, para tirar o e-mail da chave do rate limit"""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413)
        chunks.append(chunk)
    return b"".join(chunks)


@router.api_route("/api/{rest:path}", methods=_ALL_METHODS, include_in_schema=False)
async def proxy(request: Request, gateway: GatewayDep) -> Response:
    """Casa a rota, aplica rate limit e JWT e repassa ao upstream"""
    raw_path: bytes = request.scope.get("raw_path") or request.url.path.encode()
    if not is_safe_path(raw_path.split(b"?")[0]):
        raise HTTPException(404)
    match = gateway.table.match(request.method, request.url.path)
    route = match.route
    set_log_fields(request, route=route.path, upstream=route.upstream)
    client_ip = resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.getlist("x-forwarded-for"),
        gateway.trusted,
    )
    body: bytes | None = None
    if route.rate_limit is not None and route.rate_limit.key is RateKey.IP_AND_EMAIL:
        try:
            body = await read_bounded(request, BUFFERED_BODY_MAX)
        except ClientDisconnect:
            log.info("client_disconnected", upstream=route.upstream)
            return Response(status_code=400)
    principal = await gateway.admit.execute(
        route, client_ip=client_ip, authorization=request.headers.get("authorization"), body=body
    )
    if principal is not None:
        set_log_fields(request, user_id=principal.user_id)
    return await gateway.proxy.forward(
        request, match, principal=principal, client_ip=client_ip, body=body
    )
