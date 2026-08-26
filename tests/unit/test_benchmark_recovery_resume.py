from __future__ import annotations

from types import SimpleNamespace

from pd_agent.core import AgentResponse
from pd_agent.core.errors import ProviderError
from pd_agent.experimental import (
    DISPATCH_STARTED,
    LunaBudgetGuard,
    LunaEconomicState,
    LunaEconomicStateStore,
    LunaPricingSnapshot,
    RESPONSE_MISSING,
    UNCERTAIN_CONSUMED,
)
from pd_agent.benchmark.models import BenchmarkConfig
from pd_agent.benchmark.runner import BenchmarkExecutionRunner
from pd_agent.benchmark.scheduler import BenchmarkScheduledAttempt
from pd_agent.providers import (
    RECOVERY_BUDGET_BLOCKED,
    RecoveryCoordinatorResult,
)


def _guard() -> LunaBudgetGuard:
    state = LunaEconomicState(execution_id="resume-test")
    return LunaBudgetGuard(
        state=state,
        state_store=LunaEconomicStateStore(state),
        pricing=LunaPricingSnapshot(max_output_tokens=256),
    )


def _uncertain_record(guard: LunaBudgetGuard):
    record = guard.prepare_dispatch(
        {"input": "resume", "max_output_tokens": 64},
        provider="fake",
        model="fake-model",
        retry_count=0,
    )
    guard.before_request(
        {"input": "resume", "max_output_tokens": 64},
        retry_count=0,
        dispatch_record=record,
    )
    guard.mark_dispatch_started(record)
    guard.record_dispatch_result(record, provider_request_id="request-1")
    try:
        guard.on_failure_without_usage(retry_count=0, failure={"kind": "timeout"})
    except ProviderError:
        pass
    return record


def _attempt() -> BenchmarkScheduledAttempt:
    return BenchmarkScheduledAttempt(
        scheduled_attempt_id="scheduled-1",
        task_id="task-1",
        task_version="1",
        config_id="config-1",
        config_hash="hash-1",
        repetition_index=0,
        attempt_index=1,
        scheduling_position=0,
    )


def test_modern_uncertain_dispatch_is_eligible_but_legacy_state_is_not() -> None:
    guard = _guard()
    assert not BenchmarkExecutionRunner._has_modern_recovery_evidence(guard.state)

    record = _uncertain_record(guard)
    assert record.dispatch_state == DISPATCH_STARTED
    assert record.functional_state == RESPONSE_MISSING
    assert guard.state.ledger[record.reservation_id]["status"] == UNCERTAIN_CONSUMED
    assert BenchmarkExecutionRunner._has_modern_recovery_evidence(guard.state)


def test_recovery_blocker_does_not_call_executor_directly() -> None:
    guard = _guard()
    record = _uncertain_record(guard)
    coordinator = SimpleNamespace(
        recover=lambda *_args: RecoveryCoordinatorResult(
            status=RECOVERY_BUDGET_BLOCKED,
            original_physical_request_id=record.physical_request_id,
            logical_attempt_id=record.logical_attempt_id,
            recovery_generation=0,
            reason="insufficient recovery budget",
        )
    )

    class Executor:
        provider = None

        def __init__(self):
            self.execute_calls = 0

        def execute(self, *_args, **_kwargs):
            self.execute_calls += 1
            raise AssertionError("resume must not call provider execution directly")

    executor = Executor()
    runner = BenchmarkExecutionRunner(executor=executor, recovery_coordinator=coordinator)
    result, evidence = runner._recover_pending(
        record=record,
        task=SimpleNamespace(prompt="resume task"),
        config=BenchmarkConfig(config_id="config-1", provider="fake", model="fake-model", brain_enabled=False),
        attempt=_attempt(),
        execution_dir=SimpleNamespace(),
        pd_agent_commit=None,
        fixture_root=SimpleNamespace(),
        knowledge_needs=(),
        preserve_workspaces=False,
    )

    assert result is None
    assert evidence["status"] == RECOVERY_BUDGET_BLOCKED
    assert executor.execute_calls == 0


def test_recovery_success_requires_explicit_same_run_continuation() -> None:
    guard = _guard()
    record = _uncertain_record(guard)
    coordinator = SimpleNamespace(
        recover=lambda *_args: RecoveryCoordinatorResult(
            status="RECOVERED_EXISTING_RESPONSE",
            original_physical_request_id=record.physical_request_id,
            logical_attempt_id=record.logical_attempt_id,
            recovery_generation=0,
            response=AgentResponse(assistant_message="recovered"),
        )
    )
    runner = BenchmarkExecutionRunner(executor=SimpleNamespace(provider=None), recovery_coordinator=coordinator)
    result, evidence = runner._recover_pending(
        record=record,
        task=SimpleNamespace(prompt="resume task"),
        config=BenchmarkConfig(config_id="config-1", provider="fake", model="fake-model", brain_enabled=False),
        attempt=_attempt(),
        execution_dir=SimpleNamespace(),
        pd_agent_commit=None,
        fixture_root=SimpleNamespace(),
        knowledge_needs=(),
        preserve_workspaces=False,
    )

    assert result is None
    assert evidence["continuation"] == "unavailable"
    assert evidence["original_physical_request_id"] == record.physical_request_id
    assert guard.state.ledger[record.reservation_id]["status"] == UNCERTAIN_CONSUMED
