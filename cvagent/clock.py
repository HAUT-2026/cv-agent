"""Injectable clocks for workflow and SLA tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return an aware UTC timestamp."""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class ManualClock:
    def __init__(self, initial: datetime) -> None:
        if initial.tzinfo is None:
            raise ValueError("ManualClock requires an aware datetime")
        self._now = initial.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> datetime:
        self._now += timedelta(**kwargs)
        return self._now

    def set(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("ManualClock requires an aware datetime")
        self._now = value.astimezone(timezone.utc)


__all__ = ["Clock", "ManualClock", "SystemClock"]
