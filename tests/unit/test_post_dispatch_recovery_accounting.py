from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.core import AgentRequest, AgentResponse
from pd_agent.core.errors import ProviderError
from pd_agent.experimental import (
    ACCOUNTED,
    DISPATCH_STARTED,
    LunaBudgetGuard,
    LunaEconomicState,
    LunaEconomicStateStore,
    LunaPricingSnapshot,
    RELEASED,
    UNCERTAIN_CONSUMED,
)
from pd_agent.providers import (
    ProviderRecoveryCapabilities,
    RECOVERY_BUDGET_BLOCKED,
    RECOVERY_DISPATCH_UNCERTAIN,
    RECOVERY_EXISTING_RESPONSE,
    RECOVERY_LIMIT_EXHAUSTED,
    RECOVERY_PRE_DISPATCH_FAILED,
    RECOVERY_REISSUE_SUCCEEDED,
    RecoveryCoordinator,
    RecoveryResult,
)
from pd_agent.providers.openai_provider import OpenAIProvider


def _usage(*, input_tokens: int = 10, output_tokens: int = 4) -> dict[str, object]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_tokens_details": {"cached_tokens": 2, "cache_write_tokens": 1},
        "output_tokens_details": {"reasoning_tokens": 1},
    }


def _request() -> AgentRequest:
    return AgentRequest(
        messages=(SimpleNamespace(role="user", content="recover"),),
        model_config={"model": "gpt-test", "max_output_tokens": 64},
    )


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


def _guard(execution_id: str = "r8") -> LunaBudgetGuard:
    state = LunaEconomicState(execution_id=execution_id)
    return LunaBudgetGuard(
        state=state,
        state_store=LunaEconomicStateStore(state),
        pricing=LunaPricingSnapshot(max_output_tokens=256),
    )


def _uncertain(guard: LunaBudgetGuard):
    record = guard.prepare_dispatch(
        {"input": "recover", "max_output_tokens": 64},
        provider="openai",
        model="gpt-test",
        retry_count=0,
    )
    guard.before_request(
        {"input": "recover", "max_output_tokens": 64},
        retry_count=0,
        dispatch_record=record,
    )
    guard.mark_dispatch_started(record)
    guard.record_dispatch_result(record, provider_request_id="req-original")
    with pytest.raises(ProviderError):
        guard.on_failure_without_usage(retry_count=0, failure={"kind": "timeout"})
    return record


def _response(response_id: str = "response"):
    return SimpleNamespace(
        id=response_id,
        _request_id=f"request-{response_id}",
        status="completed",
        usage=_usage(),
        output=[],
    )


def test_normal_success_accounts_once_and_counts_one_physical_dispatch() -> None:
    guard = _guard("success")
    result = OpenAIProvider(model="gpt-test", client=_Client([_response()]), budget_guard=guard).execute(_request())

    assert isinstance(result, AgentResponse)
    assert guard.physical_request_count == 1
    assert guard.provider_retry_count == 0
    assert guard.state.global_uncertain_consumed_usd == Decimal("0")
    assert next(iter(guard.state.ledger.values()))["status"] == ACCOUNTED


def test_proven_pre_dispatch_failure_releases_without_physical_consumption() -> None:
    guard = _guard("pre-dispatch")
    record = guard.prepare_dispatch({"input": "never"}, provider="fake", model="m", retry_count=0)
    guard.abandon_pre_dispatch(record, reason="validation failed")

    assert guard.physical_request_count == 0
    assert guard.state.global_reserved_usd == Decimal("0")
    assert guard.state.ledger == {}
    assert guard.state.dispatch_records[record.physical_request_id]["dispatch_state"] == "REQUEST_PREPARED"
    assert guard.state.dispatch_records[record.physical_request_id]["functional_state"] == "ABANDONED"


def test_original_post_dispatch_uncertainty_preserves_conservative_cost_and_started_evidence() -> None:
    guard = _guard("uncertain")
    record = _uncertain(guard)
    entry = guard.state.ledger[record.reservation_id]

    assert guard.physical_request_count == 1
    assert entry["status"] == UNCERTAIN_CONSUMED
    assert entry["actual_billed_cost_usd"] is None
    assert Decimal(entry["conservative_budget_consumed_usd"]) > 0
    assert guard.state.global_uncertain_consumed_usd == Decimal(entry["conservative_budget_consumed_usd"])
    assert guard.state.dispatch_records[record.physical_request_id]["dispatch_state"] == DISPATCH_STARTED


def test_retrieval_uses_existing_response_without_new_accounting() -> None:
    guard = _guard("retrieval")
    original = _uncertain(guard)

    class RetrievalProvider:
        def recovery_capabilities(self):
            return ProviderRecoveryCapabilities(provider="openai", response_retrieval=True)

        def retrieve_response(self, lookup):
            return RecoveryResult(
                status="RECOVERED",
                provider="openai",
                model="gpt-test",
                physical_request_id=lookup.physical_request_id,
                provider_request_id="req-original",
                agent_response=AgentResponse(assistant_message="existing"),
            )

    provider = RetrievalProvider()
    result = RecoveryCoordinator(provider, budget_guard=guard).recover(original, _request())

    assert result.status == RECOVERY_EXISTING_RESPONSE
    assert result.response is not None
    assert guard.physical_request_count == 1
    assert len(guard.state.ledger) == 1
    assert guard.state.global_uncertain_consumed_usd > 0


def test_reissue_success_has_independent_reservation_and_accounts_both_dispatches() -> None:
    guard = _guard("reissue-success")
    original = _uncertain(guard)
    result = RecoveryCoordinator(
        OpenAIProvider(model="gpt-test", client=_Client([_response("recovery")])) ,
        budget_guard=guard,
    ).recover(original, _request())

    recovery = next(
        record for record in guard.state.dispatch_records.values()
        if record.get("recovery_of") == original.physical_request_id
    )
    assert result.status == RECOVERY_REISSUE_SUCCEEDED
    assert guard.physical_request_count == 2
    assert guard.state.ledger[original.reservation_id]["status"] == UNCERTAIN_CONSUMED
    assert guard.state.ledger[recovery["reservation_id"]]["status"] == ACCOUNTED
    assert recovery["reservation_id"] != original.reservation_id
    assert recovery["physical_request_id"] != original.physical_request_id
    assert recovery["client_correlation_id"] != original.client_correlation_id
    assert recovery["recovery_generation"] == 1
    assert recovery["logical_attempt_id"] == original.logical_attempt_id
    assert guard.state.global_uncertain_consumed_usd == Decimal(
        guard.state.ledger[original.reservation_id]["conservative_budget_consumed_usd"]
    )


def test_reissue_second_uncertainty_sums_two_conservative_dispatches_and_is_bounded() -> None:
    guard = _guard("reissue-uncertain")
    original = _uncertain(guard)
    provider = OpenAIProvider(model="gpt-test", client=_Client([RuntimeError("timeout")]))
    result = RecoveryCoordinator(provider, budget_guard=guard).recover(original, _request())

    recovery = next(
        record for record in guard.state.dispatch_records.values()
        if record.get("recovery_of") == original.physical_request_id
    )
    original_amount = Decimal(guard.state.ledger[original.reservation_id]["conservative_budget_consumed_usd"])
    recovery_amount = Decimal(guard.state.ledger[recovery["reservation_id"]]["conservative_budget_consumed_usd"])
    assert result.status == RECOVERY_DISPATCH_UNCERTAIN
    assert guard.physical_request_count == 2
    assert guard.state.ledger[recovery["reservation_id"]]["status"] == UNCERTAIN_CONSUMED
    assert guard.state.global_uncertain_consumed_usd == original_amount + recovery_amount
    assert RecoveryCoordinator(provider, budget_guard=guard).recover(
        type(original).from_dict(recovery), _request()
    ).status == RECOVERY_LIMIT_EXHAUSTED
    assert guard.physical_request_count == 2


def test_reissue_budget_blocked_keeps_original_and_makes_no_new_dispatch() -> None:
    guard = _guard("reissue-budget")
    original = _uncertain(guard)
    guard.state.global_uncertain_consumed_usd = guard.state.global_ceiling_usd
    guard.state.attempt_uncertain_consumed_usd = guard.state.attempt_ceiling_usd
    client = _Client([])

    result = RecoveryCoordinator(
        OpenAIProvider(model="gpt-test", client=client), budget_guard=guard
    ).recover(original, _request())

    assert result.status == RECOVERY_BUDGET_BLOCKED
    assert client.responses.calls == []
    assert guard.physical_request_count == 1
    assert guard.state.ledger[original.reservation_id]["status"] == UNCERTAIN_CONSUMED


def test_recovery_pre_dispatch_failure_is_distinct_from_uncertainty() -> None:
    guard = _guard("reissue-pre-dispatch")
    original = _uncertain(guard)

    class PreDispatchFailureProvider:
        budget_guard = guard

        def execute(self, request):
            record = guard.prepare_dispatch(
                {"input": "recover", "max_output_tokens": 64},
                provider="fake",
                model="gpt-test",
                retry_count=0,
                recovery_generation=1,
                recovery_of=original.physical_request_id,
            )
            guard.abandon_pre_dispatch(record, reason="local validation")
            raise ProviderError("pre-dispatch failure", kind="protocol", provider="fake")

        def recovery_capabilities(self):
            return ProviderRecoveryCapabilities.none("openai")

    result = RecoveryCoordinator(PreDispatchFailureProvider(), budget_guard=guard).recover(original, _request())

    assert result.status == RECOVERY_PRE_DISPATCH_FAILED
    assert guard.physical_request_count == 1
    assert guard.state.global_uncertain_consumed_usd > 0


def test_recovery_does_not_increment_logical_turn_attempt_or_retry_counters() -> None:
    guard = _guard("logical")
    guard.begin_attempt("scheduled-attempt")
    guard.begin_logical_turn()
    original = _uncertain(guard)
    before = (guard.logical_provider_turn_count, guard.state.active_attempt_id, guard.provider_retry_count)

    RecoveryCoordinator(
        OpenAIProvider(model="gpt-test", client=_Client([_response("recovery")])) ,
        budget_guard=guard,
    ).recover(original, _request())

    assert (guard.logical_provider_turn_count, guard.state.active_attempt_id, guard.provider_retry_count) == before


def test_persistence_round_trip_preserves_recovery_totals_and_identities(tmp_path: Path) -> None:
    state = LunaEconomicState(execution_id="round-trip")
    store = LunaEconomicStateStore(state, path=tmp_path / "economic-state.json")
    guard = LunaBudgetGuard(state=state, state_store=store, pricing=LunaPricingSnapshot(max_output_tokens=256))
    original = _uncertain(guard)
    RecoveryCoordinator(
        OpenAIProvider(model="gpt-test", client=_Client([_response("recovery")])) ,
        budget_guard=guard,
    ).recover(original, _request())
    before = state.to_dict()

    restored = LunaEconomicStateStore.load(tmp_path / "economic-state.json").state

    assert restored.to_dict() == before
    assert restored.physical_request_count == 2
    assert restored.global_uncertain_consumed_usd > 0
    assert len(restored.dispatch_records) == 2


def test_duplicate_reservation_identity_is_rejected_fail_closed() -> None:
    guard = _guard("duplicate")
    first = guard.prepare_dispatch({"input": "one"}, provider="fake", model="m", retry_count=0)
    guard.before_request({"input": "one"}, retry_count=0, dispatch_record=first)
    payload = guard.state.to_dict()
    duplicate = dict(payload["dispatch_records"][first.physical_request_id])
    duplicate["physical_request_id"] = "dispatch-duplicate"
    payload["dispatch_records"]["dispatch-duplicate"] = duplicate

    with pytest.raises(ValueError, match="reservation identity reused"):
        LunaEconomicState.from_dict(payload)


def test_duplicate_settlement_is_not_silently_accounted_twice() -> None:
    guard = _guard("settlement-once")
    guard.before_request({"input": []}, retry_count=0)
    first = guard.account_response(_usage())

    with pytest.raises(ProviderError) as error:
        guard.account_response(_usage())

    assert error.value.details["abort_reason"] == "UNKNOWN_RESERVED_REQUEST"
    assert guard.accumulated_cost_usd == Decimal(first["derived_cost_usd"])


def test_prepared_dispatch_has_no_ledger_consumption_until_reservation_commit() -> None:
    guard = _guard("prepared")
    record = guard.prepare_dispatch({"input": "prepared"}, provider="fake", model="m", retry_count=0)

    assert record.reservation_id is None
    assert guard.physical_request_count == 0
    assert guard.state.ledger == {}
    assert guard.state.global_remaining_usd == guard.state.global_ceiling_usd


def test_r8_serialized_evidence_contains_no_secret_or_raw_reasoning() -> None:
    guard = _guard("redaction")
    guard.before_request({"input": "safe"}, retry_count=0)
    metadata = json.dumps(guard.metadata())

    assert "OPENAI_API_KEY" not in metadata
    assert "encrypted_content" not in metadata


def test_release_is_only_available_before_dispatch() -> None:
    guard = _guard("release")
    guard.before_request({"input": []}, retry_count=0)
    released = guard.release_reservation(reason="proven local failure")

    assert released["status"] == RELEASED
    assert guard.state.global_remaining_usd == guard.state.global_ceiling_usd
    assert guard.state.global_uncertain_consumed_usd == Decimal("0")

    with pytest.raises(ProviderError) as error:
        guard.release_reservation(reason="duplicate release")
    assert error.value.details["abort_reason"] == "UNKNOWN_RESERVED_REQUEST"
