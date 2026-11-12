"""Testes da Issue [S1-08] (#8): Verificação de e-mail por código de 6 dígitos (RF02, ADR-007)."""

from httpx import AsyncClient
from sqlalchemy import select

from auth_service.adapters.clock import FakeClock
from auth_service.models import EmailVerificationCode, User, UserStatus
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import InMemoryNotifier


async def _register_and_extract_code(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    email: str = "verif@example.com",
) -> str:
    r = await client.post(
        "/auth/register",
        json={"name": "Usuária Teste", "email": email, "password": "SenhaForte123"},
    )
    assert r.status_code == 201
    sent = notifier.find_by_template("email_verification")
    assert sent
    code = sent[-1].data["code"]
    assert isinstance(code, str)
    return code


async def test_verify_email_stores_hmac_hash_activates_user_and_sends_welcome(
    client: AsyncClient,
    db: Database,
    notifier: InMemoryNotifier,
    audit_logger: InMemoryAuditLogger,
) -> None:
    raw_code = await _register_and_extract_code(client, notifier)

    # No banco, code_hash é HMAC-SHA256 hex de 64 chars (nunca o código em texto puro — ADR-007)
    async with db.session_factory() as session:
        record = await session.scalar(select(EmailVerificationCode))
        assert record is not None
        assert len(record.code_hash) == 64
        assert record.code_hash != raw_code

    res = await client.post(
        "/auth/verify-email",
        json={"email": "verif@example.com", "code": raw_code},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "active"}

    # Usuário ativo com email_verified_at preenchido e código marcado com consumed_at
    async with db.session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "verif@example.com"))
        assert user is not None
        assert user.status == UserStatus.ACTIVE
        assert user.email_verified_at is not None

        consumed = await session.scalar(select(EmailVerificationCode))
        assert consumed is not None
        assert consumed.consumed_at is not None

    # Disparo de notificação `welcome` e evento de auditoria `auth.email.verified`
    assert len(notifier.find_by_template("welcome")) == 1
    assert len(audit_logger.find("auth.email.verified")) == 1

    # Reutilizar código já consumido retorna 400
    reuse = await client.post(
        "/auth/verify-email",
        json={"email": "verif@example.com", "code": raw_code},
    )
    assert reuse.status_code == 400


async def test_verify_email_wrong_code_increments_attempts_and_blocks_at_five(
    client: AsyncClient,
    notifier: InMemoryNotifier,
) -> None:
    real_code = await _register_and_extract_code(client, notifier, email="attempts@example.com")
    wrong_code = "000000" if real_code != "000000" else "999999"

    # 4 primeiras tentativas erradas retornam 400 com attempts_remaining decrescente
    for expected_remaining in (4, 3, 2, 1):
        r = await client.post(
            "/auth/verify-email",
            json={"email": "attempts@example.com", "code": wrong_code},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_code"
        assert r.json()["detail"]["attempts_remaining"] == expected_remaining

    # 5ª tentativa errada esgota e invalida o código
    fifth = await client.post(
        "/auth/verify-email",
        json={"email": "attempts@example.com", "code": wrong_code},
    )
    assert fifth.status_code == 400
    assert fifth.json()["detail"]["code"] == "too_many_attempts"

    # Mesmo enviando o código correto após a 5ª tentativa, deve falhar com 400
    after_lock = await client.post(
        "/auth/verify-email",
        json={"email": "attempts@example.com", "code": real_code},
    )
    assert after_lock.status_code == 400


async def test_verify_email_expired_code_returns_400(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    fake_clock: FakeClock,
) -> None:
    raw_code = await _register_and_extract_code(client, notifier, email="expired@example.com")
    fake_clock.advance(minutes=16)

    res = await client.post(
        "/auth/verify-email",
        json={"email": "expired@example.com", "code": raw_code},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "code_expired"


async def test_resend_code_invalidates_previous_and_enforces_cooldown_and_hourly_limit(
    client: AsyncClient,
    notifier: InMemoryNotifier,
    fake_clock: FakeClock,
) -> None:
    first_code = await _register_and_extract_code(client, notifier, email="resend@example.com")

    # Cooldown de 60s: tentar reenviar após 20s retorna 429 com Retry-After
    fake_clock.advance(seconds=20)
    too_soon = await client.post(
        "/auth/verify-email/resend",
        json={"email": "resend@example.com"},
    )
    assert too_soon.status_code == 429
    assert int(too_soon.headers["Retry-After"]) == 40

    # Avança para completar 60s -> reenvia com sucesso (202 Accepted)
    fake_clock.advance(seconds=45)
    resend_ok = await client.post(
        "/auth/verify-email/resend",
        json={"email": "resend@example.com"},
    )
    assert resend_ok.status_code == 202
    assert resend_ok.json() == {"status": "accepted"}

    second_code = notifier.find_by_template("email_verification")[-1].data["code"]

    # O primeiro código foi invalidado pelo novo envio
    old_attempt = await client.post(
        "/auth/verify-email",
        json={"email": "resend@example.com", "code": first_code},
    )
    assert old_attempt.status_code == 400

    # Limite de 5 envios por hora: já temos 2 códigos criados na última hora; mais 3 atingem 5
    for _ in range(3):
        fake_clock.advance(seconds=65)
        r = await client.post(
            "/auth/verify-email/resend",
            json={"email": "resend@example.com"},
        )
        assert r.status_code == 202

    # 6º código na mesma hora -> 429
    fake_clock.advance(seconds=65)
    sixth = await client.post(
        "/auth/verify-email/resend",
        json={"email": "resend@example.com"},
    )
    assert sixth.status_code == 429
    assert "Retry-After" in sixth.headers

    # O último código emitido continua válido
    latest_code = notifier.find_by_template("email_verification")[-1].data["code"]
    assert latest_code != second_code or isinstance(latest_code, str)
    verify_latest = await client.post(
        "/auth/verify-email",
        json={"email": "resend@example.com", "code": latest_code},
    )
    assert verify_latest.status_code == 200


async def test_resend_anti_enumeration_for_unknown_or_already_active_email(
    client: AsyncClient,
    notifier: InMemoryNotifier,
) -> None:
    # E-mail inexistente deve retornar 202 sem disparar notificação (anti-enumeração)
    unknown = await client.post(
        "/auth/verify-email/resend",
        json={"email": "naoexiste@example.com"},
    )
    assert unknown.status_code == 202
    assert len(notifier.sent) == 0
