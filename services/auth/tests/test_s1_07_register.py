"""Testes da Issue [S1-07] (#7): Cadastro de usuário (`POST /auth/register`, RF01, REQ 01)."""

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


async def test_register_common_user_creates_pending_verification_and_triggers_side_effects(
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
        headers={"X-Request-Id": req_id},
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
    sent = notifier.find_by_template("email_verification")
    assert len(sent) == 1
    assert sent[0].to == "maria.silva@example.com"
    code = sent[0].data["code"]
    assert isinstance(code, str) and len(code) == 6 and code.isdigit()

    # Evento de auditoria `auth.user.registered` sem senha ou código em texto puro
    events = audit_logger.find("auth.user.registered")
    assert len(events) == 1
    assert events[0].actor_id == body["id"]
    assert str(events[0].request_id) == req_id
    assert events[0].metadata == {"role": "common"}


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


async def test_register_lawyer_and_profile_type_validation_req01_d1(
    client: AsyncClient,
) -> None:
    # Advogado sem OAB deve falhar com 422
    lawyer_no_oab = await client.post(
        "/auth/register",
        json={
            "name": "Dr. Carlos",
            "email": "carlos@example.com",
            "password": "SenhaForte123",
            "role": "lawyer",
        },
    )
    assert lawyer_no_oab.status_code == 422
    assert "OAB" in lawyer_no_oab.json()["detail"][0]["msg"]

    # Advogado com OAB e CPF válido (dígitos verificadores módulo 11) deve cadastrar com 201
    lawyer_ok = await client.post(
        "/auth/register",
        json={
            "name": "Dr. Carlos",
            "email": "carlos@example.com",
            "password": "SenhaForte123",
            "role": "lawyer",
            "cpf": "123.456.789-09",
            "oab_number": "ba 12345",
        },
    )
    assert lawyer_ok.status_code == 201

    # Perfil 'company' (Empresa) fora de escopo na v1 (Decisão D1 / Apêndice A) -> 422
    company_rejected = await client.post(
        "/auth/register",
        json={
            "name": "Empresa X",
            "email": "contato@empresax.com",
            "password": "SenhaForte123",
            "role": "company",
        },
    )
    assert company_rejected.status_code == 422
