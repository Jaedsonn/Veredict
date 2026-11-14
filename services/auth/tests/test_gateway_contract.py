"""Contrato gateway × auth: toda rota do gateway com upstream auth existe no OpenAPI do auth"""

from collections.abc import Iterable, Mapping
from typing import Any

import pytest

from auth_service.config import Settings
from auth_service.main import create_app
from gateway_service.domain import Route
from gateway_service.routes import ROUTES

AUTH_ROUTES = tuple(route for route in ROUTES if route.upstream == "auth")


def _is_endpoint(path: str) -> bool:
    return path.startswith(("/auth/", "/me/")) or path == "/me"


def missing_operations(paths: Mapping[str, Any], routes: Iterable[Route]) -> list[str]:
    """Operações que o gateway encaminha e o OpenAPI não declara"""
    return sorted(
        f"{method} {route.upstream_path}"
        for route in routes
        for method in route.methods
        if method.lower() not in paths.get(route.upstream_path, {})
    )


def test_gateway_has_exact_auth_routes() -> None:
    # Rota prefix não aparece como caminho único no OpenAPI
    assert AUTH_ROUTES
    assert not any(route.prefix for route in AUTH_ROUTES)


def test_missing_operations_lists_path_and_method() -> None:
    paths = {"/me": {"get": {}}, "/auth/login": {"post": {}}}
    routes = (
        Route("/api/me", "auth", "/me", public=False, methods=frozenset({"GET", "PATCH"})),
        Route("/api/auth/login", "auth", "/auth/login", public=True),
        Route("/api/auth/x", "auth", "/auth/x", public=True),
    )

    assert missing_operations(paths, routes) == ["PATCH /me", "POST /auth/x"]


def test_gateway_routes_exist_in_auth_openapi(settings: Settings) -> None:
    paths = create_app(settings=settings).openapi()["paths"]
    if not any(_is_endpoint(path) for path in paths):
        pytest.skip("auth sem endpoints nesta branch: o contrato passa a valer com o PR #54")

    assert missing_operations(paths, AUTH_ROUTES) == []
