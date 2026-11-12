from monitoring_service.domain import AuditEventFilter, AuditEventPage
from monitoring_service.ports import AuditEventRepository
from veriditi_common.errors import AppError


class ListAuditEvents:
    """Cursor por id estável para dados confirmados; não segue a cauda com escritas concorrentes"""

    def __init__(self, events: AuditEventRepository) -> None:
        self._events = events

    async def execute(
        self, filters: AuditEventFilter, *, after_id: int | None, limit: int
    ) -> AuditEventPage:
        start, end = filters.occurred_from, filters.occurred_to
        if start is not None and end is not None and start > end:
            raise AppError(422, "invalid_time_range", "from precisa ser anterior ou igual a to.")
        # Uma linha a mais diz se existe próxima página sem um COUNT
        rows = await self._events.search(filters, after_id=after_id, limit=limit + 1)
        items = rows[:limit]
        next_cursor = items[-1].id if len(rows) > limit else None
        return AuditEventPage(items=items, next_cursor=next_cursor)
