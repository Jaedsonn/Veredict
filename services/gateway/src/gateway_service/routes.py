"""Tabela de rotas do gateway; um serviço novo só acrescenta linhas"""

from typing import Final

from gateway_service.domain import RateKey, RateLimit, Route

LOGIN_LIMIT: Final = RateLimit("login", 5, 60.0, RateKey.IP_AND_EMAIL)
REGISTER_LIMIT: Final = RateLimit("register", 10, 60.0)
RESEND_LIMIT: Final = RateLimit("resend", 10, 60.0)
# Token bucket: rajada igual à capacidade e depois 1 ficha a cada período/capacidade
# (forgot por e-mail: 3 de rajada, depois 1 a cada 20 min)
FORGOT_IP_LIMIT: Final = RateLimit("forgot_ip", 10, 3600.0)
FORGOT_EMAIL_LIMIT: Final = RateLimit("forgot_email", 3, 3600.0, RateKey.EMAIL)
RESET_LIMIT: Final = RateLimit("reset_ip", 10, 3600.0)
# Cada pedido gera uma cobrança no provedor: limita rajadas de cliques e scripts (REQ05)
ORDER_LIMIT: Final = RateLimit("orders", 10, 60.0)

ROUTES: Final[tuple[Route, ...]] = (
    Route(
        "/api/auth/register", "auth", "/auth/register", public=True, rate_limits=(REGISTER_LIMIT,)
    ),
    Route("/api/auth/verify-email", "auth", "/auth/verify-email", public=True),
    Route(
        "/api/auth/verify-email/resend",
        "auth",
        "/auth/verify-email/resend",
        public=True,
        rate_limits=(RESEND_LIMIT,),
    ),
    Route("/api/auth/login", "auth", "/auth/login", public=True, rate_limits=(LOGIN_LIMIT,)),
    Route("/api/auth/refresh", "auth", "/auth/refresh", public=True),
    # IP antes do e-mail: um IP que varre e-mails para no limite dele sem gastar o dos alvos
    Route(
        "/api/auth/password/forgot",
        "auth",
        "/auth/password/forgot",
        public=True,
        rate_limits=(FORGOT_IP_LIMIT, FORGOT_EMAIL_LIMIT),
    ),
    Route(
        "/api/auth/password/reset",
        "auth",
        "/auth/password/reset",
        public=True,
        rate_limits=(RESET_LIMIT,),
    ),
    Route("/api/auth/logout", "auth", "/auth/logout", public=False),
    Route("/api/me", "auth", "/me", public=False, methods=frozenset({"GET", "PATCH"})),
    Route("/api/me/password", "auth", "/me/password", public=False),
    # Pagamento (REQ05): catálogo público; pedidos e carteira só com JWT
    Route("/api/packages", "payment", "/packages", public=True, methods=frozenset({"GET"})),
    # POST /api/orders cria; /api/orders/{id} (GET) e /{id}/simulate-payment (POST) via prefixo
    Route(
        "/api/orders",
        "payment",
        "/orders",
        public=False,
        methods=frozenset({"GET", "POST"}),
        prefix=True,
        rate_limits=(ORDER_LIMIT,),
        extra_request_headers=frozenset({"idempotency-key"}),
    ),
    Route(
        "/api/credits",
        "payment",
        "/credits",
        public=False,
        methods=frozenset({"GET"}),
        prefix=True,
    ),
)
