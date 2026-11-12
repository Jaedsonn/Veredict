from collections.abc import AsyncIterator, Callable
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from veriditi_common.db import Database
from veriditi_common.health import build_health_router


async def _get(app: FastAPI, path: str) -> tuple[int, Any]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(path)
    return resp.status_code, resp.json()


def _app(get_session: Callable[..., Any] | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(build_health_router(get_session))
    return app


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    yield database
    await database.dispose()


async def test_live_is_always_ok() -> None:
    assert await _get(_app(), "/health/live") == (200, {"status": "ok"})


async def test_ready_without_session_does_not_touch_database() -> None:
    assert await _get(_app(), "/health/ready") == (200, {"status": "ok"})


async def test_ready_with_session_checks_database(db: Database) -> None:
    assert await _get(_app(db.session), "/health/ready") == (
        200,
        {"status": "ok", "database": "up"},
    )


class _BrokenSession:
    async def execute(self, *_: object) -> None:
        raise ConnectionError("banco fora")


async def test_ready_returns_503_when_database_fails() -> None:
    async def broken() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, _BrokenSession())

    assert await _get(_app(broken), "/health/ready") == (
        503,
        {"status": "unavailable", "database": "down"},
    )
