import io
import itertools
import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from notification_service.adapters.memory_sender import InMemoryEmailSender
from notification_service.config import Settings
from notification_service.main import create_app
from notification_service.models import Base
from notification_service.ports import DeliveryTask, MessageIdFactory
from veriditi_common.audit import InMemoryAuditLogger
from veriditi_common.db import Database
from veriditi_common.logging import configure_logging
from veriditi_common.notifications import NotificationRequest
from veriditi_common.security import INTERNAL_TOKEN_HEADER

TOKEN = "test-internal-token-0123456789"
FIXED_NOW = datetime(2026, 11, 12, 15, 0, 0, 123456, tzinfo=UTC)

JsonLogs = Callable[[], list[dict[str, Any]]]
RequestFactory = Callable[..., NotificationRequest]


class FakeSleep:
    """Registra as esperas sem esperar"""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class CollectingScheduler:
    """Guarda as tarefas para o teste provar que nada foi enviado antes de rodá-las"""

    def __init__(self) -> None:
        self.tasks: list[DeliveryTask] = []

    def schedule(self, task: DeliveryTask) -> None:
        self.tasks.append(task)

    async def run_all(self) -> None:
        while self.tasks:
            await self.tasks.pop(0)()


@pytest.fixture
def token() -> str:
    return TOKEN


@pytest.fixture
def now() -> datetime:
    return FIXED_NOW


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        db_user="test",
        db_password="test",  # type: ignore[arg-type]
        internal_api_token=TOKEN,  # type: ignore[arg-type]
        web_url="http://localhost:3000",
    )


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
def audit() -> InMemoryAuditLogger:
    return InMemoryAuditLogger()


@pytest.fixture
def sender() -> InMemoryEmailSender:
    return InMemoryEmailSender()


@pytest.fixture
def sleep() -> FakeSleep:
    return FakeSleep()


@pytest.fixture
def scheduler() -> CollectingScheduler:
    return CollectingScheduler()


@pytest.fixture
def message_ids() -> MessageIdFactory:
    counter = itertools.count(1)

    def make() -> str:
        return f"<fixed-{next(counter)}@veriditi.app>"

    return make


@pytest.fixture
def make_request() -> RequestFactory:
    """Pedido como o auth o envia; o default é o e-mail de verificação"""

    def factory(**overrides: Any) -> NotificationRequest:
        values: dict[str, Any] = {
            "idempotency_key": "email_verification:42",
            "template": "email_verification",
            "to": "joao@exemplo.com",
            "data": {"name": "João", "code": "042137", "expires_in_minutes": 15},
        }
        values.update(overrides)
        return NotificationRequest(**values)

    return factory


@pytest.fixture
async def app(
    settings: Settings,
    db: Database,
    audit: InMemoryAuditLogger,
    sender: InMemoryEmailSender,
    sleep: FakeSleep,
    message_ids: MessageIdFactory,
) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings,
        db=db,
        audit_logger=audit,
        email_sender=sender,
        clock=lambda: FIXED_NOW,
        sleep=sleep,
        message_ids=message_ids,
    )

    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {INTERNAL_TOKEN_HEADER: TOKEN}


def _reset_logging() -> None:
    root = logging.getLogger()
    for handler in [h for h in root.handlers if h.name == "veriditi"]:
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)
    structlog.reset_defaults()


@pytest.fixture
def reset_logging() -> Iterator[None]:
    """Desfaz o configure_logging, que mexe no root logger e no structlog"""
    yield
    _reset_logging()


@pytest.fixture
def json_logs(reset_logging: None) -> JsonLogs:
    """Saída real com redação; peça depois do app, porque o create_app reconfigura o logging"""
    stream = io.StringIO()
    configure_logging("notification", stream=stream, level="DEBUG")

    def read() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines()]

    return read
