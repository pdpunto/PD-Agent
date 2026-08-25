from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from pd_agent.core import AgentMessage, AgentRequest
from pd_agent.core.errors import ProviderError
from pd_agent.experimental import (
    ABANDONED,
    ACCOUNTED,
    DISPATCH_STARTED,
    RESPONSE_AVAILABLE,
    RESPONSE_MISSING,
    REQUEST_PREPARED,
    RESERVATION_COMMITTED,
    RESPONSE_OBSERVED,
    DispatchRecord,
    LunaBudgetGuard,
    LunaEconomicState,
    LunaEconomicStateStore,
    LunaPricingSnapshot,
    UNCERTAIN_CONSUMED,
)
from pd_agent.providers import OpenAIProvider


def _request() -> AgentRequest:
    return AgentRequest(
        messages=(AgentMessage(role="user", content="hello"),),
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
    def __init__(self, outcome: object, on_create=None) -> None:
        self.outcome = outcome
        self.on_create = on_create
        self.calls = 0
        self.kwargs: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        if self.on_create is not None:
            self.on_create()
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _Client:
    def __init__(self, outcome: object, on_create=None) -> None:
        self.responses = _Responses(outcome, on_create=on_create)

    def with_options(self, **_kwargs):
        return self


def _guard(*, state=None, store=None, callback=None) -> LunaBudgetGuard:
    state = state or LunaEconomicState(execution_id="dispatch-test")
    store = store or LunaEconomicStateStore(state, persist_callback=callback)
    return LunaBudgetGuard(
        state=state,
        state_store=store,
        pricing=LunaPricingSnapshot(max_output_tokens=4096),
    )


def test_physical_identity_and_generation_zero_are_distinct() -> None:
    guard = _guard()
    first = guard.prepare_dispatch({"input": "hello"}, provider="openai", model="gpt-test", retry_count=0)
    second = guard.prepare_dispatch({"input": "hello"}, provider="openai", model="gpt-test", retry_count=0)

    assert first.physical_request_id != second.physical_request_id
    assert first.logical_attempt_id == second.logical_attempt_id
    assert first.recovery_generation == 0
    assert first.recovery_of is None
    assert first.client_correlation_id != first.physical_request_id


def test_fingerprint_is_deterministic_and_semantic_changes_are_visible() -> None:
    guard = _guard()
    first = guard.prepare_dispatch({"input": [{"content": "a", "role": "user"}]}, provider="openai", model="m", retry_count=0)
    same = guard.prepare_dispatch({"input": [{"role": "user", "content": "a"}]}, provider="openai", model="m", retry_count=0)
    changed = guard.prepare_dispatch({"input": [{"role": "user", "content": "b"}]}, provider="openai", model="m", retry_count=0)

    assert first.request_fingerprint == same.request_fingerprint
    assert first.request_fingerprint != changed.request_fingerprint
    assert len(first.request_fingerprint) == 64


def test_dispatch_record_round_trip_and_fail_closed_schema() -> None:
    guard = _guard()
    record = guard.prepare_dispatch({"input": "hello"}, provider="openai", model="m", retry_count=0)
    restored = DispatchRecord.from_dict(record.to_dict())

    assert restored.to_dict() == record.to_dict()
    malformed = record.to_dict()
    malformed.pop("physical_request_id")
    with pytest.raises(ValueError, match="incomplete dispatch schema"):
        DispatchRecord.from_dict(malformed)
    unsupported = record.to_dict()
    unsupported["dispatch_schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported dispatch schema"):
        DispatchRecord.from_dict(unsupported)


def test_incomplete_committed_record_fails_closed() -> None:
    guard = _guard()
    record = guard.prepare_dispatch({"input": "hello"}, provider="openai", model="m", retry_count=0)
    invalid = record.to_dict()
    invalid["dispatch_state"] = RESERVATION_COMMITTED
    invalid["reservation_id"] = None

    with pytest.raises(ValueError, match="reserved dispatch requires"):
        DispatchRecord.from_dict(invalid)


def test_write_ahead_order_is_persisted_before_provider_call() -> None:
    snapshots: list[str] = []

    def persist(payload):
        records = payload.get("dispatch_records", {})
        if records:
            snapshots.append(next(iter(records.values()))["dispatch_state"])

    response = SimpleNamespace(id="resp-1", _request_id="req-1", status="completed", usage=_usage(), output=[])
    guard = _guard(callback=persist)
    client = _Client(response, on_create=lambda: snapshots.append("PROVIDER_CALL"))
    OpenAIProvider(model="gpt-test", client=client, budget_guard=guard).execute(_request())

    assert snapshots.index(REQUEST_PREPARED) < snapshots.index(RESERVATION_COMMITTED)
    assert snapshots.index(RESERVATION_COMMITTED) < snapshots.index(DISPATCH_STARTED)
    assert snapshots.index(DISPATCH_STARTED) < snapshots.index("PROVIDER_CALL")
    assert snapshots[-1] == RESPONSE_OBSERVED


def test_openai_sends_durable_correlation_header_after_dispatch_started() -> None:
    state = LunaEconomicState(execution_id="header")
    guard = _guard(state=state)
    response = SimpleNamespace(id="resp-header", _request_id="req-header", status="completed", usage=_usage(), output=[])
    client = _Client(response)

    OpenAIProvider(model="gpt-test", client=client, budget_guard=guard).execute(_request())

    record = next(iter(state.dispatch_records.values()))
    assert client.responses.kwargs[0]["extra_headers"] == {
        "X-Client-Request-Id": record["client_correlation_id"],
    }
    assert record["dispatch_state"] == RESPONSE_OBSERVED


def test_success_separates_accounting_from_functional_availability() -> None:
    state = LunaEconomicState(execution_id="success-split")
    guard = _guard(state=state)
    response = SimpleNamespace(id="resp-1", _request_id="req-1", status="completed", usage=_usage(), output=[])

    OpenAIProvider(model="gpt-test", client=_Client(response), budget_guard=guard).execute(_request())

    record = next(iter(state.dispatch_records.values()))
    assert record["functional_state"] == RESPONSE_AVAILABLE
    assert next(iter(state.ledger.values()))["status"] == ACCOUNTED


def test_ambiguous_failure_separates_missing_response_from_uncertain_billing() -> None:
    state = LunaEconomicState(execution_id="missing-split")
    guard = _guard(state=state)

    with pytest.raises(ProviderError):
        OpenAIProvider(model="gpt-test", client=_Client(RuntimeError("transport")), budget_guard=guard).execute(_request())

    record = next(iter(state.dispatch_records.values()))
    assert record["functional_state"] == RESPONSE_MISSING
    assert next(iter(state.ledger.values()))["status"] == UNCERTAIN_CONSUMED
    assert next(iter(state.ledger.values()))["actual_billed_cost_usd"] is None


def test_pre_dispatch_abandonment_is_functional_only() -> None:
    client = _Client(SimpleNamespace(id="never", usage=_usage(), output=[]))
    state = LunaEconomicState(
        execution_id="abandoned",
        global_ceiling_usd=Decimal("0.000001"),
        attempt_ceiling_usd=Decimal("0.000001"),
    )
    guard = LunaBudgetGuard(
        hard_budget_usd=Decimal("0.000001"),
        state=state,
        state_store=LunaEconomicStateStore(state),
        pricing=LunaPricingSnapshot(max_output_tokens=4096),
    )

    with pytest.raises(ProviderError):
        OpenAIProvider(model="gpt-test", client=client, budget_guard=guard).execute(_request())

    record = next(iter(state.dispatch_records.values()))
    assert record["functional_state"] == ABANDONED
    assert state.global_uncertain_consumed_usd == Decimal("0")
    assert state.global_accumulated_usd == Decimal("0")


def test_invalid_functional_transition_fails_closed() -> None:
    guard = _guard()
    record = guard.prepare_dispatch({"input": "hello"}, provider="openai", model="m", retry_count=0)
    guard.before_request({"input": "hello"}, retry_count=0, dispatch_record=record)
    guard.mark_dispatch_started(record)
    record.functional_state = RESPONSE_AVAILABLE
    guard.state.dispatch_records[record.physical_request_id] = record.to_dict()

    with pytest.raises(ProviderError) as error:
        guard.record_dispatch_result(record, completed=False)

    assert error.value.details["abort_reason"] == "FUNCTIONAL_STATE_TRANSITION_INVALID"


def test_dispatch_record_reservation_matches_economic_ledger() -> None:
    guard = _guard()
    decision = guard.before_request({"input": "hello"}, retry_count=0)
    record = next(iter(guard.state.dispatch_records.values()))

    assert record["reservation_id"] == decision["request_id"]
    assert record["reserved_cost"] == guard.state.ledger[decision["request_id"]]["reservation_usd"]
    assert record["dispatch_state"] == RESERVATION_COMMITTED


def test_dispatch_identity_mismatch_fails_closed() -> None:
    guard = _guard()
    record = guard.prepare_dispatch({"input": "hello"}, provider="openai", model="m", retry_count=0)
    record.logical_attempt_id = "different-attempt"

    with pytest.raises(ProviderError) as error:
        guard.before_request({"input": "hello"}, retry_count=0, dispatch_record=record)

    assert error.value.details["abort_reason"] == "DISPATCH_RECORD_IDENTITY_MISMATCH"


def test_success_captures_provider_metadata_and_persists_evidence(tmp_path) -> None:
    state = LunaEconomicState(execution_id="metadata")
    store = LunaEconomicStateStore(state, path=tmp_path / "economic-state.json")
    guard = _guard(state=state, store=store)
    response = SimpleNamespace(id="resp-1", _request_id="req-1", status="completed", usage=_usage(), output=[])

    OpenAIProvider(model="gpt-test", client=_Client(response), budget_guard=guard).execute(_request())
    restored = LunaEconomicStateStore.load(tmp_path / "economic-state.json").state
    record = next(iter(restored.dispatch_records.values()))

    assert record["provider_request_id"] == "req-1"
    assert record["provider_response_id"] == "resp-1"
    assert record["response_status"] == "completed"
    assert record["dispatch_state"] == RESPONSE_OBSERVED


def test_provider_response_id_cannot_be_reused_by_another_dispatch() -> None:
    state = LunaEconomicState(execution_id="response-id")
    guard = _guard(state=state)
    first = guard.prepare_dispatch({"input": "one"}, provider="openai", model="m", retry_count=0)
    guard.before_request({"input": "one"}, retry_count=0, dispatch_record=first)
    guard.mark_dispatch_started(first)
    guard.record_dispatch_result(first, provider_response_id="resp-1", completed=True)

    second = guard.prepare_dispatch({"input": "two"}, provider="openai", model="m", retry_count=0)
    guard.before_request({"input": "two"}, retry_count=0, dispatch_record=second)
    guard.mark_dispatch_started(second)
    with pytest.raises(ProviderError) as error:
        guard.record_dispatch_result(second, provider_response_id="resp-1", completed=True)

    assert error.value.details["abort_reason"] == "PROVIDER_RESPONSE_ID_REUSED"


def test_ambiguous_failure_keeps_started_evidence_and_redacts_secret() -> None:
    secret = "super-secret-key"
    state = LunaEconomicState(execution_id="failure")
    store = LunaEconomicStateStore(state)
    guard = LunaBudgetGuard(
        state=state,
        state_store=store,
        pricing=LunaPricingSnapshot(max_output_tokens=4096),
        # The provider owns the redactor; this assertion checks persisted normalized fields.
    )
    with pytest.raises(ProviderError):
        OpenAIProvider(
            model="gpt-test",
            client=_Client(RuntimeError(secret)),
            budget_guard=guard,
            api_key=secret,
        ).execute(_request())

    record = next(iter(state.dispatch_records.values()))
    serialized = json.dumps(record)
    assert record["dispatch_state"] == DISPATCH_STARTED
    assert record["dispatch_started_at"] is not None
    assert secret not in serialized


def test_budget_block_has_no_false_dispatched_record() -> None:
    client = _Client(SimpleNamespace(id="never", usage=_usage(), output=[]))
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.000001"))

    with pytest.raises(ProviderError):
        OpenAIProvider(model="gpt-test", client=client, budget_guard=guard).execute(_request())

    assert client.responses.calls == 0
    record = next(iter(guard.state.dispatch_records.values()))
    assert record["dispatch_state"] == REQUEST_PREPARED
    assert record["dispatch_started_at"] is None


def test_legacy_state_without_dispatch_records_remains_loadable() -> None:
    state = LunaEconomicState(execution_id="legacy")
    payload = state.to_dict()
    payload.pop("dispatch_records")

    restored = LunaEconomicState.from_dict(payload)

    assert restored.dispatch_records == {}
    assert restored.reconciliation_state == "CLEAR"


def test_r1_dispatch_schema_loads_as_waiting_without_heuristic_recovery() -> None:
    guard = _guard()
    record = guard.prepare_dispatch({"input": "hello"}, provider="openai", model="m", retry_count=0)
    legacy = record.to_dict()
    legacy["dispatch_schema_version"] = 1
    legacy.pop("functional_state")

    restored = DispatchRecord.from_dict(legacy)

    assert restored.schema_version == 1
    assert restored.functional_state == "WAITING"
