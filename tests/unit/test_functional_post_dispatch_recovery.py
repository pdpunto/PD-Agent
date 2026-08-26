from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.core import AgentMessage, AgentRequest, AgentResponse
from pd_agent.core.errors import ProviderError
from pd_agent.experimental import (
    LunaBudgetGuard,
    LunaEconomicState,
    LunaEconomicStateStore,
    LunaPricingSnapshot,
    UNCERTAIN_CONSUMED,
)
from pd_agent.benchmark import (
    BenchmarkConfig,
    BenchmarkExecutionResult,
    BenchmarkExecutionRunner,
)
from pd_agent.benchmark.scheduler import BenchmarkScheduledAttempt
from pd_agent.providers import (
    ProviderRecoveryAdapter,
    ProviderRecoveryCapabilities,
    RECOVERY_BUDGET_BLOCKED,
    RECOVERY_DISPATCH_UNCERTAIN,
    RECOVERY_EXISTING_RESPONSE,
    RECOVERY_IDENTITY_INVALID,
    RECOVERY_LIMIT_EXHAUSTED,
    RECOVERY_PRE_DISPATCH_FAILED,
    RECOVERY_PROVIDER_FAILURE,
    RECOVERY_REISSUE_SUCCEEDED,
    RecoveryCoordinator,
    RecoveryResult,
)
from pd_agent.providers.recovery import RECOVERY_INVALID, RECOVERY_RECOVERED
from pd_agent.providers.openai_provider import OpenAIProvider


@dataclass
class _Responses:
    outcomes: list[object]
    calls: list[dict[str, object]]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Client:
    def __init__(self, outcomes: list[object]) -> None:
        self.responses = _Responses(outcomes, [])

    def with_options(self, **_kwargs):
        return self


def _guard(execution_id: str = "r9") -> LunaBudgetGuard:
    state = LunaEconomicState(execution_id=execution_id)
    return LunaBudgetGuard(
        state=state,
        state_store=LunaEconomicStateStore(state),
        pricing=LunaPricingSnapshot(max_output_tokens=256),
    )


def _request() -> AgentRequest:
    return AgentRequest(
        messages=(AgentMessage(role="user", content="recover"),),
        model_config={"model": "gpt-test", "max_output_tokens": 64},
    )


def _task() -> SimpleNamespace:
    return SimpleNamespace(prompt="recover task")


def _config() -> BenchmarkConfig:
    return BenchmarkConfig(config_id="cfg", provider="fake", model="gpt-test", brain_enabled=False)


def _attempt() -> BenchmarkScheduledAttempt:
    return BenchmarkScheduledAttempt(
        scheduled_attempt_id="scheduled-1",
        task_id="task-1",
        task_version="1",
        config_id="cfg",
        config_hash=_config().config_hash(),
        repetition_index=0,
        attempt_index=1,
        scheduling_position=0,
    )


def _uncertain(guard: LunaBudgetGuard, *, provider: str = "fake", attempt_id: str | None = None):
    if attempt_id is not None:
        guard.begin_attempt(attempt_id)
    record = guard.prepare_dispatch(
        {"input": "recover", "max_output_tokens": 64},
        provider=provider,
        model="gpt-test",
        retry_count=0,
    )
    guard.before_request(
        {"input": "recover", "max_output_tokens": 64},
        retry_count=0,
        dispatch_record=record,
    )
    guard.mark_dispatch_started(record)
    guard.record_dispatch_result(record, provider_request_id="request-original")
    with pytest.raises(ProviderError):
        guard.on_failure_without_usage(retry_count=0, failure={"kind": "timeout"})
    return record


def _response(response_id: str = "recovered") -> AgentResponse:
    return AgentResponse(
        assistant_message="real recovered response",
        provider_metadata={"provider": "fake", "response_id": response_id},
    )


def _result() -> BenchmarkExecutionResult:
    return BenchmarkExecutionResult(
        execution_id="execution-r9",
        execution_root=Path("."),
        workspace=SimpleNamespace(),
        run_state=SimpleNamespace(logical_provider_request_count=1),
        final_report=SimpleNamespace(),
        collection=SimpleNamespace(logical_provider_request_count=1),
        classification=SimpleNamespace(),
        benchmark_run=SimpleNamespace(),
        minecraft_result=None,
        project_snapshot=SimpleNamespace(),
        benchmark_run_path=Path("benchmark-run.json"),
        benchmark_collection_path=Path("benchmark-collection.json"),
        benchmark_classification_path=Path("benchmark-classification.json"),
        workspace_metadata_path=Path("workspace.json"),
        runtime_storage_root=Path("runtime"),
    )


class _RetrievalProvider(ProviderRecoveryAdapter):
    provider_name = "fake"

    def __init__(self, result: RecoveryResult) -> None:
        self.result = result
        self.retrieve_calls = 0
        self.execute_calls = 0

    def recovery_capabilities(self) -> ProviderRecoveryCapabilities:
        return ProviderRecoveryCapabilities(provider="fake", response_retrieval=True)

    def retrieve_response(self, _lookup):
        self.retrieve_calls += 1
        return self.result

    def execute(self, _request):
        self.execute_calls += 1
        raise AssertionError("retrieval success must not reissue")


class _ContinuingExecutor:
    def __init__(self, provider, result: BenchmarkExecutionResult | None = None) -> None:
        self.provider = provider
        self.continuation_calls = 0
        self.responses: list[AgentResponse] = []
        self.result = result or _result()

    def continue_recovered_response(self, response, *_args, **_kwargs):
        self.continuation_calls += 1
        self.responses.append(response)
        return self.result


def _recover_pending(runner, record, *, attempt=None):
    return runner._recover_pending(
        record=record,
        task=_task(),
        config=_config(),
        attempt=attempt or _attempt(),
        execution_dir=Path("."),
        pd_agent_commit="commit",
        fixture_root=Path("tests/fixtures/l11_fabric_fixture"),
        knowledge_needs=(),
        preserve_workspaces=True,
    )


def test_retrieval_success_reaches_real_continuation_without_reissue() -> None:
    guard = _guard("retrieval-e2e")
    original = _uncertain(guard)
    response = _response()
    provider = _RetrievalProvider(
        RecoveryResult(
            status=RECOVERY_RECOVERED,
            provider="fake",
            model="gpt-test",
            physical_request_id=original.physical_request_id,
            provider_request_id="request-original",
            agent_response=response,
        )
    )
    executor = _ContinuingExecutor(provider)
    runner = BenchmarkExecutionRunner(executor=executor, recovery_coordinator=RecoveryCoordinator(provider, budget_guard=guard))

    result, evidence = _recover_pending(runner, original)

    assert isinstance(result, BenchmarkExecutionResult)
    assert executor.responses == [response]
    assert executor.continuation_calls == 1
    assert provider.retrieve_calls == 1
    assert provider.execute_calls == 0
    assert guard.physical_request_count == 1
    assert guard.state.ledger[original.reservation_id]["status"] == UNCERTAIN_CONSUMED
    assert evidence["terminal_state"] == "RECOVERED"
    assert evidence["continuation_status"] == "COMPLETED"
    assert evidence["logical_attempt_id"] == original.logical_attempt_id
    assert "response" not in evidence


def test_reissue_success_reaches_same_run_continuation_and_preserves_schedule_identity() -> None:
    guard = _guard("reissue-e2e")
    original = _uncertain(guard, provider="openai", attempt_id="scheduled-1")
    client = _Client([SimpleNamespace(id="response-recovery", _request_id="request-recovery", status="completed", usage={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}, output=[])])
    provider = OpenAIProvider(model="gpt-test", client=client)
    executor = _ContinuingExecutor(provider)
    attempt = _attempt()
    runner = BenchmarkExecutionRunner(executor=executor, recovery_coordinator=RecoveryCoordinator(provider, budget_guard=guard))

    result, evidence = _recover_pending(runner, original, attempt=attempt)
    recovery = next(record for record in guard.state.dispatch_records.values() if record.get("recovery_of") == original.physical_request_id)

    assert isinstance(result, BenchmarkExecutionResult)
    assert evidence["status"] == RECOVERY_REISSUE_SUCCEEDED
    assert len(client.responses.calls) == 1
    assert recovery["recovery_generation"] == 1
    assert recovery["recovery_of"] == original.physical_request_id
    assert recovery["logical_attempt_id"] == attempt.scheduled_attempt_id
    assert executor.continuation_calls == 1


def test_retrieval_identity_mismatch_never_continues_or_reissues() -> None:
    guard = _guard("identity-mismatch")
    original = _uncertain(guard)
    provider = _RetrievalProvider(
        RecoveryResult(
            status=RECOVERY_RECOVERED,
            provider="fake",
            model="gpt-test",
            physical_request_id="wrong-dispatch",
            provider_request_id="request-original",
            agent_response=_response(),
        )
    )
    executor = _ContinuingExecutor(provider)
    runner = BenchmarkExecutionRunner(executor=executor, recovery_coordinator=RecoveryCoordinator(provider, budget_guard=guard, allow_reissue=False))

    result, evidence = _recover_pending(runner, original)

    assert result is None
    assert evidence["status"] == RECOVERY_IDENTITY_INVALID
    assert executor.continuation_calls == 0
    assert provider.execute_calls == 0
    assert guard.physical_request_count == 1


def test_recovery_claim_without_real_response_fails_closed() -> None:
    guard = _guard("missing-response")
    original = _uncertain(guard)
    provider = _RetrievalProvider(
        RecoveryResult(
            status=RECOVERY_INVALID,
            provider="fake",
            model="gpt-test",
            physical_request_id=original.physical_request_id,
        )
    )
    executor = _ContinuingExecutor(provider)
    runner = BenchmarkExecutionRunner(executor=executor, recovery_coordinator=RecoveryCoordinator(provider, budget_guard=guard, allow_reissue=False))

    result, evidence = _recover_pending(runner, original)

    assert result is None
    assert evidence["status"] == RECOVERY_IDENTITY_INVALID
    assert executor.continuation_calls == 0


def test_budget_blocked_recovery_stays_paused_without_functional_failure() -> None:
    guard = _guard("budget-blocked")
    original = _uncertain(guard, provider="openai")
    guard.state.global_uncertain_consumed_usd = guard.state.global_ceiling_usd
    guard.state.attempt_uncertain_consumed_usd = guard.state.attempt_ceiling_usd
    provider = OpenAIProvider(model="gpt-test", client=_Client([]))
    executor = _ContinuingExecutor(provider)
    runner = BenchmarkExecutionRunner(executor=executor, recovery_coordinator=RecoveryCoordinator(provider, budget_guard=guard))

    result, evidence = _recover_pending(runner, original)

    assert result is None
    assert evidence["status"] == RECOVERY_BUDGET_BLOCKED
    assert executor.continuation_calls == 0
    assert guard.physical_request_count == 1


def test_limit_exhausted_makes_no_provider_call_or_continuation() -> None:
    guard = _guard("limit")
    original = _uncertain(guard, provider="openai")
    original.recovery_generation = 1
    guard.state.dispatch_records[original.physical_request_id] = original.to_dict()
    provider = OpenAIProvider(model="gpt-test", client=_Client([]))
    executor = _ContinuingExecutor(provider)
    result = RecoveryCoordinator(provider, budget_guard=guard).recover(original, _request())

    assert result.status == RECOVERY_LIMIT_EXHAUSTED
    assert provider._client.responses.calls == []
    assert executor.continuation_calls == 0


def test_second_uncertain_reissue_blocks_without_third_dispatch() -> None:
    guard = _guard("second-uncertain")
    original = _uncertain(guard, provider="openai")
    provider = OpenAIProvider(model="gpt-test", client=_Client([RuntimeError("transport")]))
    first = RecoveryCoordinator(provider, budget_guard=guard).recover(original, _request())
    recovery = next(record for record in guard.state.dispatch_records.values() if record.get("recovery_of") == original.physical_request_id)
    second = RecoveryCoordinator(provider, budget_guard=guard).recover(type(original).from_dict(recovery), _request())

    assert first.status == RECOVERY_DISPATCH_UNCERTAIN
    assert second.status == RECOVERY_LIMIT_EXHAUSTED
    assert guard.physical_request_count == 2


def test_pre_dispatch_recovery_failure_has_no_response_or_remote_uncertainty() -> None:
    guard = _guard("pre-dispatch")
    original = _uncertain(guard)

    class PreDispatchProvider:
        budget_guard = guard

        def recovery_capabilities(self):
            return ProviderRecoveryCapabilities.none("fake")

        def execute(self, _request):
            record = guard.prepare_dispatch({"input": "recover"}, provider="fake", model="gpt-test", retry_count=0, recovery_generation=1, recovery_of=original.physical_request_id)
            guard.abandon_pre_dispatch(record, reason="local validation")
            raise ProviderError("local recovery failure", kind="protocol", provider="fake")

    result = RecoveryCoordinator(PreDispatchProvider(), budget_guard=guard).recover(original, _request())
    recovery = next(record for record in guard.state.dispatch_records.values() if record.get("recovery_of") == original.physical_request_id)

    assert result.status == RECOVERY_PRE_DISPATCH_FAILED
    assert recovery["functional_state"] == "ABANDONED"
    assert guard.physical_request_count == 1
    assert guard.state.ledger[original.reservation_id]["status"] == UNCERTAIN_CONSUMED


def test_nonrecoverable_provider_failure_is_not_functional_fail() -> None:
    guard = _guard("provider-failure")
    original = _uncertain(guard)

    class FailingProvider:
        budget_guard = guard

        def recovery_capabilities(self):
            return ProviderRecoveryCapabilities.none("fake")

        def execute(self, _request):
            raise ProviderError("provider unavailable", kind="unavailable", provider="fake")

    result = RecoveryCoordinator(FailingProvider(), budget_guard=guard).recover(original, _request())

    assert result.status == RECOVERY_PROVIDER_FAILURE
    assert guard.physical_request_count == 1


def test_missing_coordinator_never_silently_resends_original_request() -> None:
    guard = _guard("no-coordinator")
    original = _uncertain(guard)
    executor = _ContinuingExecutor(provider=None)
    runner = BenchmarkExecutionRunner(executor=executor, recovery_coordinator=None)

    result, evidence = _recover_pending(runner, original)

    assert result is None
    assert evidence["status"] == "RECOVERY_RECONCILIATION_UNSUPPORTED"
    assert "unavailable" in evidence["reason"]
    assert executor.continuation_calls == 0


def test_legacy_without_dispatch_record_never_enters_functional_recovery(tmp_path: Path) -> None:
    guard = _guard("legacy")
    execution_dir = tmp_path / "legacy"
    execution_dir.mkdir()
    assert guard.state.dispatch_records == {}
    assert BenchmarkExecutionRunner._has_modern_recovery_evidence(guard.state) is False
    assert not (execution_dir / "recovery_state.json").exists()


def test_response_provenance_and_same_run_identity_are_preserved() -> None:
    guard = _guard("identity-preserved")
    original = _uncertain(guard, attempt_id="scheduled-1")
    provider = _RetrievalProvider(
        RecoveryResult(
            status=RECOVERY_RECOVERED,
            provider="fake",
            model="gpt-test",
            physical_request_id=original.physical_request_id,
            provider_request_id="request-original",
            agent_response=_response("response-original"),
        )
    )
    executor = _ContinuingExecutor(provider)
    attempt = _attempt()
    runner = BenchmarkExecutionRunner(executor=executor, recovery_coordinator=RecoveryCoordinator(provider, budget_guard=guard))
    result, evidence = _recover_pending(runner, original, attempt=attempt)

    assert isinstance(result, BenchmarkExecutionResult)
    assert evidence["original_physical_request_id"] == original.physical_request_id
    assert evidence["logical_attempt_id"] == attempt.scheduled_attempt_id
    assert executor.responses[0].provider_metadata["response_id"] == "response-original"


def test_completed_recovery_state_blocks_duplicate_resume_fail_closed() -> None:
    state = {
        "status": RECOVERY_EXISTING_RESPONSE,
        "terminal_state": "RECOVERED",
        "continuation_status": "COMPLETED",
    }

    assert BenchmarkExecutionRunner._recovery_continuation_already_completed(state) is True
    assert BenchmarkExecutionRunner._recovery_continuation_already_completed(None) is False
    assert BenchmarkExecutionRunner._recovery_continuation_already_completed({"terminal_state": "PAUSED"}) is False
