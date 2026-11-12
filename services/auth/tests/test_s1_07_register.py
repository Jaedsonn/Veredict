"""Testes da Issue [S1-07] (#7): Cadastro de usuário (`POST /auth/register`, RF01)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from auth_service.models import User, UserStatus
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import InMemoryNotifier


async def test_health_and_legacy_users_endpoints_removed(client: AsyncClient) -> None:
    health_live = await client.get("/health/live")
    assert health_live.status_code == 200
    assert health_live.json() == {"status": "ok"}

    health_ready = await client.get("/health/ready")
    assert health_ready.status_code == 200
    assert health_ready.json() == {"status": "ok", "database": "up"}

    # Endpoints de exemplo `POST /users` e `GET /users/{id}` foram removidos (#7)
    legacy_post = await client.post("/users", json={"email": "a@b.com", "name": "A"})
    assert legacy_post.status_code == 404
    legacy_get = await client.get("/users/1")
    assert legacy_get.status_code == 404


async def test_register_creates_pending_verification_and_triggers_side_effects(
    client: AsyncClient,
    db: Database,
    notifier: InMemoryNotifier,
    audit_logger: InMemoryAuditLogger,
) -> None:
    req_id = str(uuid.uuid4())
    response = await client.post(
        "/auth/register",
        json={
            "name": "  Maria da Silva  ",
            "email": "  Maria.Silva@Example.COM ",
            "password": "SenhaForte123",
        },
        headers={"X-Request-ID": req_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["email"] == "maria.silva@example.com"
    assert body["status"] == "pending_verification"

    # Verifica persistência com Argon2id e status pending_verification
    async with db.session_factory() as session:
        user = await session.scalar(select(User).where(User.id == body["id"]))
        assert user is not None
        assert user.name == "Maria da Silva"
        assert user.email == "maria.silva@example.com"
        assert user.status == UserStatus.PENDING_VERIFICATION
        assert user.password_hash.startswith("$argon2id$")
        assert "SenhaForte123" not in user.password_hash
        assert user.email_verified_at is None

    # Disparo de notificação `email_verification` com código de 6 dígitos
    sent = [n for n in notifier.sent if n.template == "email_verification"]
    assert len(sent) == 1
    assert sent[0].to == "maria.silva@example.com"
    code = sent[0].data["code"]
    assert isinstance(code, str) and len(code) == 6 and code.isdigit()

    # Evento de auditoria `auth.user.registered` sem senha ou código em texto puro
    events = [e for e in audit_logger.events if e.action == "auth.user.registered"]
    assert len(events) == 1
    assert events[0].actor_id == body["id"]
    assert str(events[0].request_id) == req_id
    assert events[0].metadata == {}


async def test_register_duplicate_email_returns_409_case_insensitive(
    client: AsyncClient,
) -> None:
    first = await client.post(
        "/auth/register",
        json={
            "name": "João",
            "email": "joao@example.com",
            "password": "SenhaForte123",
        },
    )
    assert first.status_code == 201

    duplicate = await client.post(
        "/auth/register",
        json={
            "name": "Outro João",
            "email": "JOAO@EXAMPLE.COM",
            "password": "OutraSenha123",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "email_already_registered"


async def test_register_weak_password_returns_422_with_portuguese_message(
    client: AsyncClient,
) -> None:
    # Menos de 10 caracteres
    short_pw = await client.post(
        "/auth/register",
        json={"name": "Ana", "email": "ana@example.com", "password": "Ab1"},
    )
    assert short_pw.status_code == 422
    assert "pelo menos 10 caracteres" in short_pw.json()["detail"][0]["msg"]

    # Sem número
    no_digit = await client.post(
        "/auth/register",
        json={"name": "Ana", "email": "ana@example.com", "password": "ApenasLetrasLongas"},
    )
    assert no_digit.status_code == 422
    assert "pelo menos 1 número" in no_digit.json()["detail"][0]["msg"]

    # Sem letra
    no_letter = await client.post(
        "/auth/register",
        json={"name": "Ana", "email": "ana@example.com", "password": "12345678901"},
    )
    assert no_letter.status_code == 422
    assert "pelo menos 1 letra" in no_letter.json()["detail"][0]["msg"]


async def test_register_ignores_unpersisted_extra_fields(
    client: AsyncClient,
    audit_logger: InMemoryAuditLogger,
) -> None:
    # Campos extras não persistidos no schema de `users` (§5.1) são ignorados
    res = await client.post(
        "/auth/register",
        json={
            "name": "Dr. Carlos",
            "email": "carlos@example.com",
            "password": "SenhaForte123",
            "role": "lawyer",
            "cpf": "123.456.789-09",
            "oab_number": "BA12345",
        },
    )
    assert res.status_code == 201
    events = [e for e in audit_logger.events if e.action == "auth.user.registered"]
    assert len(events) == 1
    assert "role" not in events[0].metadata
