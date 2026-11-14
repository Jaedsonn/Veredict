"""Contrato gateway × auth: toda rota do gateway com upstream auth existe no OpenAPI do auth"""

from collections.abc import Iterable, Mapping
from typing import Any

import pytest

from auth_service.config import Settings
from auth_service.main import create_app
from gateway_service.domain import Route
from gateway_service.routes import ROUTES

AUTH_ROUTES = tuple(route for route in ROUTES if route.upstream == "auth")


def has_only_health(paths: Iterable[str]) -> bool:
    """Auth ainda sem endpoints: o OpenAPI só declara /health/*"""
    return all(path.startswith("/health") for path in paths)


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


def test_only_health_paths_skip_the_contract() -> None:
    assert has_only_health({"/health/live": {}, "/health/ready": {}})


def test_single_auth_path_enforces_the_contract() -> None:
    assert not has_only_health({"/health/live": {}, "/auth/login": {"post": {}}})


def test_routes_under_another_prefix_fail_the_contract() -> None:
    paths = {"/health/live": {}, "/v1/auth/login": {"post": {}}, "/v1/me": {"get": {}}}
    every_operation = sorted(
        f"{method} {route.upstream_path}" for route in AUTH_ROUTES for method in route.methods
    )

    assert not has_only_health(paths)
    assert missing_operations(paths, AUTH_ROUTES) == every_operation


def test_gateway_routes_exist_in_auth_openapi(settings: Settings) -> None:
    paths = create_app(settings=settings).openapi()["paths"]
    # Remover este skip quando o #54 entrar: depois disso, auth sem rota voltaria a pular
    if has_only_health(paths):
        pytest.skip("auth sem endpoints nesta branch: o contrato passa a valer com o PR #54")

    assert missing_operations(paths, AUTH_ROUTES) == []
