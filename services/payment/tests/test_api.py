"""REQ05 de ponta a ponta no serviço: pacote → faturamento → PIX → confirmação → saldo"""

import uuid
from collections.abc import Callable
from typing import Any

from httpx import AsyncClient

from payment_service.adapters.sandbox_provider import crc16_ccitt
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.security import INTERNAL_TOKEN_HEADER

TOKEN = "test-internal-token-0123456789"
# Tipos das fixtures do conftest (que não é importável no modo importlib do pytest)
UserHeaders = Callable[..., dict[str, str]]
FakeClock = Any
FlakyProvider = Any


async def _order(
    client: AsyncClient,
    headers: dict[str, str],
    billing: dict[str, Any],
    *,
    package: str = "basico",
    key: str = "key-00000001",
) -> Any:
    return await client.post(
        "/orders",
        json={"package_code": package, "billing": billing},
        headers={**headers, "Idempotency-Key": key},
    )


# Catálogo (RF07, D2)


async def test_packages_follow_d2_ordered_by_price(client: AsyncClient) -> None:
    res = await client.get("/packages", headers={INTERNAL_TOKEN_HEADER: TOKEN})
    assert res.status_code == 200
    body = res.json()
    assert [p["code"] for p in body] == ["basico", "medio", "premium"]
    basico = body[0]
    assert basico == {
        "code": "basico",
        "name": "Básico",
        "credits": 5,
        "unit_price_cents": 500,
        "price_cents": 2500,
        "currency": "BRL",
        "benefits": "Registros pontuais.",
        "highlight": False,
    }
    assert [p["highlight"] for p in body] == [False, True, False]


async def test_packages_require_the_gateway_token(client: AsyncClient) -> None:
    assert (await client.get("/packages")).status_code == 401
    assert (
        await client.get("/packages", headers={INTERNAL_TOKEN_HEADER: "x" * 30})
    ).status_code == 401


# Pedido (RF08, REQ05)


async def test_create_order_returns_pix_and_masks_cpf(
    client: AsyncClient,
    user_headers: UserHeaders,
    billing: dict[str, Any],
    audit: InMemoryAuditLogger,
    provider: FlakyProvider,
) -> None:
    res = await _order(client, user_headers(), billing, package="medio")
    assert res.status_code == 201
    order = res.json()
    assert order["status"] == "pending"
    assert order["package"] == {"code": "medio", "name": "Médio"}
    assert (order["credits"], order["amount_cents"], order["currency"]) == (20, 8000, "BRL")
    assert order["provider"] == "sandbox"
    pix = order["pix_copy_paste"]
    assert "540580.00" in pix and crc16_ccitt(pix[:-4]) == pix[-4:]
    assert order["pix_qr_svg"].startswith("<svg")
    assert order["expires_at"].startswith("2026-11-19T12:30:00")
    assert order["billing"] == {
        "name": "Ana Maria Souza",
        "email": "ana@example.com",
        "phone": "71998765432",
        "cpf_masked": "***.982.247-**",
        "cep": "40110100",
        "street": "Avenida Sete de Setembro",
        "number": "1234",
        "complement": "Sala 5",
        "district": "Centro",
        "city": "Salvador",
        "state": "BA",
    }
    # O CPF completo vai só ao provedor e nunca à resposta
    assert provider.requests[0].payer.cpf == "52998224725"
    assert "52998224725" not in res.text

    [event] = audit.events
    assert event.action == "payment.order.created"
    assert event.actor_id == 7
    assert str(event.actor_ip) == "203.0.113.9"
    assert event.resource_id == order["id"]
    assert event.metadata == {
        "package": "medio",
        "credits": 20,
        "amount_cents": 8000,
        "provider": "sandbox",
    }
    assert "52998224725" not in str(event.model_dump())


async def test_amount_comes_from_the_package_not_the_client(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    res = await client.post(
        "/orders",
        json={"package_code": "basico", "billing": billing, "amount_cents": 1, "credits": 999},
        headers={**user_headers(), "Idempotency-Key": "key-tamper01"},
    )
    assert res.status_code == 201
    assert (res.json()["credits"], res.json()["amount_cents"]) == (5, 2500)


async def test_same_idempotency_key_returns_the_same_order(
    client: AsyncClient,
    user_headers: UserHeaders,
    billing: dict[str, Any],
    provider: FlakyProvider,
) -> None:
    first = await _order(client, user_headers(), billing)
    again = await _order(client, user_headers(), billing)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    assert len(provider.requests) == 1


async def test_idempotency_key_is_scoped_per_user(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    mine = await _order(client, user_headers(7), billing)
    theirs = await _order(client, user_headers(8), billing)
    assert theirs.status_code == 201
    assert mine.json()["id"] != theirs.json()["id"]


async def test_reusing_a_key_for_another_package_is_409(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    await _order(client, user_headers(), billing, package="basico")
    res = await _order(client, user_headers(), billing, package="premium")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "idempotency_key_reused"


async def test_idempotency_key_is_required(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    res = await client.post(
        "/orders", json={"package_code": "basico", "billing": billing}, headers=user_headers()
    )
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["header", "Idempotency-Key"]


async def test_unknown_package_is_404(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    res = await _order(client, user_headers(), billing, package="ouro")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "package_not_found"


async def test_invalid_billing_lists_ptbr_errors_per_field(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    bad = {
        **billing,
        "name": " ",
        "email": "ana@",
        "phone": "1234",
        "cpf": "529.982.247-24",
        "cep": "123",
        "street": "",
        "number": "",
        "district": "",
        "city": "",
        "state": "XX",
    }
    res = await _order(client, user_headers(), bad)
    assert res.status_code == 422
    errors = {tuple(e["loc"][2:])[0]: e["msg"] for e in res.json()["detail"]}
    assert errors == {
        "name": "Informe o nome completo.",
        "email": "Informe um e-mail válido.",
        "phone": "Informe o telefone com DDD.",
        "cpf": "CPF inválido.",
        "cep": "Informe o CEP com 8 dígitos.",
        "street": "Informe o endereço.",
        "number": "Informe o número (ou S/N).",
        "district": "Informe o bairro.",
        "city": "Informe a cidade.",
        "state": "Escolha o estado.",
    }
    # O CPF digitado não volta no erro
    assert "529.982.247-24" not in res.text


async def test_billing_field_too_long_is_422(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    res = await _order(client, user_headers(), {**billing, "complement": "x" * 61})
    assert res.status_code == 422
    assert res.json()["detail"][0]["msg"] == "Use no máximo 60 caracteres."


async def test_empty_complement_is_stored_as_null(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    res = await _order(client, user_headers(), {**billing, "complement": "  "})
    assert res.json()["billing"]["complement"] is None


async def test_orders_require_an_authenticated_user(
    client: AsyncClient, billing: dict[str, Any]
) -> None:
    res = await client.post(
        "/orders",
        json={"package_code": "basico", "billing": billing},
        headers={INTERNAL_TOKEN_HEADER: TOKEN, "Idempotency-Key": "key-00000001"},
    )
    assert res.status_code == 401


async def test_provider_down_marks_order_failed_and_returns_503(
    client: AsyncClient,
    user_headers: UserHeaders,
    billing: dict[str, Any],
    provider: FlakyProvider,
    audit: InMemoryAuditLogger,
) -> None:
    provider.down = True
    res = await _order(client, user_headers(), billing)
    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "payment_provider_unavailable"
    [event] = audit.events
    assert (event.action, event.outcome.value) == ("payment.order.failed", "failure")
    # Repetir a mesma chave devolve o pedido falho, sem nova cobrança
    provider.down = False
    again = await _order(client, user_headers(), billing)
    assert again.status_code == 200
    assert again.json()["status"] == "failed"
    assert again.json()["pix_qr_svg"] is None
    assert len(provider.requests) == 1


# Consulta (IDOR e expiração)


async def test_get_order_is_scoped_to_the_owner(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    order_id = (await _order(client, user_headers(7), billing)).json()["id"]
    assert (await client.get(f"/orders/{order_id}", headers=user_headers(7))).status_code == 200
    other = await client.get(f"/orders/{order_id}", headers=user_headers(8))
    assert other.status_code == 404
    assert other.json()["detail"]["code"] == "order_not_found"
    missing = await client.get(f"/orders/{uuid.uuid4()}", headers=user_headers(7))
    assert missing.status_code == 404


async def test_overdue_order_expires_on_read(
    client: AsyncClient,
    user_headers: UserHeaders,
    billing: dict[str, Any],
    clock: FakeClock,
    audit: InMemoryAuditLogger,
) -> None:
    order_id = (await _order(client, user_headers(), billing)).json()["id"]
    clock.advance(minutes=29)
    assert (await client.get(f"/orders/{order_id}", headers=user_headers())).json()[
        "status"
    ] == "pending"
    clock.advance(minutes=1)
    res = await client.get(f"/orders/{order_id}", headers=user_headers())
    assert res.json()["status"] == "expired"
    assert res.json()["pix_qr_svg"] is None
    await client.get(f"/orders/{order_id}", headers=user_headers())
    assert audit.actions().count("payment.order.expired") == 1


# Confirmação e carteira (#73)


async def test_simulated_payment_credits_the_wallet_once(
    client: AsyncClient,
    user_headers: UserHeaders,
    billing: dict[str, Any],
    audit: InMemoryAuditLogger,
) -> None:
    headers = user_headers()
    assert (await client.get("/credits/balance", headers=headers)).json() == {"balance": 0}

    first = (await _order(client, headers, billing, package="basico", key="key-a0000001")).json()
    second = (await _order(client, headers, billing, package="medio", key="key-b0000001")).json()

    paid = await client.post(f"/orders/{first['id']}/simulate-payment", headers=headers)
    assert paid.status_code == 200
    assert paid.json()["balance"] == 5
    assert paid.json()["order"]["status"] == "paid"
    assert paid.json()["order"]["paid_at"] is not None

    # Repetir a confirmação não credita de novo
    again = await client.post(f"/orders/{first['id']}/simulate-payment", headers=headers)
    assert again.status_code == 200
    assert again.json()["balance"] == 5

    await client.post(f"/orders/{second['id']}/simulate-payment", headers=headers)
    assert (await client.get("/credits/balance", headers=headers)).json() == {"balance": 25}

    statement = (await client.get("/credits/statement", headers=headers)).json()
    assert statement["balance"] == 25
    assert [(e["delta"], e["balance_after"], e["reason"]) for e in statement["entries"]] == [
        (20, 25, "purchase"),
        (5, 5, "purchase"),
    ]
    assert statement["entries"][1]["reference_id"] == first["id"]

    assert audit.actions().count("payment.order.paid") == 2
    assert audit.actions().count("payment.credits.credited") == 2
    credited = next(e for e in audit.events if e.action == "payment.credits.credited")
    assert credited.metadata == {
        "delta": 5,
        "balance_after": 5,
        "reason": "purchase",
        "order_id": first["id"],
    }


async def test_wallet_is_per_user(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    order_id = (await _order(client, user_headers(7), billing)).json()["id"]
    await client.post(f"/orders/{order_id}/simulate-payment", headers=user_headers(7))
    assert (await client.get("/credits/balance", headers=user_headers(8))).json() == {"balance": 0}
    statement = (await client.get("/credits/statement", headers=user_headers(8))).json()
    assert statement == {"balance": 0, "entries": []}


async def test_other_user_cannot_pay_my_order(
    client: AsyncClient, user_headers: UserHeaders, billing: dict[str, Any]
) -> None:
    order_id = (await _order(client, user_headers(7), billing)).json()["id"]
    res = await client.post(f"/orders/{order_id}/simulate-payment", headers=user_headers(8))
    assert res.status_code == 404


async def test_expired_or_failed_order_cannot_be_paid(
    client: AsyncClient,
    user_headers: UserHeaders,
    billing: dict[str, Any],
    clock: FakeClock,
    provider: FlakyProvider,
) -> None:
    order_id = (await _order(client, user_headers(), billing)).json()["id"]
    clock.advance(minutes=31)
    res = await client.post(f"/orders/{order_id}/simulate-payment", headers=user_headers())
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "order_not_payable"

    provider.down = True
    await _order(client, user_headers(), billing, key="key-failed01")
    failed = await client.post(
        "/orders",
        json={"package_code": "basico", "billing": billing},
        headers={**user_headers(), "Idempotency-Key": "key-failed01"},
    )
    res = await client.post(
        f"/orders/{failed.json()['id']}/simulate-payment", headers=user_headers()
    )
    assert res.status_code == 409
    assert (await client.get("/credits/balance", headers=user_headers())).json() == {"balance": 0}


async def test_credits_require_an_authenticated_user(client: AsyncClient) -> None:
    res = await client.get("/credits/balance", headers={INTERNAL_TOKEN_HEADER: TOKEN})
    assert res.status_code == 401
