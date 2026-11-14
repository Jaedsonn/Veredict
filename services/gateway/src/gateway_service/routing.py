import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from starlette.exceptions import HTTPException

from gateway_service.domain import Route, Upstream

ALLOWED_METHODS: Final = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
# Bytes crus, antes do percent-decode: %, //, barra final e \ ficam de fora
_SAFE_API_PATH: Final = re.compile(rb"/api(?:/[A-Za-z0-9._~-]+)+")
_SAFE_UPSTREAM_PATH: Final = re.compile(rb"(?:/[A-Za-z0-9._~-]+)+")
_DOT_SEGMENTS: Final = frozenset({b".", b".."})


def _no_dot_segments(path: bytes) -> bool:
    return not any(segment in _DOT_SEGMENTS for segment in path.split(b"/"))


def is_safe_path(raw_path: bytes) -> bool:
    """Recusa em vez de normalizar: nenhuma rota precisa de caractere codificado"""
    return _SAFE_API_PATH.fullmatch(raw_path) is not None and _no_dot_segments(raw_path)


def _is_safe_upstream_path(path: str) -> bool:
    raw = path.encode()
    return _SAFE_UPSTREAM_PATH.fullmatch(raw) is not None and _no_dot_segments(raw)


@dataclass(frozen=True, slots=True)
class RouteMatch:
    route: Route
    # route.upstream_path + sufixo nas rotas prefix
    upstream_path: str


class RouteTable:
    """Validada no startup: rota quebrada derruba a subida, não a 1ª requisição"""

    def __init__(self, routes: Iterable[Route], upstreams: Mapping[str, Upstream]) -> None:
        self._upstreams = dict(upstreams)
        self._by_path: dict[str, dict[str, Route]] = {}
        for route in routes:
            self._validate(route)
            by_method = self._by_path.setdefault(route.path, {})
            for method in route.methods:
                if method in by_method:
                    raise ValueError(f"Rota duplicada: {method} {route.path}")
                by_method[method] = route
        # Do prefixo mais longo para o mais curto
        self._prefixes = sorted(
            (path for path, by_method in self._by_path.items() if _any_prefix(by_method)),
            key=len,
            reverse=True,
        )

    def _validate(self, route: Route) -> None:
        if not is_safe_path(route.path.encode()):
            raise ValueError(f"Path inseguro na tabela: {route.path!r}")
        if not _is_safe_upstream_path(route.upstream_path):
            raise ValueError(f"upstream_path inseguro na tabela: {route.upstream_path!r}")
        if route.upstream not in self._upstreams:
            raise ValueError(f"Upstream desconhecido: {route.upstream!r} em {route.path}")
        if not route.methods or not route.methods <= ALLOWED_METHODS:
            raise ValueError(f"Método inválido em {route.path}: {sorted(route.methods)}")
        limit = route.rate_limit
        if limit is not None and (limit.capacity < 1 or limit.period_seconds <= 0):
            raise ValueError(f"Rate limit inválido em {route.path}")

    def match(self, method: str, path: str) -> RouteMatch:
        """404 quando nenhum path casa; 405 com Allow quando só o método não casa"""
        suffix = ""
        by_method = self._by_path.get(path)
        if by_method is None:
            for prefix in self._prefixes:
                if path.startswith(prefix + "/"):
                    suffix = path[len(prefix) :]
                    by_method = {m: r for m, r in self._by_path[prefix].items() if r.prefix}
                    break
        if by_method is None:
            raise HTTPException(404)
        route = by_method.get(method)
        if route is None:
            raise HTTPException(405, headers={"Allow": ", ".join(sorted(by_method))})
        return RouteMatch(route, route.upstream_path + suffix)

    def upstream(self, name: str) -> Upstream:
        return self._upstreams[name]


def _any_prefix(by_method: Mapping[str, Route]) -> bool:
    return any(route.prefix for route in by_method.values())
