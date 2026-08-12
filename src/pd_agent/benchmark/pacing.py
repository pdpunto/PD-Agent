"""Benchmark-local request pacing for provider calls."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from pd_agent.core import AgentRequest, AgentResponse, ModelProvider


@dataclass(slots=True)
class BenchmarkRequestPacer:
    """Throttle logical provider requests with a monotonic clock."""

    min_interval_seconds: float = 4.5
    daily_request_budget: int | None = None
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], None] = time.sleep
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _last_request_at: float | None = field(default=None, init=False, repr=False)
    _request_count: int = field(default=0, init=False, repr=False)
    _total_wait_seconds: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.min_interval_seconds <= 0:
            raise ValueError("min_interval_seconds must be positive")
        if self.daily_request_budget is not None and self.daily_request_budget <= 0:
            raise ValueError("daily_request_budget must be positive when set")

    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def total_wait_seconds(self) -> float:
        return self._total_wait_seconds

    def acquire(self) -> float:
        """Wait until the next provider slot is available."""

        with self._lock:
            now = self.clock()
            waited = 0.0
            if self._last_request_at is not None:
                elapsed = now - self._last_request_at
                waited = max(0.0, self.min_interval_seconds - elapsed)
                if waited > 0:
                    self.sleeper(waited)
                    now = self.clock()
                    self._total_wait_seconds += waited
            self._last_request_at = now
            self._request_count += 1
            return waited

    def requests_remaining(self) -> int | None:
        if self.daily_request_budget is None:
            return None
        return max(0, self.daily_request_budget - self._request_count)

    def budget_snapshot(
        self,
        *,
        planned_runs: int | None = None,
        completed_runs: int | None = None,
    ) -> dict[str, float | int | None]:
        """Return a lightweight budget report for benchmark logging."""

        snapshot: dict[str, float | int | None] = {
            "min_interval_seconds": self.min_interval_seconds,
            "daily_request_budget": self.daily_request_budget,
            "request_count": self._request_count,
            "requests_remaining": self.requests_remaining(),
            "total_wait_seconds": self.total_wait_seconds,
            "planned_runs": planned_runs,
            "completed_runs": completed_runs,
            "projected_request_count": None,
        }
        if planned_runs is not None and completed_runs not in {None, 0}:
            snapshot["projected_request_count"] = (self._request_count / completed_runs) * planned_runs
        return snapshot


@dataclass(slots=True)
class BenchmarkPacedProvider(ModelProvider):
    """Provider wrapper that enforces benchmark pacing before each request."""

    provider: ModelProvider
    pacer: BenchmarkRequestPacer

    def execute(self, request: AgentRequest) -> AgentResponse:
        self.pacer.acquire()
        return self.provider.execute(request)
