"""Testes da Issue [S1-07] (#7): Cadastro de usuário (`POST /auth/register`, RF01)

Na #60 (RF22) o cadastro exige tipo de conta e CPF, e o advogado informa a OAB.
"""

import json
import uuid
from typing import Any

import pytest
from auth_test_data import common_identity, make_cpf
from httpx import AsyncClient
from sqlalchemy import func, select

from auth_service.adapters.clock import FakeClock
from auth_service.adapters.cpf_protector import AesGcmCpfProtector
from auth_service.adapters.password_hasher import Argon2PasswordHasher
from auth_service.adapters.repositories import (
    SqlAlchemyUserRepository,
    SqlAlchemyVerificationCodeRepository,
)
from auth_service.domain.cpf import Cpf
from auth_service.domain.entities import RequestContext
from auth_service.domain.errors import InvalidOabError
from auth_service.domain.password_policy import PasswordPolicy
from auth_service.domain.verification_code import VerificationCodeService
from auth_service.models import OabKind, OabUf, User, UserStatus, UserType
from auth_service.use_cases import RegisterCommand, RegisterUser
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.notifications import InMemoryNotifier

REGISTER = "/auth/register"
PASSWORD = "SenhaForte123"
CPF = "529.982.247-25"
CPF_DIGITS = "52998224725"
OAB = {"number": "012345", "uf": "BA", "kind": "principal"}


def _common(email: str, cpf: str = CPF, **extra: Any) -> dict[str, Any]:
    return {
        "name": "Maria",
        "email": email,
        "password": PASSWORD,
        "user_type": "common",
        "cpf": cpf,
        **extra,
    }


def _lawyer(email: str, cpf: str, oab: dict[str, Any] | None = None) -> dict[str, Any]:
    body = _common(email, cpf, oab=oab or OAB)
    body["user_type"] = "lawyer"
    return body


def _errors(response: Any) -> dict[tuple[str, ...], str]:
    return {tuple(e["loc"][1:]): e["msg"] for e in response.json()["detail"]}


async def _count_users(db: Database) -> int:
    async with db.session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(User)) or 0)


async def test_register_creates_pending_verification_and_triggers_side_effects(
    client: AsyncClient,
    db: Database,
    notifier: InMemoryNotifier,
    audit_logger: InMemoryAuditLogger,
    cpf_protector: AesGcmCpfProtector,
) -> None:
    req_id = str(uuid.uuid4())
    response = await client.post(
        "/auth/register",
        json={
            "name": "  Maria da Silva  ",
            "email": "  Maria.Silva@Example.COM ",
            "password": "SenhaForte123",
            "user_type": "common",
            "cpf": CPF,
        },
        headers={"X-Request-ID": req_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["email"] == "maria.silva@example.com"
    assert body["status"] == "pending_verification"
    assert body["user_type"] == "common"
    assert set(body) == {"id", "email", "status", "user_type"}

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
        assert user.user_type is UserType.COMMON
        # Só a cifra e o índice: o CPF não fica em claro em coluna nenhuma
        assert CPF_DIGITS.encode() not in user.cpf_enc
        assert cpf_protector.decrypt(user.cpf_enc).digits == CPF_DIGITS
        assert user.cpf_hmac == cpf_protector.blind_index(cpf_protector.decrypt(user.cpf_enc))
        assert (user.oab_number, user.oab_uf, user.oab_kind) == (None, None, None)

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
    assert events[0].metadata == {"user_type": "common"}


async def test_register_duplicate_email_returns_409_case_insensitive(
    client: AsyncClient,
) -> None:
    first = await client.post(
        "/auth/register",
        json={
            "name": "João",
            "email": "joao@example.com",
            "password": "SenhaForte123",
            **common_identity("joao@example.com"),
        },
    )
    assert first.status_code == 201

    duplicate = await client.post(
        "/auth/register",
        json={
            "name": "Outro João",
            "email": "JOAO@EXAMPLE.COM",
            "password": "OutraSenha123",
            **common_identity("outro@example.com"),
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "email_already_registered",
        "message": "Este e-mail já está cadastrado.",
        "field": "email",
    }


async def test_register_weak_password_returns_422_with_portuguese_message(
    client: AsyncClient,
) -> None:
    # Menos de 10 caracteres
    short_pw = await client.post(
        "/auth/register",
        json={
            "name": "Ana",
            "email": "ana@example.com",
            "password": "Ab1",
            **common_identity("ana@"),
        },
    )
    assert short_pw.status_code == 422
    assert "pelo menos 10 caracteres" in short_pw.json()["detail"][0]["msg"]

    # Sem número
    no_digit = await client.post(
        "/auth/register",
        json={
            "name": "Ana",
            "email": "ana@example.com",
            "password": "ApenasLetrasLongas",
            **common_identity("ana@"),
        },
    )
    assert no_digit.status_code == 422
    assert "pelo menos 1 número" in no_digit.json()["detail"][0]["msg"]

    # Sem letra
    no_letter = await client.post(
        "/auth/register",
        json={
            "name": "Ana",
            "email": "ana@example.com",
            "password": "12345678901",
            **common_identity("ana@"),
        },
    )
    assert no_letter.status_code == 422
    assert "pelo menos 1 letra" in no_letter.json()["detail"][0]["msg"]


async def test_register_ignores_role_and_unknown_fields(
    client: AsyncClient,
    db: Database,
    audit_logger: InMemoryAuditLogger,
) -> None:
    # `role` não vem do cadastro: quem escolhe é o tipo de conta, e admin não se autodeclara
    res = await client.post(
        REGISTER,
        json=_common("carlos@example.com", role="admin", status="active", oab_number="BA12345"),
    )
    assert res.status_code == 201
    async with db.session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "carlos@example.com"))
        assert user is not None
        assert user.status is UserStatus.PENDING_VERIFICATION
        assert user.oab_number is None
    events = [e for e in audit_logger.events if e.action == "auth.user.registered"]
    assert len(events) == 1
    assert events[0].metadata == {"user_type": "common"}


async def test_register_lawyer_stores_normalized_oab(
    client: AsyncClient,
    db: Database,
    audit_logger: InMemoryAuditLogger,
) -> None:
    res = await client.post(
        REGISTER, json=_lawyer("adv@example.com", make_cpf(11), {**OAB, "uf": "ba"})
    )
    assert res.status_code == 201
    assert res.json()["user_type"] == "lawyer"
    async with db.session_factory() as session:
        user = await session.scalar(select(User).where(User.id == res.json()["id"]))
        assert user is not None
        assert user.user_type is UserType.LAWYER
        assert (user.oab_number, user.oab_uf, user.oab_kind) == (
            "12345",
            OabUf.BA,
            OabKind.PRINCIPAL,
        )
    [event] = [e for e in audit_logger.events if e.action == "auth.user.registered"]
    assert event.metadata == {"user_type": "lawyer"}


async def test_cpf_with_or_without_mask_is_the_same_cpf(client: AsyncClient, db: Database) -> None:
    first = await client.post(REGISTER, json=_common("a@example.com", CPF))
    assert first.status_code == 201

    duplicate = await client.post(REGISTER, json=_common("b@example.com", f" {CPF_DIGITS} "))

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "cpf_already_registered",
        "message": "Este CPF já está cadastrado.",
        "field": "cpf",
    }
    assert CPF_DIGITS not in duplicate.text
    assert await _count_users(db) == 1


async def test_duplicate_oab_returns_409_but_other_uf_is_allowed(
    client: AsyncClient, db: Database
) -> None:
    first = await client.post(REGISTER, json=_lawyer("a@example.com", make_cpf(21)))
    assert first.status_code == 201

    # Zeros à esquerda e outro tipo de inscrição não fazem dela outra inscrição
    same = {"number": "12345", "uf": "BA", "kind": "suplementar"}
    duplicate = await client.post(REGISTER, json=_lawyer("b@example.com", make_cpf(22), same))
    other_uf = await client.post(
        REGISTER, json=_lawyer("c@example.com", make_cpf(23), {**same, "uf": "SP"})
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "oab_already_registered",
        "message": "Esta inscrição na OAB já está cadastrada.",
        "field": "oab",
    }
    assert other_uf.status_code == 201
    assert await _count_users(db) == 2


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"cpf": None}, {("cpf",): "CPF inválido."}),
        ({"cpf": ""}, {("cpf",): "CPF inválido."}),
        ({"cpf": "529.982.247-24"}, {("cpf",): "CPF inválido."}),
        ({"cpf": "111.111.111-11"}, {("cpf",): "CPF inválido."}),
        ({"cpf": 52998224725}, {("cpf",): "CPF inválido."}),
        ({"user_type": None}, {("user_type",): "Escolha o tipo de conta."}),
        ({"user_type": "admin"}, {("user_type",): "Escolha o tipo de conta."}),
        ({"oab": OAB}, {("oab",): "Só advogados informam OAB."}),
        ({"user_type": "lawyer"}, {("oab",): "Informe a inscrição na OAB."}),
        ({"user_type": "lawyer", "oab": "12345/BA"}, {("oab",): "Informe a inscrição na OAB."}),
        (
            {"user_type": "lawyer", "oab": {"number": "1234567", "uf": "XX", "kind": "estagiario"}},
            {
                ("oab", "number"): "Informe o número da OAB com até 6 dígitos.",
                ("oab", "uf"): "Escolha a UF da seccional.",
                ("oab", "kind"): "Escolha o tipo de inscrição.",
            },
        ),
        (
            {"user_type": "lawyer", "oab": {}},
            {
                ("oab", "number"): "Informe o número da OAB com até 6 dígitos.",
                ("oab", "uf"): "Escolha a UF da seccional.",
                ("oab", "kind"): "Escolha o tipo de inscrição.",
            },
        ),
    ],
)
async def test_invalid_identity_returns_422_per_field(
    client: AsyncClient,
    db: Database,
    change: dict[str, Any],
    expected: dict[tuple[str, ...], str],
) -> None:
    payload = {**_common("x@example.com"), **change}
    payload = {k: v for k, v in payload.items() if v is not None or k not in change}

    res = await client.post(REGISTER, json=payload)

    assert res.status_code == 422
    assert _errors(res) == expected
    assert CPF_DIGITS not in res.text and CPF not in res.text
    assert await _count_users(db) == 0


async def test_missing_identity_fields_are_reported_together(client: AsyncClient) -> None:
    res = await client.post(
        REGISTER, json={"name": "Ana", "email": "ana@example.com", "password": PASSWORD}
    )

    assert res.status_code == 422
    assert _errors(res) == {
        ("user_type",): "Escolha o tipo de conta.",
        ("cpf",): "CPF inválido.",
    }


async def test_cpf_never_reaches_audit_or_logs(
    client: AsyncClient,
    audit_logger: InMemoryAuditLogger,
    notifier: InMemoryNotifier,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    await client.post(REGISTER, json=_common("a@example.com"))
    await client.post(REGISTER, json=_common("b@example.com"))
    await client.post(REGISTER, json=_common("c@example.com", "529.982.247-24"))
    await client.post(REGISTER, json=_lawyer("d@example.com", make_cpf(31)))

    trail = json.dumps([e.model_dump(mode="json") for e in audit_logger.events])
    mails = json.dumps([n.data for n in notifier.sent], default=str)
    logs = "\n".join(str(record.msg) for record in caplog.records)
    assert "/auth/register" in logs
    for cpf in (CPF, make_cpf(31)):
        digits = cpf.replace(".", "").replace("-", "")
        for leaked in (cpf, digits):
            assert leaked not in trail
            assert leaked not in logs
            assert leaked not in mails
    assert "52998224724" not in logs and "529.982.247-24" not in logs


async def test_use_case_rejects_oab_mismatch_even_without_the_schema(
    db: Database,
    audit_logger: InMemoryAuditLogger,
    notifier: InMemoryNotifier,
    cpf_protector: AesGcmCpfProtector,
) -> None:
    # O schema já barra, mas a regra é do domínio e vale para qualquer outra entrada
    async with db.session_factory() as session:
        use_case = RegisterUser(
            users=SqlAlchemyUserRepository(session),
            codes=SqlAlchemyVerificationCodeRepository(session),
            hasher=Argon2PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1),
            code_service=VerificationCodeService("pepper-de-teste-0123456789"),
            password_policy=PasswordPolicy(),
            notifier=notifier,
            audit=audit_logger,
            clock=FakeClock(),
            cpf_protector=cpf_protector,
        )
        command = RegisterCommand(
            name="Ana",
            email="ana@example.com",
            password=PASSWORD,
            user_type=UserType.LAWYER,
            cpf=Cpf.parse(CPF),
        )
        with pytest.raises(InvalidOabError) as exc:
            await use_case.execute(command, RequestContext())

    assert exc.value.message == "Informe a inscrição na OAB."
    assert await _count_users(db) == 0
