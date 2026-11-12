from dataclasses import dataclass, field
from enum import StrEnum


class RateKey(StrEnum):
    IP = "ip"
    IP_AND_EMAIL = "ip_email"


@dataclass(frozen=True, slots=True)
class RateLimit:
    # Namespace do bucket e campo policy do log
    name: str
    capacity: int
    # Tempo para encher do zero
    period_seconds: float
    key: RateKey = RateKey.IP


@dataclass(frozen=True, slots=True)
class Upstream:
    name: str
    base_url: str
    # Entra nas mensagens 502/503/504: "Serviço de {label} indisponível."
    label: str


@dataclass(frozen=True, slots=True)
class Route:
    """Rota pública do gateway; o upstream_path explícito tira o /api sem mágica"""

    path: str
    upstream: str
    upstream_path: str
    public: bool = field(kw_only=True)
    methods: frozenset[str] = field(default=frozenset({"POST"}), kw_only=True)
    rate_limit: RateLimit | None = field(default=None, kw_only=True)
    # Casa path e path/...; sem uso na Sprint 1
    prefix: bool = field(default=False, kw_only=True)
    # Headers do cliente além da allowlist do proxy (ex.: assinatura de webhook)
    extra_request_headers: frozenset[str] = field(default=frozenset(), kw_only=True)
