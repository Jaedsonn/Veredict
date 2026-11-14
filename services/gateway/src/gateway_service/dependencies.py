from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request

from gateway_service.adapters.reverse_proxy import ReverseProxy
from gateway_service.client_ip import TrustedProxies
from gateway_service.config import Settings
from gateway_service.ports import JwtVerifier, RateLimiter
from gateway_service.routes import ROUTES
from gateway_service.routing import RouteTable
from gateway_service.use_cases.admit_request import AdmitRequest


@dataclass(frozen=True, slots=True)
class Gateway:
    table: RouteTable
    admit: AdmitRequest
    proxy: ReverseProxy
    trusted: TrustedProxies


def build_gateway(
    settings: Settings,
    client: httpx.AsyncClient,
    *,
    limiter: RateLimiter,
    verifier: JwtVerifier,
) -> Gateway:
    """Composition root: o mesmo registro de upstreams na tabela, no proxy e no health"""
    upstreams = settings.upstreams
    return Gateway(
        table=RouteTable(ROUTES, upstreams),
        admit=AdmitRequest(limiter, verifier),
        proxy=ReverseProxy(client, upstreams, settings.internal_token),
        trusted=TrustedProxies(settings.trusted_proxies),
    )


def get_gateway(request: Request) -> Gateway:
    gateway: Gateway = request.app.state.gateway
    return gateway


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Um client por processo (pool de conexões), criado no lifespan"""
    client: httpx.AsyncClient = request.app.state.http
    return client


GatewayDep = Annotated[Gateway, Depends(get_gateway)]
