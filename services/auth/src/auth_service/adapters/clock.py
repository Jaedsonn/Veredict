"""Implementações de relógio (`Clock`) para produção e testes (LSP / DIP)."""

from datetime import UTC, datetime, timedelta


class SystemClock:
    """Relógio real do sistema, sempre retornando UTC timezone-aware."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Relógio controlável em memória para testes determinísticos de expiração e cooldown (LSP)."""

    def __init__(self, initial: datetime | None = None) -> None:
        default_dt = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
        self._current = initial.astimezone(UTC) if initial else default_dt

    def now(self) -> datetime:
        return self._current

    def advance(
        self,
        *,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        days: int = 0,
    ) -> datetime:
        self._current = self._current + timedelta(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            days=days,
        )
        return self._current
