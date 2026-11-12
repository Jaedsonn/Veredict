"""Tabela de rotas da Sprint 1; um serviço novo só acrescenta linhas"""

from typing import Final

from gateway_service.domain import RateKey, RateLimit, Route

LOGIN_LIMIT: Final = RateLimit("login", 5, 60.0, RateKey.IP_AND_EMAIL)
REGISTER_LIMIT: Final = RateLimit("register", 10, 60.0)
RESEND_LIMIT: Final = RateLimit("resend", 10, 60.0)

ROUTES: Final[tuple[Route, ...]] = (
    Route("/api/auth/register", "auth", "/auth/register", public=True, rate_limit=REGISTER_LIMIT),
    Route("/api/auth/verify-email", "auth", "/auth/verify-email", public=True),
    Route(
        "/api/auth/verify-email/resend",
        "auth",
        "/auth/verify-email/resend",
        public=True,
        rate_limit=RESEND_LIMIT,
    ),
    Route("/api/auth/login", "auth", "/auth/login", public=True, rate_limit=LOGIN_LIMIT),
    Route("/api/auth/refresh", "auth", "/auth/refresh", public=True),
    Route("/api/auth/logout", "auth", "/auth/logout", public=False),
    Route("/api/me", "auth", "/me", public=False, methods=frozenset({"GET", "PATCH"})),
    Route("/api/me/password", "auth", "/me/password", public=False),
)
