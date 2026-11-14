import dataclasses
from datetime import UTC, datetime

from notification_service.domain import NotificationStatus, StoredNotification


class InMemoryNotificationRepository:
    """Fake com a semântica do adapter SQL: UNIQUE por chave e UPDATE só a partir de pending"""

    def __init__(self) -> None:
        self.rows: list[StoredNotification] = []

    async def add(self, idempotency_key: str, template: str, *, created_at: datetime) -> int | None:
        if any(row.idempotency_key == idempotency_key for row in self.rows):
            return None
        row = StoredNotification(
            id=len(self.rows) + 1,
            idempotency_key=idempotency_key,
            template=template,
            status=NotificationStatus.PENDING,
            attempts=0,
            message_id=None,
            created_at=created_at.astimezone(UTC),
            sent_at=None,
        )
        self.rows.append(row)
        return row.id

    async def get(self, idempotency_key: str) -> StoredNotification | None:
        return next((row for row in self.rows if row.idempotency_key == idempotency_key), None)

    async def mark_sent(
        self, notification_id: int, *, attempts: int, message_id: str, sent_at: datetime
    ) -> bool:
        return self._finish(
            notification_id,
            status=NotificationStatus.SENT,
            attempts=attempts,
            message_id=message_id,
            sent_at=sent_at.astimezone(UTC),
        )

    async def mark_failed(self, notification_id: int, *, attempts: int) -> bool:
        return self._finish(notification_id, status=NotificationStatus.FAILED, attempts=attempts)

    def _finish(self, notification_id: int, **changes: object) -> bool:
        for index, row in enumerate(self.rows):
            if row.id == notification_id and row.status is NotificationStatus.PENDING:
                self.rows[index] = dataclasses.replace(row, **changes)  # type: ignore[arg-type]
                return True
        return False
