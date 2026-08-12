from __future__ import annotations

from dataclasses import dataclass

from pd_agent.benchmark import BenchmarkPacedProvider, BenchmarkRequestPacer
from pd_agent.core import AgentRequest, AgentResponse


@dataclass
class _FakeClock:
    value: float = 100.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: AgentRequest) -> AgentResponse:  # noqa: ARG002
        self.calls += 1
        return AgentResponse(assistant_message="ok")


def test_first_request_does_not_wait() -> None:
    clock = _FakeClock()
    waits: list[float] = []
    pacer = BenchmarkRequestPacer(
        min_interval_seconds=4.5,
        daily_request_budget=500,
        clock=clock.now,
        sleeper=waits.append,
    )

    waited = pacer.acquire()

    assert waited == 0.0
    assert waits == []
    assert pacer.request_count == 1
    assert pacer.requests_remaining() == 499


def test_second_request_waits_until_minimum_interval() -> None:
    clock = _FakeClock()

    def sleeper(seconds: float) -> None:
        clock.advance(seconds)

    pacer = BenchmarkRequestPacer(
        min_interval_seconds=4.5,
        daily_request_budget=500,
        clock=clock.now,
        sleeper=sleeper,
    )

    assert pacer.acquire() == 0.0
    clock.advance(0.5)

    waited = pacer.acquire()

    assert waited == 4.0
    assert pacer.request_count == 2
    assert pacer.total_wait_seconds == 4.0
    assert clock.value == 104.5


def test_request_after_interval_does_not_wait() -> None:
    clock = _FakeClock()
    waits: list[float] = []
    pacer = BenchmarkRequestPacer(min_interval_seconds=4.5, clock=clock.now, sleeper=waits.append)

    pacer.acquire()
    clock.advance(5.0)

    waited = pacer.acquire()

    assert waited == 0.0
    assert waits == []
    assert pacer.request_count == 2


def test_shared_pacer_is_reused_across_brain_off_and_on() -> None:
    clock = _FakeClock()
    waits: list[float] = []
    pacer = BenchmarkRequestPacer(min_interval_seconds=4.5, clock=clock.now, sleeper=waits.append)
    provider = _FakeProvider()
    off = BenchmarkPacedProvider(provider=provider, pacer=pacer)
    on = BenchmarkPacedProvider(provider=provider, pacer=pacer)
    request = AgentRequest()

    off.execute(request)
    clock.advance(0.25)
    on.execute(request)

    assert provider.calls == 2
    assert waits == [4.25]
    assert pacer.request_count == 2


def test_budget_snapshot_reports_projection() -> None:
    clock = _FakeClock()

    def sleeper(seconds: float) -> None:
        clock.advance(seconds)

    pacer = BenchmarkRequestPacer(
        min_interval_seconds=4.5,
        daily_request_budget=500,
        clock=clock.now,
        sleeper=sleeper,
    )

    pacer.acquire()
    pacer.acquire()

    snapshot = pacer.budget_snapshot(planned_runs=18, completed_runs=2)

    assert snapshot["request_count"] == 2
    assert snapshot["requests_remaining"] == 498
    assert snapshot["projected_request_count"] == 18.0
