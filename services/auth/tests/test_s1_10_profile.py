"""Testes da Issue [S1-10] (#10): Perfil e senha (`GET /me`, `PATCH /me`, `POST /me/password`)."""

from httpx import AsyncClient

from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.notifications import InMemoryNotifier

TEST_INTERNAL_TOKEN = "test-internal-token"


def gateway_headers(user_id: int, email: str = "perfil@example.com") -> dict[str, str]:
    return {
        "X-Internal-Token": TEST_INTERNAL_TOKEN,
        "X-User-Id": str(user_id),
        "X-User-Email": email,
    }


async def _setup_active_user(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    *,
    email: str = "perfil@example.com",
    password: str = "SenhaForte123",
) -> int:
    reg = await client.post(
        "/auth/register",
        json={"name": "Nome Inicial", "email": email, "password": password},
    )
    assert reg.status_code == 201
    user_id: int = reg.json()["id"]
    code = notifier.find_by_template("email_verification")[-1].data["code"]
    await client.post("/auth/verify-email", json={"email": email, "code": code})
    return user_id


async def test_me_requires_gateway_headers_and_returns_profile(
    client: AsyncClient,
    notifier: InMemoryNotifier,
) -> None:
    user_id = await _setup_active_user(client, notifier)

    # Sem X-Internal-Token / X-User-Id -> 401
    unauth = await client.get("/me")
    assert unauth.status_code == 401

    # Usuário inexistente -> 404
    not_found = await client.get("/me", headers=gateway_headers(99999))
    assert not_found.status_code == 404

    # Autenticado via headers do Gateway -> 200
    res = await client.get("/me", headers=gateway_headers(user_id))
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == user_id
    assert body["name"] == "Nome Inicial"
    assert body["email"] == "perfil@example.com"
    assert body["status"] == "active"
    assert body["email_verified_at"] is not None
    assert body["created_at"] is not None


async def test_patch_me_updates_name_ignores_mass_assignment_and_audits_fields(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    audit_logger: InMemoryAuditLogger,
) -> None:
    user_id = await _setup_active_user(client, notifier, email="patch@example.com")

    res = await client.patch(
        "/me",
        headers=gateway_headers(user_id),
        json={
            "name": "  Novo Nome Atualizado  ",
            "email": "atacante@example.com",
            "status": "blocked",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Novo Nome Atualizado"
    # Campos sensíveis ignorados (proteção contra mass assignment — #10)
    assert body["email"] == "patch@example.com"
    assert body["status"] == "active"

    events = audit_logger.find("auth.profile.updated")
    assert len(events) == 1
    assert events[0].actor_id == user_id
    assert events[0].metadata == {"fields": ["name"]}


async def test_change_password_validates_current_enforces_policy_and_revokes_other_sessions(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    audit_logger: InMemoryAuditLogger,
) -> None:
    user_id = await _setup_active_user(client, notifier, email="senha@example.com")

    # Cria duas sessões ativas (dispositivo A = sessão atual; dispositivo B = outra sessão)
    login_a = await client.post(
        "/auth/login",
        json={"email": "senha@example.com", "password": "SenhaForte123"},
    )
    login_b = await client.post(
        "/auth/login",
        json={"email": "senha@example.com", "password": "SenhaForte123"},
    )
    refresh_a = login_a.json()["refresh_token"]
    refresh_b = login_b.json()["refresh_token"]

    # Senha atual incorreta -> 400
    wrong_current = await client.post(
        "/me/password",
        headers=gateway_headers(user_id),
        json={
            "current_password": "SenhaIncorreta999",
            "new_password": "NovaSenhaValida456",
        },
    )
    assert wrong_current.status_code == 400
    assert wrong_current.json()["detail"]["code"] == "invalid_current_password"

    # Nova senha fraca -> 422
    weak_new = await client.post(
        "/me/password",
        headers=gateway_headers(user_id),
        json={
            "current_password": "SenhaForte123",
            "new_password": "curta",
        },
    )
    assert weak_new.status_code == 422

    # Alteração válida preservando a sessão atual (refresh_a) e revogando refresh_b -> 204
    changed = await client.post(
        "/me/password",
        headers=gateway_headers(user_id),
        json={
            "current_password": "SenhaForte123",
            "new_password": "NovaSenhaValida456",
            "refresh_token": refresh_a,
        },
    )
    assert changed.status_code == 204
    assert len(audit_logger.find("auth.password.changed")) == 1

    # Outra sessão (refresh_b) foi revogada
    refresh_b_res = await client.post("/auth/refresh", json={"refresh_token": refresh_b})
    assert refresh_b_res.status_code == 401

    # Sessão atual (refresh_a) continua ativa
    refresh_a_res = await client.post("/auth/refresh", json={"refresh_token": refresh_a})
    assert refresh_a_res.status_code == 200

    # Login com a nova senha funciona
    new_login = await client.post(
        "/auth/login",
        json={"email": "senha@example.com", "password": "NovaSenhaValida456"},
    )
    assert new_login.status_code == 200
