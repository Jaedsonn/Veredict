from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Annotated, Final
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import NoDecode

from gateway_service.domain import Upstream
from veriditi_common.settings import BaseServiceSettings

ProxyNetwork = IPv4Network | IPv6Network

_MISSING_KEY: Final = "JWT_PUBLIC_KEY não definido: rode `make keys` e reinicie o gateway"


def _http_url(name: str, value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"{name} precisa ser uma URL http(s) absoluta")
    return value.rstrip("/")


class Settings(BaseServiceSettings):
    service_name: str = "gateway"
    auth_url: str = "http://localhost:8001"
    upstream_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    health_timeout_s: float = Field(default=2.0, gt=0, le=60)
    jwt_public_key: str | None = None
    jwt_issuer: str = "veriditi-auth"
    jwt_audience: str = "veriditi"
    jwt_leeway_seconds: int = Field(default=10, ge=0, le=60)
    # Vazio: nenhum proxy confiável, o X-Forwarded-For do cliente é ignorado
    trusted_proxies: Annotated[tuple[ProxyNetwork, ...], NoDecode] = ()
    web_url: str = "http://localhost:3000"
    max_body_bytes: int = Field(default=1_048_576, ge=1024, le=104_857_600)

    @field_validator("auth_url")
    @classmethod
    def _auth_url(cls, value: str) -> str:
        return _http_url("AUTH_URL", value)

    @field_validator("web_url")
    @classmethod
    def _web_url(cls, value: str) -> str:
        """Só a origem vira allow_origins do CORS; um path seria ignorado em silêncio"""
        url = _http_url("WEB_URL", value)
        if urlsplit(url).path or urlsplit(url).query:
            raise ValueError("WEB_URL não pode ter path nem query")
        return url

    @field_validator("jwt_public_key", mode="before")
    @classmethod
    def _empty_key_is_missing(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _parse_proxies(cls, value: object) -> object:
        """CSV de CIDR ou IP solto (vira /32 ou /128), sem exigir JSON no .env"""
        if not isinstance(value, str):
            return value
        networks: list[ProxyNetwork] = []
        for item in (part.strip() for part in value.split(",")):
            if not item:
                continue
            try:
                networks.append(ip_network(item, strict=False))
            except ValueError:
                raise ValueError(f"TRUSTED_PROXIES: item inválido {item!r}") from None
        return tuple(networks)

    @property
    def upstreams(self) -> dict[str, Upstream]:
        """Notification e monitoring são internos e ficam fora, de propósito"""
        return {"auth": Upstream("auth", self.auth_url, "autenticação")}

    @property
    def upstream_urls(self) -> dict[str, str]:
        """Serviços que o /health/ready agrega"""
        return {name: upstream.base_url for name, upstream in self.upstreams.items()}

    @property
    def web_origin(self) -> str:
        parts = urlsplit(self.web_url)
        return f"{parts.scheme}://{parts.netloc}"

    def require_jwt_public_key(self) -> str:
        """Fail-fast: sem a chave nenhum token validaria"""
        if self.jwt_public_key is None:
            raise RuntimeError(_MISSING_KEY)
        return self.jwt_public_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
