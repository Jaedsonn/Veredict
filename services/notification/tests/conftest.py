from collections.abc import AsyncIterator

import pytest

from notification_service.models import Base
from veriditi_common.db import Database


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()
