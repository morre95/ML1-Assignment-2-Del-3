"""Rate limiting utilities for hub requests."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

Clock = Callable[[], float]
Sleeper = Callable[[float], None]


@dataclass
class RateLimiter:
    """Simple minimum-interval limiter for one agent name."""

    interval_seconds: float
    clock: Clock = time.monotonic
    sleeper: Sleeper = time.sleep
    _next_allowed_at: float = 0.0

    def wait(self) -> None:
        now = self.clock()
        if now < self._next_allowed_at:
            self.sleeper(self._next_allowed_at - now)
            now = self.clock()
        self._next_allowed_at = now + self.interval_seconds

    def set_interval(self, interval_seconds: float) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
