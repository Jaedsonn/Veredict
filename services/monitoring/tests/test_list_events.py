from datetime import UTC, datetime
from uuid import UUID

from monitoring_service.adapters.memory_repo import InMemoryAuditEventRepository
from monitoring_service.domain import AuditEventFilter, StoredAuditEvent
from monitoring_service.use_cases.list_events import ListAuditEvents
from veriditi_common.audit import AuditEvent, AuditOutcome


async def _repo_with(count: int, received_at: datetime) -> InMemoryAuditEventRepository:
    repo = InMemoryAuditEventRepository()
    for _ in range(count):
        event = AuditEvent(
            service="auth",
            action="auth.user.registered",
            outcome=AuditOutcome.SUCCESS,
            request_id=None,
        )
        await repo.add(event, received_at=received_at)
    return repo


async def test_next_cursor_points_to_last_item_when_more_rows_exist(
    received_at: datetime,
) -> None:
    use_case = ListAuditEvents(await _repo_with(3, received_at))

    first = await use_case.execute(AuditEventFilter(), after_id=None, limit=2)
    last = await use_case.execute(AuditEventFilter(), after_id=first.next_cursor, limit=2)

    assert [item.id for item in first.items] == [1, 2]
    assert first.next_cursor == 2
    assert [item.id for item in last.items] == [3]
    assert last.next_cursor is None


async def test_exact_page_has_no_next_cursor(received_at: datetime) -> None:
    page = await ListAuditEvents(await _repo_with(2, received_at)).execute(
        AuditEventFilter(), after_id=None, limit=2
    )

    assert page.next_cursor is None


class _SpyRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[AuditEventFilter, int | None, int]] = []

    async def add(self, event: AuditEvent, *, received_at: datetime) -> bool:
        raise NotImplementedError

    async def get(self, event_id: UUID) -> StoredAuditEvent | None:
        raise NotImplementedError

    async def search(
        self, filters: AuditEventFilter, *, after_id: int | None, limit: int
    ) -> list[StoredAuditEvent]:
        self.calls.append((filters, after_id, limit))
        return []


async def test_filters_reach_the_repository_with_one_extra_row() -> None:
    spy = _SpyRepository()
    filters = AuditEventFilter(actor_id=42, action="auth.user.registered")

    await ListAuditEvents(spy).execute(filters, after_id=7, limit=10)

    assert spy.calls == [(filters, 7, 11)]


async def test_empty_window_is_valid() -> None:
    start = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
    filters = AuditEventFilter(occurred_from=start, occurred_to=start)

    page = await ListAuditEvents(_SpyRepository()).execute(filters, after_id=None, limit=10)

    assert page.items == []
