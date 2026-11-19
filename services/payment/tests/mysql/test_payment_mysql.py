"""Migrations do payment contra MySQL real: seed da D2, privilégio mínimo e crédito único"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pymysql
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from payment_service.config import Settings, get_settings
from payment_service.main import create_app
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.security import INTERNAL_TOKEN_HEADER, USER_EMAIL_HEADER, USER_ID_HEADER

pytestmark = pytest.mark.mysql

ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"
HOST = os.environ.get("CONTRACT_DB_HOST", "127.0.0.1")
PORT = int(os.environ.get("CONTRACT_DB_PORT", "3317"))
MIGRATOR_PASSWORD = os.environ.get("DB_MIGRATOR_PASSWORD", "m")
RUNTIME = "payment_svc"
RUNTIME_PASSWORD = os.environ.get("PAYMENT_DB_PASSWORD", "p")
TOKEN = "test-internal-token-0123456789"
TABLE_ACCESS_DENIED = 1142

BILLING: dict[str, Any] = {
    "name": "Ana Maria Souza",
    "email": "ana@example.com",
    "phone": "71998765432",
    "cpf": "52998224725",
    "cep": "40110100",
    "street": "Avenida Sete de Setembro",
    "number": "1234",
    "complement": None,
    "district": "Centro",
    "city": "Salvador",
    "state": "BA",
}


def _runtime() -> pymysql.Connection:
    return pymysql.connect(
        host=HOST,
        port=PORT,
        user=RUNTIME,
        password=RUNTIME_PASSWORD,
        database="veriditi",
        autocommit=True,
    )


@pytest.fixture
def migrated(monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
    # Síncrono de propósito: o env.py chama asyncio.run e não pode rodar dentro de um loop
    for key, value in {
        "DB_HOST": HOST,
        "DB_PORT": str(PORT),
        "DB_NAME": "veriditi",
        "DB_USER": RUNTIME,
        "DB_MIGRATOR_USER": "migrator",
        "DB_MIGRATOR_PASSWORD": MIGRATOR_PASSWORD,
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    yield cfg
    command.downgrade(cfg, "base")
    get_settings.cache_clear()


def test_seed_has_the_d2_packages(migrated: Config) -> None:
    with _runtime() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT code, credits, unit_price_cents, price_cents, highlight "
            "FROM credit_packages ORDER BY price_cents"
        )
        assert cur.fetchall() == (
            ("basico", 5, 500, 2500, 0),
            ("medio", 20, 400, 8000, 1),
            ("premium", 60, 350, 21000, 0),
        )


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO credit_packages (code, name, credits, unit_price_cents, price_cents, "
        "benefits) VALUES ('ouro', 'Ouro', 1, 1, 1, 'x')",
        "UPDATE credit_packages SET price_cents = 1",
        "UPDATE credit_ledger SET delta = 1",
        "DELETE FROM credit_ledger",
        "DELETE FROM orders",
        "DELETE FROM credit_wallets",
    ],
)
def test_runtime_user_has_least_privilege(migrated: Config, statement: str) -> None:
    with (
        _runtime() as conn,
        conn.cursor() as cur,
        pytest.raises(pymysql.err.OperationalError) as exc,
    ):
        cur.execute(statement)
    assert exc.value.args[0] == TABLE_ACCESS_DENIED


def test_price_must_match_credits_times_unit(migrated: Config) -> None:
    root = pymysql.connect(
        host=HOST, port=PORT, user="migrator", password=MIGRATOR_PASSWORD, database="veriditi"
    )
    with root, root.cursor() as cur, pytest.raises(pymysql.err.OperationalError) as exc:
        cur.execute(
            "INSERT INTO credit_packages (code, name, credits, unit_price_cents, price_cents, "
            "benefits) VALUES ('torto', 'Torto', 2, 100, 150, 'x')"
        )
    # 3819: Check constraint is violated
    assert exc.value.args[0] == 3819


@pytest.fixture
async def client(migrated: Config) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        db_host=HOST,
        db_port=PORT,
        db_password=RUNTIME_PASSWORD,  # type: ignore[arg-type]
        internal_api_token=TOKEN,  # type: ignore[arg-type]
    )
    db = Database(settings.database_url)
    app = create_app(settings, db, InMemoryAuditLogger())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac,
    ):
        yield ac


HEADERS = {INTERNAL_TOKEN_HEADER: TOKEN, USER_ID_HEADER: "11", USER_EMAIL_HEADER: "a@x.com"}


async def test_concurrent_confirmations_credit_once(client: AsyncClient) -> None:
    created = await client.post(
        "/orders",
        json={"package_code": "medio", "billing": BILLING},
        headers={**HEADERS, "Idempotency-Key": "key-mysql-01"},
    )
    assert created.status_code == 201
    order_id = created.json()["id"]

    results = await asyncio.gather(
        *(client.post(f"/orders/{order_id}/simulate-payment", headers=HEADERS) for _ in range(5))
    )

    assert {r.status_code for r in results} == {200}
    assert {r.json()["balance"] for r in results} == {20}
    statement = (await client.get("/credits/statement", headers=HEADERS)).json()
    assert [(e["delta"], e["balance_after"]) for e in statement["entries"]] == [(20, 20)]

    with _runtime() as conn, conn.cursor() as cur:
        cur.execute("SELECT billing_cpf_masked FROM orders WHERE id = %s", (order_id,))
        assert cur.fetchone() == ("***.982.247-**",)


async def test_concurrent_creates_with_same_key_make_one_order(client: AsyncClient) -> None:
    results = await asyncio.gather(
        *(
            client.post(
                "/orders",
                json={"package_code": "basico", "billing": BILLING},
                headers={**HEADERS, "Idempotency-Key": "key-mysql-02"},
            )
            for _ in range(4)
        )
    )
    assert {r.json()["id"] for r in results} == {results[0].json()["id"]}
    assert sorted(r.status_code for r in results).count(201) == 1
