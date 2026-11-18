"""Testes da Issue [S2-02] (#19): recuperação de senha por link (`/auth/password/*`)"""

import hashlib
import json
import re

import pytest
from auth_test_data import common_identity
from httpx import AsyncClient
from sqlalchemy import select, update

from auth_service.adapters.clock import FakeClock
from auth_service.domain.reset_token import ResetTokenService
from auth_service.models import PasswordResetToken, RefreshToken, RevokeReason, User, UserStatus
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.logging import is_sensitive_key
from veriditi_common.notifications import InMemoryNotifier

EMAIL = "reset@example.com"
OLD_PASSWORD = "SenhaAntiga123"
NEW_PASSWORD = "SenhaNovinha456"
FORGOT = "/auth/password/forgot"
RESET = "/auth/password/reset"
INVALID = {
    "detail": {
        "code": "invalid_reset_token",
        "message": "Link inválido ou expirado. Solicite um novo.",
    }
}


async def _register(client: AsyncClient, notifier: InMemoryNotifier, email: str = EMAIL) -> int:
    reg = await client.post(
        "/auth/register",
        json={
            "name": "Ana Reset",
            "email": email,
            "password": OLD_PASSWORD,
            **common_identity(email),
        },
    )
    assert reg.status_code == 201
    user_id: int = reg.json()["id"]
    return user_id


async def _active_user(client: AsyncClient, notifier: InMemoryNotifier, email: str = EMAIL) -> int:
    user_id = await _register(client, notifier, email)
    code = [n for n in notifier.sent if n.template == "email_verification"][-1].data["code"]
    verified = await client.post("/auth/verify-email", json={"email": email, "code": code})
    assert verified.status_code == 200
    return user_id


async def _login(client: AsyncClient, password: str, email: str = EMAIL) -> int:
    return (
        await client.post("/auth/login", json={"email": email, "password": password})
    ).status_code


async def _forgot(client: AsyncClient, notifier: InMemoryNotifier, email: str = EMAIL) -> str:
    resp = await client.post(FORGOT, json={"email": email})
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    token = notifier.sent[-1].data["token"]
    assert isinstance(token, str)
    return token


def _reset_mails(notifier: InMemoryNotifier) -> list[str]:
    return [n.template for n in notifier.sent if n.template.startswith("password_")]


def _events(audit: InMemoryAuditLogger, action: str) -> list[dict[str, object]]:
    return [e.model_dump(mode="json") for e in audit.events if e.action == action]


async def _reset_rows(db: Database) -> list[PasswordResetToken]:
    async with db.session_factory() as session:
        return list(
            await session.scalars(select(PasswordResetToken).order_by(PasswordResetToken.id))
        )


# Domínio


def test_token_service_generates_43_urlsafe_chars_and_stores_only_sha256() -> None:
    service = ResetTokenService(ttl_minutes=30)

    token, token_hash = service.generate()

    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    assert token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert service.is_well_formed(token)
    assert service.generate()[0] != token


@pytest.mark.parametrize(
    "token", ["", "a" * 42, "a" * 44, "a" * 42 + "=", "a" * 42 + "/", "á" * 43]
)
def test_token_service_rejects_malformed(token: str) -> None:
    assert not ResetTokenService().is_well_formed(token)


def test_token_service_requires_positive_ttl() -> None:
    with pytest.raises(ValueError, match="PASSWORD_RESET_TTL_MINUTES"):
        ResetTokenService(ttl_minutes=0)


def test_payload_keys_are_redacted_by_the_common_lib() -> None:
    assert is_sensitive_key("token")
    assert is_sensitive_key("new_password")


# POST /auth/password/forgot


async def test_forgot_for_active_account_emails_a_link_and_stores_only_the_hash(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    audit: InMemoryAuditLogger,
    db: Database,
    fake_clock: FakeClock,
) -> None:
    user_id = await _active_user(client, notifier)

    token = await _forgot(client, notifier, "  RESET@Example.com ")

    mail = notifier.sent[-1]
    assert mail.template == "password_reset"
    assert mail.to == EMAIL
    assert mail.data == {"name": "Ana Reset", "token": token, "expires_in_minutes": 30}
    [row] = await _reset_rows(db)
    assert mail.idempotency_key == f"password_reset:{row.id}"
    assert row.user_id == user_id
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert row.created_at == fake_clock.now()
    assert (row.expires_at - row.created_at).total_seconds() == 30 * 60
    assert row.requested_ip is not None
    assert row.consumed_at is None
    [event] = _events(audit, "auth.password.reset_requested")
    assert (event["outcome"], event["actor_id"]) == ("success", user_id)
    assert token not in json.dumps(event)


@pytest.mark.parametrize("case", ["unknown", "pending", "blocked"])
async def test_forgot_without_active_account_is_202_without_effect(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    audit: InMemoryAuditLogger,
    db: Database,
    case: str,
) -> None:
    email = f"{case}@example.com"
    if case != "unknown":
        user_id = await _register(client, notifier, email)
    if case == "blocked":
        async with db.session_factory() as session:
            await session.execute(
                update(User).where(User.id == user_id).values(status=UserStatus.BLOCKED)
            )
            await session.commit()

    resp = await client.post(FORGOT, json={"email": email})

    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    assert _reset_mails(notifier) == []
    assert await _reset_rows(db) == []
    [event] = _events(audit, "auth.password.reset_requested")
    expected = "user_not_found" if case == "unknown" else "account_not_active"
    assert (event["outcome"], event["metadata"]) == ("failure", {"reason": expected})
    assert email not in json.dumps(event)


async def test_forgot_with_malformed_email_is_422(client: AsyncClient) -> None:
    resp = await client.post(FORGOT, json={"email": "nao-e-email"})

    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "email"]


async def test_new_request_replaces_the_previous_link(
    client: AsyncClient, notifier: InMemoryNotifier, audit: InMemoryAuditLogger, db: Database
) -> None:
    await _active_user(client, notifier)
    first = await _forgot(client, notifier)
    second = await _forgot(client, notifier)

    replaced = await client.post(RESET, json={"token": first, "new_password": NEW_PASSWORD})

    assert replaced.status_code == 400
    assert replaced.json() == INVALID
    old_row, new_row = await _reset_rows(db)
    assert old_row.consumed_at is not None
    assert new_row.consumed_at is None
    assert _events(audit, "auth.password.reset_failed")[-1]["metadata"] == {"reason": "consumed"}
    ok = await client.post(RESET, json={"token": second, "new_password": NEW_PASSWORD})
    assert ok.status_code == 204


# POST /auth/password/reset


async def test_reset_swaps_password_revokes_every_session_and_notifies(
    client: AsyncClient, notifier: InMemoryNotifier, audit: InMemoryAuditLogger, db: Database
) -> None:
    user_id = await _active_user(client, notifier)
    sessions = [
        (await client.post("/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD})).json()
        for _ in range(2)
    ]
    token = await _forgot(client, notifier)

    resp = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

    assert resp.status_code == 204
    assert resp.content == b""
    async with db.session_factory() as session:
        refresh = list(await session.scalars(select(RefreshToken)))
    assert len(refresh) == 2
    assert {r.revoke_reason for r in refresh} == {RevokeReason.PASSWORD_RESET}
    for pair in sessions:
        again = await client.post("/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert again.status_code == 401
        assert again.json()["detail"]["code"] == "invalid_refresh"
    # Sessão encerrada pelo reset não é tratada como roubo de token
    assert _events(audit, "auth.session.refresh_reuse_detected") == []
    assert await _login(client, OLD_PASSWORD) == 401
    assert await _login(client, NEW_PASSWORD) == 200

    [row] = await _reset_rows(db)
    assert row.consumed_at is not None
    assert _reset_mails(notifier) == ["password_reset", "password_changed"]
    changed = next(n for n in notifier.sent if n.template == "password_changed")
    assert (changed.to, changed.data) == (EMAIL, {"name": "Ana Reset"})
    assert changed.idempotency_key == f"password_changed:{row.id}"
    [event] = _events(audit, "auth.password.reset_completed")
    assert (event["outcome"], event["actor_id"]) == ("success", user_id)
    assert event["metadata"] == {"revoked_sessions": 2}


async def test_reused_token_is_rejected(
    client: AsyncClient, notifier: InMemoryNotifier, audit: InMemoryAuditLogger
) -> None:
    user_id = await _active_user(client, notifier)
    token = await _forgot(client, notifier)
    assert (
        await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
    ).status_code == 204

    again = await client.post(RESET, json={"token": token, "new_password": "OutraSenha789"})

    assert again.status_code == 400
    assert again.json() == INVALID
    [event] = _events(audit, "auth.password.reset_failed")
    assert (event["actor_id"], event["metadata"]) == (user_id, {"reason": "consumed"})
    assert await _login(client, NEW_PASSWORD) == 200


async def test_expired_token_is_rejected(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    audit: InMemoryAuditLogger,
    fake_clock: FakeClock,
) -> None:
    await _active_user(client, notifier)
    token = await _forgot(client, notifier)
    fake_clock.advance(minutes=30)

    resp = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

    assert resp.status_code == 400
    assert resp.json() == INVALID
    assert _events(audit, "auth.password.reset_failed")[-1]["metadata"] == {"reason": "expired"}
    assert await _login(client, OLD_PASSWORD) == 200


async def test_token_is_still_valid_just_before_expiry(
    client: AsyncClient, notifier: InMemoryNotifier, fake_clock: FakeClock
) -> None:
    await _active_user(client, notifier)
    token = await _forgot(client, notifier)
    fake_clock.advance(minutes=29, seconds=59)

    resp = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

    assert resp.status_code == 204


@pytest.mark.parametrize(
    ("token", "reason"),
    [
        ("curto", "malformed"),
        ("", "malformed"),
        ("a" * 42 + "!", "malformed"),
        ("A" * 43, "not_found"),
    ],
    ids=["short", "empty", "bad-char", "unknown"],
)
async def test_invalid_token_is_rejected_with_the_same_400(
    client: AsyncClient, audit: InMemoryAuditLogger, token: str, reason: str
) -> None:
    resp = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

    assert resp.status_code == 400
    assert resp.json() == INVALID
    [event] = _events(audit, "auth.password.reset_failed")
    assert (event["outcome"], event["actor_id"]) == ("failure", None)
    assert event["metadata"] == {"reason": reason}


async def test_weak_password_is_422_and_does_not_burn_the_link(
    client: AsyncClient, notifier: InMemoryNotifier, db: Database
) -> None:
    await _active_user(client, notifier)
    token = await _forgot(client, notifier)

    weak = await client.post(RESET, json={"token": token, "new_password": "curta"})

    assert weak.status_code == 422
    assert weak.json() == {
        "detail": [
            {
                "loc": ["body", "new_password"],
                "msg": "A senha deve ter pelo menos 10 caracteres.",
                "type": "value_error",
            }
        ]
    }
    [row] = await _reset_rows(db)
    assert row.consumed_at is None
    ok = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
    assert ok.status_code == 204


async def test_missing_fields_are_422_without_echoing_input(client: AsyncClient) -> None:
    resp = await client.post(RESET, json={"token": "x" * 43})

    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "new_password"]
    assert "x" * 43 not in resp.text


async def test_account_blocked_after_the_request_cannot_reset(
    client: AsyncClient, notifier: InMemoryNotifier, audit: InMemoryAuditLogger, db: Database
) -> None:
    user_id = await _active_user(client, notifier)
    token = await _forgot(client, notifier)
    async with db.session_factory() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(status=UserStatus.BLOCKED)
        )
        await session.commit()

    resp = await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

    assert resp.status_code == 400
    assert resp.json() == INVALID
    [row] = await _reset_rows(db)
    assert row.consumed_at is None
    [event] = _events(audit, "auth.password.reset_failed")
    assert event["metadata"] == {"reason": "account_not_active"}
    assert "password_changed" not in _reset_mails(notifier)


async def test_token_and_email_never_reach_audit_or_logs(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    audit: InMemoryAuditLogger,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    await _active_user(client, notifier)
    token = await _forgot(client, notifier)
    await client.post(RESET, json={"token": token, "new_password": "curta"})
    await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
    await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
    await client.post(FORGOT, json={"email": "ninguem@example.com"})

    reset_events = [e for e in audit.events if e.action.startswith("auth.password.reset_")]
    assert {e.action for e in reset_events} == {
        "auth.password.reset_requested",
        "auth.password.reset_completed",
        "auth.password.reset_failed",
    }
    trail = json.dumps([e.model_dump(mode="json") for e in reset_events])
    # Registros já passaram pelo redact_sensitive da lib
    logs = "\n".join(str(record.msg) for record in caplog.records)
    assert "/auth/password/reset" in logs
    for secret in (token, hashlib.sha256(token.encode()).hexdigest(), NEW_PASSWORD):
        assert secret not in trail
        assert secret not in logs
    for email in (EMAIL, "ninguem@example.com"):
        assert email not in trail
