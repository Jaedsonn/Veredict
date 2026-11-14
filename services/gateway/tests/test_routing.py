import pytest
from starlette.exceptions import HTTPException

from gateway_service.domain import RateLimit, Route, Upstream
from gateway_service.routes import LOGIN_LIMIT, REGISTER_LIMIT, RESEND_LIMIT, ROUTES
from gateway_service.routing import ALLOWED_METHODS, RouteTable, is_safe_path

UPSTREAMS = {"auth": Upstream("auth", "http://auth.test", "autenticação")}


@pytest.fixture
def table() -> RouteTable:
    return RouteTable(ROUTES, UPSTREAMS)


def _status(table: RouteTable, method: str, path: str) -> int:
    with pytest.raises(HTTPException) as exc:
        table.match(method, path)
    return exc.value.status_code


@pytest.mark.parametrize("route", ROUTES, ids=lambda r: r.path)
def test_each_route_matches_only_its_methods(table: RouteTable, route: Route) -> None:
    for method in route.methods:
        match = table.match(method, route.path)
        assert match.route is route
        assert match.upstream_path == route.upstream_path
    for method in ALLOWED_METHODS - route.methods:
        assert _status(table, method, route.path) == 405


def test_upstream_path_drops_api_prefix(table: RouteTable) -> None:
    for route in ROUTES:
        assert route.upstream_path == route.path.removeprefix("/api")


def test_method_not_allowed_lists_allowed_methods(table: RouteTable) -> None:
    with pytest.raises(HTTPException) as exc:
        table.match("DELETE", "/api/me")

    assert exc.value.status_code == 405
    assert exc.value.headers == {"Allow": "GET, PATCH"}


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS"])
def test_head_and_options_are_not_allowed(table: RouteTable, method: str) -> None:
    assert _status(table, method, "/api/me") == 405


@pytest.mark.parametrize(
    "path",
    [
        "/api/notifications",
        "/api/events",
        "/api/internal/events",
        "/api/monitoring/events",
        "/api/auth",
        "/api/auth/login/x",
        "/api/me/",
        "/api/me/password/x",
    ],
)
def test_unknown_paths_are_404(table: RouteTable, path: str) -> None:
    assert _status(table, "POST", path) == 404


def test_rate_limits_by_route(table: RouteTable) -> None:
    def limit(path: str) -> object:
        return table.match("POST", path).route.rate_limit

    assert limit("/api/auth/login") is LOGIN_LIMIT
    assert limit("/api/auth/register") is REGISTER_LIMIT
    assert limit("/api/auth/verify-email/resend") is RESEND_LIMIT
    assert limit("/api/auth/verify-email") is None
    assert limit("/api/auth/refresh") is None


def test_public_and_protected_routes() -> None:
    protected = {r.path for r in ROUTES if not r.public}

    assert protected == {"/api/auth/logout", "/api/me", "/api/me/password"}


def test_table_does_not_reach_internal_services() -> None:
    assert {r.upstream for r in ROUTES} == {"auth"}
    for route in ROUTES:
        assert "notification" not in route.path
        assert "monitoring" not in route.path
        assert "internal" not in route.upstream_path


@pytest.mark.parametrize("path", [b"/api/me", b"/api/auth/verify-email/resend", b"/api/x.y_z~1"])
def test_safe_paths(path: bytes) -> None:
    assert is_safe_path(path)


@pytest.mark.parametrize(
    "path",
    [
        b"/api/me/../auth/login",
        b"/api/./me",
        b"/api/..",
        b"/api//me",
        b"/api/%2e%2e/me",
        b"/api/me%2Fpassword",
        b"/api/me%00",
        b"/api/me\\x",
        b"/api",
        b"/api/",
        b"/api/me/",
        b"/apix/me",
        b"/internal/events",
        b"/api/m\xc3\xa9",
        b"/api/me\x80",
        b"/api/me x",
    ],
)
def test_unsafe_paths(path: bytes) -> None:
    assert not is_safe_path(path)


def test_rejects_duplicate_path_and_method() -> None:
    routes = (
        Route("/api/me", "auth", "/me", public=False, methods=frozenset({"GET"})),
        Route("/api/me", "auth", "/me2", public=False, methods=frozenset({"GET", "PATCH"})),
    )
    with pytest.raises(ValueError, match="duplicada"):
        RouteTable(routes, UPSTREAMS)


def test_same_path_with_other_methods_is_fine() -> None:
    routes = (
        Route("/api/me", "auth", "/me", public=False, methods=frozenset({"GET"})),
        Route("/api/me", "auth", "/me", public=False, methods=frozenset({"PATCH"})),
    )
    table = RouteTable(routes, UPSTREAMS)

    assert table.match("PATCH", "/api/me").route is routes[1]


@pytest.mark.parametrize(
    ("route", "message"),
    [
        (Route("/api/x", "notification", "/x", public=True), "desconhecido"),
        (Route("/api/../x", "auth", "/x", public=True), "inseguro"),
        (Route("/internal/x", "auth", "/x", public=True), "inseguro"),
        (Route("/api/x", "auth", "/a/../internal", public=True), "inseguro"),
        (Route("/api/x", "auth", "x", public=True), "inseguro"),
        (Route("/api/x", "auth", "/x", public=True, methods=frozenset({"TRACE"})), "Método"),
        (Route("/api/x", "auth", "/x", public=True, methods=frozenset()), "Método"),
    ],
)
def test_rejects_invalid_routes(route: Route, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RouteTable((route,), UPSTREAMS)


def test_rejects_invalid_rate_limit() -> None:
    route = Route("/api/x", "auth", "/x", public=True, rate_limit=RateLimit("x", 0, 60.0))
    with pytest.raises(ValueError, match="Rate limit"):
        RouteTable((route,), UPSTREAMS)


def test_prefix_route_matches_segment_boundary() -> None:
    captures = Route(
        "/api/captures",
        "auth",
        "/captures",
        public=False,
        methods=frozenset({"GET"}),
        prefix=True,
    )
    table = RouteTable((*ROUTES, captures), UPSTREAMS)

    assert table.match("GET", "/api/captures").upstream_path == "/captures"
    assert table.match("GET", "/api/captures/12").upstream_path == "/captures/12"
    assert table.match("GET", "/api/captures/12/files").upstream_path == "/captures/12/files"
    assert _status(table, "GET", "/api/capturesx") == 404
    assert _status(table, "POST", "/api/captures/12") == 405


def test_longest_prefix_wins() -> None:
    short = Route("/api/a", "auth", "/a", public=True, methods=frozenset({"GET"}), prefix=True)
    long = Route("/api/a/b", "auth", "/ab", public=True, methods=frozenset({"GET"}), prefix=True)
    table = RouteTable((short, long), UPSTREAMS)

    assert table.match("GET", "/api/a/b/c").upstream_path == "/ab/c"
    assert table.match("GET", "/api/a/x").upstream_path == "/a/x"


def test_upstream_lookup(table: RouteTable) -> None:
    assert table.upstream("auth") == UPSTREAMS["auth"]
