from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from pd_agent.core import AgentMessage, AgentRequest, AgentResponse
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
from pd_agent.providers import (
    OpenAIProvider,
    ProviderRecoveryAdapter,
    ProviderRecoveryCapabilities,
    RecoveryCoordinator,
    RecoveryLookupRequest,
    RecoveryResult,
    RECOVERY_BUDGET_BLOCKED,
    RECOVERY_DISPATCH_UNCERTAIN,
    RECOVERY_EXISTING_RESPONSE,
    RECOVERY_IDENTITY_INVALID,
    RECOVERY_LIMIT_EXHAUSTED,
    RECOVERY_RECONCILIATION_UNSUPPORTED,
    RECOVERY_REISSUE_SUCCEEDED,
)
from pd_agent.providers.recovery import RECOVERY_RECOVERED


def _request() -> AgentRequest:
    return AgentRequest(
        messages=(AgentMessage(role="user", content="recover me"),),
        model_config={"model": "gpt-test", "max_output_tokens": 64},
    )


def _usage() -> dict[str, object]:
    return {
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 14,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 1},
    }


class _Responses:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Client:
    def __init__(self, outcomes: list[object]) -> None:
        self.responses = _Responses(outcomes)

    def with_options(self, **_kwargs):
        return self


def _guard(execution_id: str = "coordinator") -> LunaBudgetGuard:
    state = LunaEconomicState(execution_id=execution_id)
    return LunaBudgetGuard(
        state=state,
        state_store=LunaEconomicStateStore(state),
        pricing=LunaPricingSnapshot(max_output_tokens=4096),
    )


def _uncertain_dispatch(guard: LunaBudgetGuard, *, provider: str = "openai"):
    record = guard.prepare_dispatch(
        {"input": "recover me", "max_output_tokens": 64},
        provider=provider,
        model="gpt-test",
        retry_count=0,
    )
    guard.before_request(
        {"input": "recover me", "max_output_tokens": 64},
        retry_count=0,
        dispatch_record=record,
    )
    guard.mark_dispatch_started(record)
    guard.record_dispatch_result(record, provider_request_id="req-original")
    with pytest.raises(ProviderError):
        guard.on_failure_without_usage(retry_count=0, failure={"kind": "timeout"})
    return record


def test_non_eligible_dispatch_is_rejected_without_recovery() -> None:
    guard = _guard()
    record = guard.prepare_dispatch({"input": "not sent"}, provider="openai", model="gpt-test", retry_count=0)
    coordinator = RecoveryCoordinator(OpenAIProvider(model="gpt-test", client=_Client([])), budget_guard=guard)

    result = coordinator.recover(record, _request())

    assert result.status == RECOVERY_IDENTITY_INVALID
    assert guard.state.physical_request_count == 0


def test_unsupported_openai_reconciliation_does_not_call_retrieval() -> None:
    guard = _guard()
    original = _uncertain_dispatch(guard)
    client = _Client([])
    provider = OpenAIProvider(model="gpt-test", client=client)

    result = RecoveryCoordinator(provider, budget_guard=guard, allow_reissue=False).recover(original, _request())

    assert result.status == RECOVERY_RECONCILIATION_UNSUPPORTED
    assert client.responses.calls == []
    assert len(guard.state.dispatch_records) == 1


class _RetrievalProvider(ProviderRecoveryAdapter):
    def __init__(self, result_factory) -> None:
        self.result_factory = result_factory
        self.retrieve_calls = 0
        self.execute_calls = 0

    def recovery_capabilities(self) -> ProviderRecoveryCapabilities:
        return ProviderRecoveryCapabilities(provider="fake", response_retrieval=True)

    def retrieve_response(self, lookup: RecoveryLookupRequest) -> RecoveryResult:
        self.retrieve_calls += 1
        return self.result_factory(lookup)

    def execute(self, _request: AgentRequest) -> AgentResponse:
        self.execute_calls += 1
        return AgentResponse(assistant_message="unexpected")


def test_reconciliation_success_returns_real_response_without_new_dispatch() -> None:
    guard = _guard("reconciliation")
    original = _uncertain_dispatch(guard, provider="fake")

    def recovered(lookup):
        return RecoveryResult(
            status=RECOVERY_RECOVERED,
            provider="fake",
            model="gpt-test",
            physical_request_id=lookup.physical_request_id,
            provider_request_id="req-original",
            agent_response=AgentResponse(assistant_message="existing response"),
        )

    provider = _RetrievalProvider(recovered)
    result = RecoveryCoordinator(provider, budget_guard=guard).recover(original, _request())

    assert result.status == RECOVERY_EXISTING_RESPONSE
    assert result.response is not None
    assert result.response.assistant_message == "existing response"
    assert provider.retrieve_calls == 1
    assert provider.execute_calls == 0
    assert len(guard.state.dispatch_records) == 1
    assert guard.state.global_uncertain_consumed_usd > 0


def test_reconciliation_identity_mismatch_fails_closed() -> None:
    guard = _guard("reconciliation-mismatch")
    original = _uncertain_dispatch(guard, provider="fake")
    provider = _RetrievalProvider(
        lambda lookup: RecoveryResult(
            status=RECOVERY_RECOVERED,
            provider="fake",
            model="gpt-test",
            physical_request_id="wrong-dispatch",
            agent_response=AgentResponse(assistant_message="wrong"),
        )
    )

    result = RecoveryCoordinator(provider, budget_guard=guard, allow_reissue=False).recover(original, _request())

    assert result.status == RECOVERY_IDENTITY_INVALID
    assert result.response is None
    assert len(guard.state.dispatch_records) == 1


def test_reissue_success_creates_new_physical_reservation_and_generation() -> None:
    guard = _guard("reissue-success")
    original = _uncertain_dispatch(guard)
    response = SimpleNamespace(id="resp-recovery", _request_id="req-recovery", status="completed", usage=_usage(), output=[])
    provider = OpenAIProvider(model="gpt-test", client=_Client([response]))

    result = RecoveryCoordinator(provider, budget_guard=guard).recover(original, _request())

    assert result.status == RECOVERY_REISSUE_SUCCEEDED
    assert result.response is not None
    assert len(guard.state.dispatch_records) == 2
    recovery = next(
        record for record in guard.state.dispatch_records.values()
        if record.get("recovery_of") == original.physical_request_id
    )
    assert recovery["recovery_generation"] == 1
    assert recovery["physical_request_id"] != original.physical_request_id
    assert recovery["reservation_id"] != original.reservation_id
    assert recovery["client_correlation_id"] != original.client_correlation_id
    assert recovery["logical_attempt_id"] == original.logical_attempt_id
    assert recovery["functional_state"] == "RESPONSE_AVAILABLE"
    assert guard.state.ledger[original.reservation_id]["status"] == UNCERTAIN_CONSUMED
    assert guard.state.global_uncertain_consumed_usd > 0
    assert guard.state.global_accumulated_usd > 0


def test_reissue_budget_blocked_does_not_cross_provider() -> None:
    guard = _guard("reissue-budget")
    original = _uncertain_dispatch(guard)
    guard.state.global_uncertain_consumed_usd = guard.state.global_ceiling_usd
    guard.state.attempt_uncertain_consumed_usd = guard.state.attempt_ceiling_usd
    client = _Client([])
    provider = OpenAIProvider(model="gpt-test", client=client)

    result = RecoveryCoordinator(provider, budget_guard=guard).recover(original, _request())

    assert result.status == RECOVERY_BUDGET_BLOCKED
    assert client.responses.calls == []
    assert guard.state.physical_request_count == 1


def test_reissue_second_uncertain_outcome_is_bounded() -> None:
    guard = _guard("reissue-uncertain")
    original = _uncertain_dispatch(guard)
    provider = OpenAIProvider(model="gpt-test", client=_Client([RuntimeError("second timeout")]))

    result = RecoveryCoordinator(provider, budget_guard=guard).recover(original, _request())

    assert result.status == RECOVERY_DISPATCH_UNCERTAIN
    assert len(guard.state.dispatch_records) == 2
    recovery = next(record for record in guard.state.dispatch_records.values() if record.get("recovery_of") == original.physical_request_id)
    assert recovery["functional_state"] == RESPONSE_MISSING
    assert guard.state.ledger[recovery["reservation_id"]]["status"] == UNCERTAIN_CONSUMED

    second = RecoveryCoordinator(provider, budget_guard=guard).recover(
        type(original).from_dict(recovery), _request()
    )
    assert second.status == RECOVERY_LIMIT_EXHAUSTED
    assert len(guard.state.dispatch_records) == 2


def test_recovery_capability_does_not_change_attempt_identity() -> None:
    guard = _guard("identity")
    original = _uncertain_dispatch(guard)
    before_attempt = guard.state.active_attempt_id
    provider = OpenAIProvider(model="gpt-test", client=_Client([]))

    RecoveryCoordinator(provider, budget_guard=guard, allow_reissue=False).recover(original, _request())

    assert guard.state.active_attempt_id == before_attempt
    assert original.logical_attempt_id == before_attempt
