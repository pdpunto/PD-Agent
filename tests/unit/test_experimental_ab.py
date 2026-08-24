from __future__ import annotations

from decimal import Decimal

import pytest

from pd_agent.benchmark.experimental_ab import (
    CANONICAL_ORDER,
    GLOBAL_OPENAI_EXPOSURE_CAP_USD,
    ExperimentalABCell,
    ExperimentalABController,
    ExperimentalABSchedule,
    ExperimentalABState,
    ExperimentalABStatus,
    aggregate_experimental_runs,
    validate_ab_configs,
)
from pd_agent.benchmark.models import BenchmarkConfig


def _config(provider: str, model: str, config_id: str) -> BenchmarkConfig:
    return BenchmarkConfig(config_id=config_id, provider=provider, model=model, brain_enabled=True,
                           model_config={"reasoning": {"effort": "medium"}} if provider == "openai" else {})


def _controller() -> ExperimentalABController:
    gemini = _config("gemini", "gemini-3.5-flash-lite", "gemini-config")
    luna = _config("openai", "gpt-5.6-luna", "luna-config")
    schedule = ExperimentalABSchedule.create(gemini_config_id=gemini.config_id, gemini_config_hash=gemini.config_hash(),
                                              luna_config_id=luna.config_id, luna_config_hash=luna.config_hash())
    cells = {gemini.config_id: ExperimentalABCell(provider="gemini", model=gemini.model, config_id=gemini.config_id, config_hash=gemini.config_hash()),
             luna.config_id: ExperimentalABCell(provider="openai", model=luna.model, config_id=luna.config_id, config_hash=luna.config_hash())}
    return ExperimentalABController(schedule=schedule, state=ExperimentalABState(execution_id="ab-test"), cells=cells)


def test_schedule_is_exact_and_two_cells_are_required():
    controller = _controller()
    assert [item.scheduled_attempt_id.removeprefix("ab-") for item in controller.schedule.attempts] == list(CANONICAL_ORDER)
    assert controller.schedule.target_valid_runs == 2
    assert controller.schedule.max_attempts_per_cell == 3
    assert len(controller.cells) == 2


def test_fail_is_valid_and_does_not_consume_replacement():
    controller = _controller()
    attempt = controller.next_attempt()
    assert attempt is not None
    controller.record(attempt, {"status": "COMPLETED", "outcome": "FAIL"})
    assert controller.state.replacements == 0
    assert controller.cells[attempt.config_id].valid[0]["outcome"] == "FAIL"


def test_invalid_gets_replacement_but_original_schedule_is_preserved():
    controller = _controller()
    attempt = controller.next_attempt()
    assert attempt is not None
    controller.record(attempt, {"status": "INVALID", "outcome": None})
    assert controller.state.replacements == 1
    assert controller.schedule.attempts[0].replacement is False
    assert controller.schedule.attempts[-1].replacement is True
    # Replacements are appended; canonical pending work keeps its order.
    assert controller.next_attempt() is controller.schedule.attempts[1]


def test_rate_limit_pause_preserves_exact_pending_attempt_without_consumption():
    controller = _controller()
    attempt = controller.next_attempt()
    assert attempt is not None
    controller.pause(attempt, rate_limit=True, reason="429 RESOURCE_EXHAUSTED")
    assert controller.state.status == ExperimentalABStatus.RATE_LIMIT_PAUSED
    assert controller.state.pending_attempt_id == attempt.scheduled_attempt_id
    assert controller.state.consumed_attempts == 0
    assert controller.state.replacements == 0
    assert controller.next_attempt().scheduled_attempt_id == attempt.scheduled_attempt_id


def test_persisted_pause_round_trips_exact_pending_without_consumption():
    controller = _controller()
    attempt = controller.next_attempt()
    assert attempt is not None
    controller.pause(attempt, rate_limit=True, reason="429 RESOURCE_EXHAUSTED")
    restored_schedule = ExperimentalABSchedule.from_dict(controller.schedule.to_dict())
    restored = ExperimentalABController.from_dict(restored_schedule, controller.to_dict())
    assert restored.state.status == ExperimentalABStatus.RATE_LIMIT_PAUSED
    assert restored.state.pending_attempt_id == attempt.scheduled_attempt_id
    assert restored.state.consumed_attempts == 0
    assert restored.state.replacements == 0
    assert restored.next_attempt().scheduled_attempt_id == attempt.scheduled_attempt_id


def test_resume_rejects_schedule_hash_drift():
    controller = _controller()
    payload = controller.schedule.to_dict()
    payload["attempts"][0]["attempt_index"] = 2
    with pytest.raises(ValueError, match="schedule hash mismatch"):
        ExperimentalABSchedule.from_dict(payload)


def test_luna_reservation_is_not_double_counted_after_resume():
    controller = _controller()
    luna_attempt = controller.schedule.attempts[1]
    controller.state.reserve_luna_attempt(attempt_id=luna_attempt.scheduled_attempt_id)
    before = controller.state.global_openai_exposure_usd
    restored = ExperimentalABController.from_dict(
        ExperimentalABSchedule.from_dict(controller.schedule.to_dict()), controller.to_dict()
    )
    restored.state.reserve_luna_attempt(attempt_id=luna_attempt.scheduled_attempt_id)
    assert restored.state.global_openai_exposure_usd == before == Decimal("1.00")


def test_luna_global_exposure_is_fail_closed_at_three_dollars():
    state = ExperimentalABState(execution_id="ab-test")
    for _ in range(3):
        state.reserve_luna_attempt()
    assert state.global_openai_exposure_usd == GLOBAL_OPENAI_EXPOSURE_CAP_USD
    with pytest.raises(RuntimeError, match="global OpenAI exposure cap"):
        state.reserve_luna_attempt()
    assert state.status == ExperimentalABStatus.BUDGET_BLOCKED


def test_config_fairness_and_aggregation_are_isolated():
    gemini = _config("gemini", "gemini-3.5-flash-lite", "gemini-config")
    luna = _config("openai", "gpt-5.6-luna", "luna-config")
    validate_ab_configs([gemini, luna])
    report = aggregate_experimental_runs([
        {"provider": "gemini", "status": "COMPLETED", "outcome": "PASS"},
        {"provider": "openai", "status": "COMPLETED", "outcome": "FAIL", "cost_usd": "0.20"},
    ])
    assert report["experimental"] is True
    assert report["non_official"] is True
    assert report["providers"]["gemini"]["cost_usd"] is None
    assert report["providers"]["openai"]["cost_usd"] == "0.20"
