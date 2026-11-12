"""Testes da Issue [S1-09] (#9): Login, JWT RS256, rotação de refresh token e logout (RF03)."""

from httpx import AsyncClient

from auth_service.adapters.clock import FakeClock
from auth_service.adapters.token_issuer import PyJwtTokenIssuer
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.notifications import InMemoryNotifier


async def _create_verified_user(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    *,
    email: str = "login@example.com",
    password: str = "SenhaForte123",
) -> int:
    reg = await client.post(
        "/auth/register",
        json={"name": "Usuário Ativo", "email": email, "password": password},
    )
    assert reg.status_code == 201
    user_id: int = reg.json()["id"]
    code = notifier.find_by_template("email_verification")[-1].data["code"]
    ver = await client.post("/auth/verify-email", json={"email": email, "code": code})
    assert ver.status_code == 200
    return user_id


async def test_login_pending_verification_returns_403_email_not_verified(
    client: AsyncClient,
) -> None:
    await client.post(
        "/auth/register",
        json={
            "name": "Pendente",
            "email": "pendente@example.com",
            "password": "SenhaForte123",
        },
    )
    res = await client.post(
        "/auth/login",
        json={"email": "pendente@example.com", "password": "SenhaForte123"},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "email_not_verified"


async def test_login_wrong_password_or_unknown_email_returns_401_and_audits_without_password(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    audit_logger: InMemoryAuditLogger,
) -> None:
    await _create_verified_user(client, notifier, email="user@example.com")

    wrong_pw = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "SenhaErrada999"},
    )
    assert wrong_pw.status_code == 401

    unknown_email = await client.post(
        "/auth/login",
        json={"email": "desconhecido@example.com", "password": "SenhaErrada999"},
    )
    assert unknown_email.status_code == 401
    # Mesma mensagem para não enumerar e-mails
    assert wrong_pw.json()["detail"] == unknown_email.json()["detail"]

    failures = audit_logger.find("auth.session.login_failed")
    assert len(failures) == 2
    assert failures[0].metadata is not None
    assert failures[1].metadata is not None
    assert failures[0].metadata["reason"] == "invalid_password"
    assert failures[1].metadata["reason"] == "user_not_found"
    for event in failures:
        assert "SenhaErrada999" not in str(event.metadata)


async def test_login_issues_valid_rs256_jwt_and_refresh_token_rotation_with_reuse_detection(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    token_issuer: PyJwtTokenIssuer,
    audit_logger: InMemoryAuditLogger,
    fake_clock: FakeClock,
) -> None:
    user_id = await _create_verified_user(client, notifier, email="sessao@example.com")

    login_res = await client.post(
        "/auth/login",
        json={"email": "sessao@example.com", "password": "SenhaForte123"},
    )
    assert login_res.status_code == 200
    tokens_1 = login_res.json()
    assert tokens_1["expires_in"] == 900
    assert len(audit_logger.find("auth.session.login_succeeded")) == 1

    # Valida assinatura RS256 e claims obrigatórios do Access Token (#9)
    claims = token_issuer.decode_access_token(tokens_1["access_token"])
    assert claims["sub"] == str(user_id)
    assert claims["email"] == "sessao@example.com"
    assert claims["iss"] == "veriditi-auth"
    assert claims["aud"] == "veriditi"
    assert "jti" in claims
    assert claims["exp"] - claims["iat"] == 900

    # Rotação de refresh token: POST /auth/refresh emite novo par e invalida o anterior
    fake_clock.advance(minutes=5)
    refresh_res = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens_1["refresh_token"]},
    )
    assert refresh_res.status_code == 200
    tokens_2 = refresh_res.json()
    assert tokens_2["refresh_token"] != tokens_1["refresh_token"]

    # Reuso do refresh_token antigo (rotacionado) revoga toda a família do usuário e retorna 401
    reuse_res = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens_1["refresh_token"]},
    )
    assert reuse_res.status_code == 401
    assert reuse_res.json()["detail"]["code"] == "refresh_reuse_detected"
    assert len(audit_logger.find("auth.session.refresh_reuse_detected")) == 1

    # Todos os tokens do usuário foram revogados por segurança; tokens_2 também não funciona mais
    compromised_res = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens_2["refresh_token"]},
    )
    assert compromised_res.status_code == 401


async def test_logout_revokes_refresh_token_and_emits_audit_event(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    audit_logger: InMemoryAuditLogger,
) -> None:
    await _create_verified_user(client, notifier, email="logout@example.com")
    login_res = await client.post(
        "/auth/login",
        json={"email": "logout@example.com", "password": "SenhaForte123"},
    )
    refresh_token = login_res.json()["refresh_token"]

    logout_res = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_res.status_code == 204
    assert len(audit_logger.find("auth.session.logout")) == 1

    # Refresh token revogado no logout não pode mais renovar sessão
    after_logout = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert after_logout.status_code == 401
