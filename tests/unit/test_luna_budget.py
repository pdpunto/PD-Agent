from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.core.errors import ProviderError
from pd_agent.core import AgentMessage, AgentRequest
from pd_agent.experimental import (
    LunaBudgetGuard,
    LunaEconomicState,
    LunaEconomicStateStore,
    LunaSharedBudgetSession,
    LunaPricingSnapshot,
    build_luna_experimental_manifest,
)
from pd_agent.providers import OpenAIProvider


class _Responses:
    def __init__(self, response=None, error=None) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


class _Client:
    def __init__(self, response=None, error=None) -> None:
        self.responses = _Responses(response=response, error=error)


def _request() -> AgentRequest:
    return AgentRequest(messages=(AgentMessage(role="user", content="hello"),), model_config={"model": "gpt-5.6-luna"})


def _usage(input_tokens: int = 100, output_tokens: int = 50, cached_tokens: int = 0, reasoning_tokens: int = 10) -> dict:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_tokens_details": {"cached_tokens": cached_tokens, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
    }


def _guard(**kwargs) -> LunaBudgetGuard:
    kwargs.setdefault("pricing", LunaPricingSnapshot(max_output_tokens=4_096))
    return LunaBudgetGuard(**kwargs)


def test_request_is_allowed_and_usage_is_accounted() -> None:
    guard = _guard()
    decision = guard.before_request({"input": [{"role": "user", "content": "hello"}]}, retry_count=0)
    record = guard.account_response(_usage())

    assert decision["decision"] == "ALLOW"
    assert record["uncached_input_tokens"] == 100
    assert record["reasoning_tokens"] == 10
    assert guard.accumulated_cost_usd < Decimal("1.00")


def test_configured_budget_is_used_for_guard_and_accounting() -> None:
    guard = _guard(hard_budget_usd=Decimal("0.25"))
    guard.before_request({"input": []}, retry_count=0)
    record = guard.account_response(_usage(input_tokens=1_000, output_tokens=500))

    assert guard.hard_budget_usd == Decimal("0.25")
    assert Decimal(record["remaining_budget_usd"]) == Decimal("0.2492")
    assert guard.metadata()["hard_budget_usd"] == "0.25"
    manifest = build_luna_experimental_manifest(
        execution_id="execution",
        run_id="run",
        launch_root="C:/temp/luna",
        task_id="F6-T2",
        task_version="5",
        hard_budget_usd=Decimal("0.25"),
    )
    assert manifest["hard_budget_usd"] == "0.25"


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-0.25"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_guard_rejects_invalid_budget(value: Decimal) -> None:
    with pytest.raises(ValueError):
        LunaBudgetGuard(hard_budget_usd=value)


def test_next_request_is_blocked_before_send() -> None:
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.10"))

    with pytest.raises(ProviderError) as error:
        guard.before_request({"input": [{"role": "user", "content": "hello"}]}, retry_count=0)

    assert error.value.kind == "budget_blocked"
    assert error.value.details["abort_reason"] == "BUDGET_BLOCKED"


def test_cached_input_pricing_is_lower_and_reasoning_is_not_double_charged() -> None:
    guard = _guard()
    guard.before_request({"input": []}, retry_count=0)
    record = guard.account_response(_usage(input_tokens=1_000, output_tokens=500, cached_tokens=800, reasoning_tokens=500))

    expected = Decimal("200") / Decimal("1_000_000") * Decimal("0.20") + Decimal("800") / Decimal("1_000_000") * Decimal("0.02") + Decimal("500") / Decimal("1_000_000") * Decimal("1.20")
    assert Decimal(str(record["derived_cost_usd"])) == expected


def test_cache_write_is_accounted_at_official_multiplier() -> None:
    guard = _guard()
    guard.before_request({"input": []}, retry_count=0)
    usage = _usage(input_tokens=1_000, output_tokens=500)
    usage["input_tokens_details"]["cache_write_tokens"] = 200
    record = guard.account_response(usage)

    expected = (
        Decimal("800") / Decimal("1_000_000") * Decimal("0.20")
        + Decimal("200") / Decimal("1_000_000") * Decimal("0.20") * Decimal("1.25")
        + Decimal("500") / Decimal("1_000_000") * Decimal("1.20")
    )
    assert Decimal(str(record["derived_cost_usd"])) == expected
    assert record["cache_write_tokens"] == 200


def test_long_context_pricing_applies_to_input_and_output() -> None:
    guard = _guard()
    guard.state.attempt_ceiling_usd = Decimal("0.25")
    guard.before_request({"input": "x" * 300_000}, retry_count=0)
    record = guard.account_response(_usage(input_tokens=300_000, output_tokens=1_000))

    assert record["long_context"] is True
    assert Decimal(str(record["derived_cost_usd"])) == Decimal("0.1218")


def test_reservation_uses_cache_write_worst_case() -> None:
    guard = _guard(hard_budget_usd=Decimal("0.25"))
    payload = {"input": []}
    decision = guard.before_request(payload, retry_count=0)

    input_tokens = guard._conservative_input_tokens(payload)
    expected = (
        Decimal(input_tokens) / Decimal("1_000_000") * Decimal("0.20") * Decimal("1.25")
        + Decimal("4096") / Decimal("1_000_000") * Decimal("1.20")
    )
    assert Decimal(str(decision["projected_worst_case_cost_usd"])) == expected
    assert decision["decision"] == "ALLOW"


def test_reservation_equal_remaining_allows_and_greater_blocks() -> None:
    payload = {"input": []}
    reference = _guard()
    reserve = reference._worst_case_cost(reference._conservative_input_tokens(payload))

    equal = _guard(hard_budget_usd=reserve)
    assert equal.before_request(payload, retry_count=0)["decision"] == "ALLOW"

    greater = _guard(hard_budget_usd=reserve - Decimal("0.0000001"))
    with pytest.raises(ProviderError) as error:
        greater.before_request(payload, retry_count=0)
    assert error.value.details["abort_reason"] == "BUDGET_BLOCKED"


def test_preview_budget_matches_dispatch_decision_without_mutation() -> None:
    payload = {"input": "x" * 70_000, "max_output_tokens": 16_384}
    guard = _guard(hard_budget_usd=Decimal("0.10"), pricing=LunaPricingSnapshot(max_output_tokens=16_384))
    before = guard.state.to_dict()

    preview = guard.preview_budget(
        input_tokens=guard._conservative_input_tokens(payload),
        output_limit=payload["max_output_tokens"],
        retry_count=0,
    )
    decision = guard.before_request(payload, retry_count=0)

    assert preview["decision"] == decision["decision"] == "ALLOW"
    assert preview["reservation_usd"] == decision["projected_worst_case_cost_usd"]
    assert guard.state.to_dict() != before


def test_preview_budget_blocks_real_second_live_ledger_before_dispatch() -> None:
    guard = LunaBudgetGuard(
        hard_budget_usd=Decimal("0.25"),
        pricing=LunaPricingSnapshot(max_output_tokens=16_384),
        state=LunaEconomicState(
            execution_id="second-live",
            global_ceiling_usd=Decimal("0.25"),
            global_accumulated_usd=Decimal("0.1869635500"),
            attempt_accumulated_usd=Decimal("0.0629950500"),
        ),
    )

    preview = guard.preview_budget(input_tokens=70_000, output_limit=16_384)

    assert preview["decision"] == "BLOCK"
    assert preview["abort_reason"] == "BUDGET_BLOCKED"
    assert Decimal(preview["attempt_remaining_usd"]) == Decimal("0.0370049500")



def test_dual_ceiling_boundaries_are_checked_independently() -> None:
    payload = {"input": []}
    reference = _guard()
    reserve = reference._worst_case_cost(reference._conservative_input_tokens(payload), payload)

    both_allow_state = LunaEconomicState(
        execution_id="both-allow",
        global_ceiling_usd=reserve,
        attempt_ceiling_usd=reserve,
    )
    both_allow = _guard(hard_budget_usd=reserve, state=both_allow_state)
    assert both_allow.before_request(payload, retry_count=0)["decision"] == "ALLOW"

    attempt_block_state = LunaEconomicState(
        execution_id="attempt-block",
        global_ceiling_usd=reserve * 2,
        attempt_ceiling_usd=reserve - Decimal("0.0000001"),
    )
    attempt_block = _guard(hard_budget_usd=reserve * 2, state=attempt_block_state)
    with pytest.raises(ProviderError):
        attempt_block.before_request(payload, retry_count=0)

    global_block_state = LunaEconomicState(
        execution_id="global-block",
        global_ceiling_usd=reserve - Decimal("0.0000001"),
        attempt_ceiling_usd=reserve * 2,
    )
    global_block = _guard(hard_budget_usd=reserve - Decimal("0.0000001"), state=global_block_state)
    with pytest.raises(ProviderError):
        global_block.before_request(payload, retry_count=0)


def test_initial_admission_blocks_when_attempt_ceiling_exceeds_global_remaining() -> None:
    state = LunaEconomicState(
        execution_id="admission-config",
        global_ceiling_usd=Decimal("0.20"),
        attempt_ceiling_usd=Decimal("0.10"),
        global_accumulated_usd=Decimal("0.15"),
    )
    guard = _guard(state=state, hard_budget_usd=Decimal("0.20"))

    result = guard.preview_initial_admission(input_tokens=1, output_limit=1)

    assert result["readiness_scope"] == "INITIAL_ADMISSION"
    assert result["decision"] == "BLOCK"
    assert result["reason"] == "ATTEMPT_CEILING_EXCEEDS_GLOBAL_REMAINING"
    assert result["full_run_economic_viability"] == "NOT_GUARANTEED"


def test_initial_admission_allows_only_the_initial_gate() -> None:
    guard = _guard(
        hard_budget_usd=Decimal("0.20"),
        state=LunaEconomicState(
            execution_id="admission-allow",
            global_ceiling_usd=Decimal("0.20"),
            attempt_ceiling_usd=Decimal("0.10"),
        )
    )

    result = guard.preview_initial_admission(input_tokens=1, output_limit=1)

    assert result["decision"] == "ALLOW"
    assert result["full_run_economic_viability"] == "NOT_GUARANTEED"


@pytest.mark.parametrize(
    ("attempt_remaining", "global_remaining", "expected"),
    [
        ("0.001", "0.10", "ATTEMPT_REMAINING"),
        ("0.10", "0.001", "GLOBAL_REMAINING"),
        ("0.001", "0.001", "BOTH"),
    ],
)
def test_preview_reports_the_blocking_limit(
    attempt_remaining: str, global_remaining: str, expected: str
) -> None:
    reference = _guard()
    payload = {"input": "x" * 10, "max_output_tokens": 4_096}
    reserve = reference._worst_case_cost(reference._conservative_input_tokens(payload), payload)
    state = LunaEconomicState(
        execution_id=f"blocking-{expected}",
        global_ceiling_usd=Decimal(global_remaining) + reserve,
        attempt_ceiling_usd=Decimal(attempt_remaining) + reserve,
        global_accumulated_usd=reserve,
        attempt_accumulated_usd=reserve,
    )
    guard = _guard(state=state, hard_budget_usd=state.global_ceiling_usd)

    result = guard.preview_budget(
        input_tokens=guard._conservative_input_tokens(payload),
        output_limit=payload["max_output_tokens"],
    )

    assert result["decision"] == "BLOCK"
    assert result["blocking_limit"] == expected


def test_blocked_dispatch_persists_safe_diagnostic_and_reopens(tmp_path: Path) -> None:
    payload = {"input": "x" * 10, "max_output_tokens": 4_096}
    reference = _guard()
    reserve = reference._worst_case_cost(reference._conservative_input_tokens(payload), payload)
    state = LunaEconomicState(
        execution_id="diagnostic",
        global_ceiling_usd=reserve * 2,
        attempt_ceiling_usd=reserve - Decimal("0.0000001"),
    )
    path = tmp_path / "economic.json"
    store = LunaEconomicStateStore(state, path=path)
    guard = _guard(state=state, state_store=store, hard_budget_usd=state.global_ceiling_usd)
    before = state.to_dict()
    record = guard.prepare_dispatch(payload, provider="openai", model="gpt-test", retry_count=0)

    with pytest.raises(ProviderError, match="BUDGET_BLOCKED"):
        guard.before_request(payload, retry_count=0, dispatch_record=record)
    guard.abandon_pre_dispatch(record, reason="economic reservation was not committed")

    persisted = LunaEconomicStateStore.load(path).state
    saved = persisted.dispatch_records[record.physical_request_id]
    diagnostic = saved["budget_diagnostic"]
    assert saved["dispatch_state"] == "REQUEST_PREPARED"
    assert saved["functional_state"] == "ABANDONED"
    assert diagnostic["dispatch_id"] == record.physical_request_id
    assert diagnostic["logical_attempt_id"] == record.logical_attempt_id
    assert diagnostic["provider"] == "openai"
    assert diagnostic["model"] == "gpt-test"
    assert diagnostic["blocking_limit"] == "ATTEMPT_REMAINING"
    assert diagnostic["reservation_usd"] == str(reserve)
    assert diagnostic["attempt_remaining_usd"] == str(reserve - Decimal("0.0000001"))
    assert "input" not in diagnostic
    assert persisted.physical_request_count == 0
    assert persisted.global_reserved_usd == Decimal("0")
    assert persisted.to_dict()["global_accumulated_usd"] == before["global_accumulated_usd"]


def test_global_ceiling_blocks_when_productive_request_exceeds_it() -> None:
    guard = LunaBudgetGuard(
        hard_budget_usd=Decimal("0.15"),
        state=LunaEconomicState(
            execution_id="global-limit",
            global_ceiling_usd=Decimal("0.15"),
            attempt_ceiling_usd=Decimal("0.50"),
        ),
    )

    with pytest.raises(ProviderError) as error:
        guard.before_request({"input": []}, retry_count=0)

    assert error.value.details["abort_reason"] == "BUDGET_BLOCKED"


def test_explicit_stricter_attempt_ceiling_is_respected() -> None:
    guard = LunaBudgetGuard(
        hard_budget_usd=Decimal("0.50"),
        state=LunaEconomicState(
            execution_id="strict-attempt",
            global_ceiling_usd=Decimal("0.50"),
            attempt_ceiling_usd=Decimal("0.10"),
        ),
    )

    with pytest.raises(ProviderError) as error:
        guard.before_request({"input": []}, retry_count=0)

    assert error.value.details["abort_reason"] == "BUDGET_BLOCKED"


def test_retry_is_checked_by_guard() -> None:
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.10"))
    with pytest.raises(ProviderError):
        guard.before_request({"input": []}, retry_count=0)
    assert guard.physical_request_count == 0


def test_official_output_limit_fits_attempt_budget_for_observed_context() -> None:
    pricing = LunaPricingSnapshot(max_output_tokens=16_384)
    guard = LunaBudgetGuard(
        hard_budget_usd=Decimal("0.10"),
        pricing=pricing,
    )

    decision = guard.before_request({"input": "x" * 70_000, "max_output_tokens": 16_384}, retry_count=0)

    assert decision["decision"] == "ALLOW"
    assert Decimal(str(decision["projected_worst_case_cost_usd"])) < Decimal("0.10")


def test_retry_uses_same_configured_budget() -> None:
    guard = _guard(hard_budget_usd=Decimal("0.25"))
    first = guard.prepare_dispatch({"input": []}, provider="fake", model="gpt-test", retry_count=0)
    guard.before_request({"input": []}, retry_count=0, dispatch_record=first)
    guard.mark_dispatch_started(first)
    guard.account_response(_usage(input_tokens=1_000, output_tokens=500))
    second = guard.prepare_dispatch({"input": []}, provider="fake", model="gpt-test", retry_count=1)
    decision = guard.before_request({"input": []}, retry_count=1, dispatch_record=second)

    assert Decimal(decision["remaining_budget_usd"]) < Decimal("0.25")
    assert guard.hard_budget_usd == Decimal("0.25")


def test_missing_usage_fails_closed() -> None:
    guard = _guard()
    guard.before_request({"input": []}, retry_count=0)
    with pytest.raises(ProviderError) as error:
        guard.account_response(None)
    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"


@pytest.mark.parametrize(
    "usage,reason",
    [
        ({"input_tokens": 10, "output_tokens": 2, "total_tokens": 99}, "INCOHERENT_USAGE"),
        ({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "cached_input_tokens": 11}, "INCOHERENT_USAGE"),
        ({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "reasoning_tokens": 3}, "INCOHERENT_USAGE"),
    ],
)
def test_incoherent_usage_fails_closed(usage: dict, reason: str) -> None:
    guard = _guard()
    guard.before_request({"input": []}, retry_count=0)
    with pytest.raises(ProviderError) as error:
        guard.account_response(usage)
    assert error.value.details["abort_reason"] == reason


def test_physical_counter_incoherence_fails_closed() -> None:
    guard = _guard()
    with pytest.raises(ProviderError) as error:
        guard.before_request({"input": []}, retry_count=1)
    assert error.value.details["abort_reason"] == "PHYSICAL_COUNTER_INCOHERENT"


def test_failed_request_without_usage_blocks_retries() -> None:
    guard = _guard()
    guard.before_request({"input": []}, retry_count=0)
    with pytest.raises(ProviderError) as error:
        guard.on_failure_without_usage(retry_count=0)
    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"
    assert guard.abort_reason == "UNKNOWN_BILLABLE_USAGE"


def test_context_bound_fails_closed_when_conservative_bytes_exceed_model_limit() -> None:
    guard = _guard()
    oversized = {"input": [{"role": "user", "content": "x" * 1_100_000}]}
    with pytest.raises(ProviderError) as error:
        guard.before_request(oversized, retry_count=0)
    assert error.value.details["abort_reason"] == "CONTEXT_BOUND_UNDETERMINED"


def test_metadata_is_experimental_and_contains_no_secret_or_encrypted_reasoning() -> None:
    guard = _guard()
    guard.begin_logical_turn()
    metadata = guard.metadata()
    serialized = json.dumps(metadata)

    assert metadata["experimental"] is True
    assert metadata["non_official"] is True
    assert "OPENAI_API_KEY" not in serialized
    assert "encrypted_content" not in serialized


def test_economic_evidence_uses_exact_decimal_text_and_round_trips(tmp_path: Path) -> None:
    state = LunaEconomicState(
        execution_id="exact-money",
        global_ceiling_usd=Decimal("0.10"),
        attempt_ceiling_usd=Decimal("0.10"),
        global_accumulated_usd=Decimal("0.0000000001"),
        attempt_accumulated_usd=Decimal("0.0000000001"),
    )
    store = LunaEconomicStateStore(state, path=tmp_path / "economic-state.json")
    guard = _guard(hard_budget_usd=Decimal("0.10"), state=state, state_store=store)

    metadata = guard.metadata()
    monetary = {key: value for key, value in metadata.items() if key.endswith("_usd") and value is not None}
    assert monetary
    assert all(isinstance(value, str) for value in monetary.values())
    assert metadata["hard_budget_usd"] == "0.10"
    assert metadata["accumulated_cost_usd"] == "0.0000000001"
    assert json.loads(json.dumps(metadata))["accumulated_cost_usd"] == "0.0000000001"

    store.persist()
    restored = LunaEconomicStateStore.load(tmp_path / "economic-state.json")
    assert isinstance(restored.state.global_ceiling_usd, Decimal)


def test_experimental_manifest_is_not_official_schedule_evidence() -> None:
    manifest = build_luna_experimental_manifest(
        execution_id="execution-experimental",
        run_id="run-experimental",
        launch_root="C:/temp/luna",
        task_id="F6-T2",
        task_version="5",
    )

    assert manifest["experimental"] is True
    assert manifest["non_official"] is True
    assert manifest["official_repetition"] is None
    assert manifest["official_attempt"] is None
    assert manifest["replacement"] is False


def test_f6_t2_invariants_and_limits_are_unchanged() -> None:
    task = json.loads(Path("benchmarks/tasks/F6-T2-v5.json").read_text(encoding="utf-8"))
    config = json.loads(Path("benchmarks/configs/f9-official-gemini-3.5-flash-lite-brain-on.json").read_text(encoding="utf-8"))

    assert task["task_id"] == "F6-T2"
    assert task["task_version"] == "5"
    assert task["fixture"]["fixture_identity"] == "3c27fd809429bc57637b3d930733d5cc7c1891073e9307325d30d25058161396"
    assert config["execution_limits"]["max_agent_steps"] == 25
    assert config["execution_limits"]["provider_retry_limit"] == 2
    assert config["execution_limits"]["max_context_bytes"] == 2_000_000


def test_provider_intercepts_physical_request_and_persists_budget_metadata() -> None:
    response = SimpleNamespace(
        id="resp-1",
        model="gpt-5.6-luna",
        status="completed",
        usage=_usage(),
        output=[],
    )
    client = _Client(response=response)
    guard = _guard()
    result = OpenAIProvider(model="gpt-5.6-luna", client=client, budget_guard=guard).execute(_request())

    assert client.responses.calls == 1
    assert result.provider_metadata["experimental"] is True
    assert result.provider_metadata["physical_request_count"] == 1
    assert Decimal(result.usage["derived_cost_usd"]) > 0


def test_provider_budget_block_happens_before_responses_create() -> None:
    client = _Client(response=SimpleNamespace(usage=_usage(), output=[]))
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.10"))

    with pytest.raises(ProviderError) as error:
        OpenAIProvider(model="gpt-5.6-luna", client=client, budget_guard=guard).execute(_request())

    assert error.value.kind == "budget_blocked"
    assert client.responses.calls == 0


def test_provider_failure_without_usage_does_not_retry_with_budget_guard() -> None:
    client = _Client(error=RuntimeError("transport failure"))
    guard = _guard()

    with pytest.raises(ProviderError) as error:
        OpenAIProvider(model="gpt-5.6-luna", client=client, budget_guard=guard).execute(_request())

    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"
    assert client.responses.calls == 1


def test_economic_state_round_trip_persists_ledger(tmp_path: Path) -> None:
    state = LunaEconomicState(execution_id="execution-1")
    store = LunaEconomicStateStore(state, path=tmp_path / "economic-state.json")
    guard = _guard(state=state, state_store=store)

    guard.begin_attempt("scheduled-1")
    record = guard.prepare_dispatch({"input": []}, provider="fake", model="gpt-test", retry_count=0)
    guard.before_request({"input": []}, retry_count=0, dispatch_record=record)
    guard.mark_dispatch_started(record)
    guard.account_response(_usage(input_tokens=1_000, output_tokens=500))

    restored = LunaEconomicStateStore.load(tmp_path / "economic-state.json").state
    assert restored.execution_id == "execution-1"
    assert restored.physical_request_count == 1
    assert restored.ledger
    assert all(entry["status"] == "ACCOUNTED" for entry in restored.ledger.values())


def test_uncertain_billable_request_is_persisted_and_not_resendable(tmp_path: Path) -> None:
    state = LunaEconomicState(execution_id="execution-2")
    store = LunaEconomicStateStore(state, path=tmp_path / "economic-state.json")
    guard = _guard(state=state, state_store=store)
    guard.before_request({"input": []}, retry_count=0)

    with pytest.raises(ProviderError) as error:
        guard.on_failure_without_usage(retry_count=0)

    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"
    restored = LunaEconomicStateStore.load(tmp_path / "economic-state.json").state
    assert restored.reconciliation_state == "UNCERTAIN_CONSUMED"
    assert restored.pause_reason == "ECONOMIC_BUDGET_BLOCKED"
    assert restored.global_uncertain_consumed_usd > 0
    assert restored.global_reserved_usd == 0
    assert all(entry["status"] == "UNCERTAIN_CONSUMED" for entry in restored.ledger.values())

    with pytest.raises(ProviderError) as blocked:
        guard.before_request({"input": []}, retry_count=1)
    assert blocked.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"


def test_uncertain_consumption_is_not_reported_as_actual_billed_cost() -> None:
    guard = _guard()
    guard.before_request({"input": []}, retry_count=0)
    with pytest.raises(ProviderError):
        guard.on_failure_without_usage(retry_count=0, failure={"message": "transport"})

    metadata = guard.metadata()
    assert metadata["actual_billed_cost_usd"] == "0"
    assert Decimal(metadata["conservative_budget_consumed_usd"]) > 0
    assert Decimal(metadata["remaining_budget_usd"]) < Decimal("1.0")


def test_uncertain_consumed_allows_only_within_remaining_attempt_budget() -> None:
    payload = {"input": [], "max_output_tokens": 1}
    reference = _guard()
    reserve = reference._worst_case_cost(reference._conservative_input_tokens(payload), payload)
    allowed_state = LunaEconomicState(
        execution_id="attempt-allow",
        global_ceiling_usd=Decimal("1.00"),
        attempt_ceiling_usd=Decimal("0.10"),
        attempt_uncertain_consumed_usd=Decimal("0.05"),
        active_attempt_id="active-allow",
    )
    allowed = _guard(state=allowed_state)
    assert allowed.before_request(payload, retry_count=0)["decision"] == "ALLOW"

    blocked_state = LunaEconomicState(
        execution_id="attempt-block",
        global_ceiling_usd=Decimal("1.00"),
        attempt_ceiling_usd=Decimal("0.10"),
        attempt_uncertain_consumed_usd=Decimal("0.10") - reserve / Decimal("2"),
        active_attempt_id="active-block",
    )
    blocked = _guard(state=blocked_state)
    with pytest.raises(ProviderError) as error:
        blocked.before_request(payload, retry_count=0)
    assert error.value.details["abort_reason"] == "BUDGET_BLOCKED"


def test_uncertain_consumed_allows_only_within_remaining_global_budget() -> None:
    payload = {"input": [], "max_output_tokens": 1}
    state = LunaEconomicState(
        execution_id="global-block",
        global_ceiling_usd=Decimal("0.10"),
        attempt_ceiling_usd=Decimal("1.00"),
        global_uncertain_consumed_usd=Decimal("0.099999"),
    )
    guard = _guard(hard_budget_usd=Decimal("0.10"), state=state)
    with pytest.raises(ProviderError) as error:
        guard.before_request(payload, retry_count=0)
    assert error.value.details["abort_reason"] == "BUDGET_BLOCKED"


def test_uncertain_and_accounted_consumption_coexist_without_double_count() -> None:
    state = LunaEconomicState(
        execution_id="coexist",
        global_accumulated_usd=Decimal("0.02"),
        global_uncertain_consumed_usd=Decimal("0.03"),
        attempt_accumulated_usd=Decimal("0.02"),
        attempt_uncertain_consumed_usd=Decimal("0.03"),
    )
    guard = _guard(state=state)
    assert guard.accumulated_cost_usd == Decimal("0.02")
    assert guard.metadata()["actual_billed_cost_usd"] == "0.02"
    assert guard.metadata()["conservative_budget_consumed_usd"] == "0.05"
    assert state.global_remaining_usd == Decimal("0.95")
    assert state.attempt_remaining_usd == Decimal("0.05")


def test_new_attempt_preserves_global_uncertain_consumption() -> None:
    state = LunaEconomicState(
        execution_id="new-attempt",
        global_uncertain_consumed_usd=Decimal("0.05"),
        attempt_uncertain_consumed_usd=Decimal("0.05"),
        active_attempt_id="old",
    )
    state.end_attempt()
    state.begin_attempt("new")
    assert state.global_uncertain_consumed_usd == Decimal("0.05")
    assert state.attempt_uncertain_consumed_usd == Decimal("0")
    assert state.global_remaining_usd == Decimal("0.95")


@pytest.mark.parametrize(
    "field_name",
    ["attempt_accumulated_usd", "attempt_reserved_usd", "attempt_uncertain_consumed_usd"],
)
def test_active_attempt_with_economic_exposure_cannot_be_replaced(field_name: str) -> None:
    state = LunaEconomicState(execution_id=f"active-{field_name}", active_attempt_id="old")
    setattr(state, field_name, Decimal("0.01"))

    with pytest.raises(ValueError, match="cannot replace an active economic attempt"):
        state.begin_attempt("new")

    assert state.active_attempt_id == "old"
    assert getattr(state, field_name) == Decimal("0.01")


def test_incomplete_economic_state_is_rejected_fail_closed() -> None:
    state = LunaEconomicState(execution_id="strict")
    payload = state.to_dict()
    payload.pop("global_uncertain_consumed_usd")
    with pytest.raises(ValueError, match="incomplete economic schema"):
        LunaEconomicState.from_dict(payload)


def test_proven_pre_dispatch_reservation_can_be_released() -> None:
    guard = _guard()
    decision = guard.before_request({"input": []}, retry_count=0)
    released = guard.release_reservation(reason="client rejected before dispatch")

    assert released["status"] == "RELEASED"
    assert guard.state.global_reserved_usd == 0
    assert guard.state.global_uncertain_consumed_usd == 0
    assert guard.state.ledger[decision["request_id"]]["actual_billed_cost_usd"] == "0"


def test_original_provider_failure_is_preserved_in_economic_abort() -> None:
    client = _Client(error=RuntimeError("transport failure"))
    guard = _guard()
    with pytest.raises(ProviderError) as error:
        OpenAIProvider(model="gpt-5.6-luna", client=client, budget_guard=guard).execute(_request())

    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"
    assert error.value.details["original_failure"]["message"] == "transport failure"
    assert guard.state.ledger[next(iter(guard.state.ledger))]["status"] == "UNCERTAIN_CONSUMED"


def test_response_without_usage_is_uncertain_and_not_retried() -> None:
    response = SimpleNamespace(id="resp-no-usage", status="completed", usage=None, output=[])
    client = _Client(response=response)
    guard = _guard()
    with pytest.raises(ProviderError) as error:
        OpenAIProvider(model="gpt-5.6-luna", client=client, budget_guard=guard).execute(_request())

    assert client.responses.calls == 1
    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"
    assert guard.state.reconciliation_state == "UNCERTAIN_CONSUMED"


def test_attempt_ownership_is_durable_and_duplicate_claim_is_rejected(tmp_path: Path) -> None:
    first = _guard(state=LunaEconomicState(execution_id="session"), state_store=None)
    first.state_store = LunaEconomicStateStore(first.state, path=tmp_path / "state.json")
    first.begin_attempt("attempt-1", run_id="run-1", launch_root=tmp_path / "launch", ownership_root=tmp_path / "locks")
    assert first.state.attempt_lifecycle == "ACTIVE"
    assert first.state.attempt_ownership["process_instance_token"]

    other_state = LunaEconomicState(execution_id="session")
    other_store = LunaEconomicStateStore(other_state, path=tmp_path / "other.json")
    other = _guard(state=other_state, state_store=other_store)
    with pytest.raises(ValueError, match="ownership"):
        other.begin_attempt("attempt-2", run_id="run-2", launch_root=tmp_path / "launch", ownership_root=tmp_path / "locks")
    first.end_attempt()


def test_active_attempt_cannot_be_replaced_before_reconciliation() -> None:
    state = LunaEconomicState(execution_id="active", active_attempt_id="old")
    with pytest.raises(ValueError, match="cannot replace"):
        state.begin_attempt("new")


def test_abrupt_termination_reconciliation_preserves_cost_and_history(tmp_path: Path) -> None:
    state = LunaEconomicState(
        execution_id="session",
        global_ceiling_usd=Decimal("1.00"),
        global_accumulated_usd=Decimal("0.03"),
        attempt_accumulated_usd=Decimal("0.03"),
        active_attempt_id="orphan",
        attempt_lifecycle="ACTIVE",
    )
    store = LunaEconomicStateStore(state, path=tmp_path / "state.json")
    session = LunaSharedBudgetSession("session", state, store, ceiling_usd=Decimal("1.00"))
    result = session.reconcile_abandoned_attempt(
        attempt_id="orphan",
        reason="owner terminated",
        evidence={"owner_terminated": True, "dispatch_ambiguity": False},
        explicit_legacy=True,
    )
    assert result["status"] == "ABORTED_RECONCILED"
    assert state.global_accumulated_usd == Decimal("0.03")
    assert state.active_attempt_id is None
    assert state.attempt_lifecycle == "ABORTED_RECONCILED"
    assert len(state.reconciliation_records) == 1
    assert session.reconcile_abandoned_attempt(
        attempt_id="orphan", reason="repeat", evidence={}, explicit_legacy=True
    )["status"] == "ABORTED_RECONCILED"
    assert len(state.reconciliation_records) == 1


def test_reconciliation_rejects_live_owner_and_post_dispatch_ambiguity(tmp_path: Path) -> None:
    state = LunaEconomicState(execution_id="session", active_attempt_id="active", attempt_lifecycle="ACTIVE")
    store = LunaEconomicStateStore(state, path=tmp_path / "state.json")
    guard = _guard(state=state, state_store=store)
    guard.begin_attempt("active", launch_root=tmp_path / "launch", ownership_root=tmp_path / "locks")
    with pytest.raises(ProviderError, match="OWNER_LOCK_STILL_HELD"):
        guard.reconcile_abandoned_attempt(attempt_id="active", reason="test", evidence={})
    guard.end_attempt()

    ambiguous = LunaEconomicState(
        execution_id="ambiguous", active_attempt_id="active", attempt_lifecycle="ACTIVE",
        attempt_reserved_usd=Decimal("0.01"), global_reserved_usd=Decimal("0.01"), pending_request_id="request",
    )
    ambiguous_store = LunaEconomicStateStore(ambiguous, path=tmp_path / "ambiguous.json")
    ambiguous_guard = _guard(state=ambiguous, state_store=ambiguous_store)
    with pytest.raises(ProviderError, match="POST_DISPATCH_AMBIGUITY"):
        ambiguous_guard.reconcile_abandoned_attempt(attempt_id="active", reason="test", evidence={}, explicit_legacy=True)


def test_legacy_orphan_requires_explicit_reconciliation_evidence() -> None:
    state = LunaEconomicState(execution_id="legacy", active_attempt_id="orphan", attempt_lifecycle="ACTIVE")
    guard = _guard(state=state)
    with pytest.raises(ProviderError, match="LEGACY_ORPHAN_REQUIRES_EXPLICIT_EVIDENCE"):
        guard.reconcile_abandoned_attempt(attempt_id="orphan", reason="test", evidence={})


def test_pre_dispatch_reconciliation_releases_only_proven_reservation() -> None:
    guard = _guard()
    decision = guard.before_request({"input": []}, retry_count=0)
    guard.reconcile_abandoned_attempt(
        attempt_id="legacy-attempt",
        reason="cancelled before provider boundary",
        evidence={"dispatch_started": False},
        explicit_legacy=True,
    )
    entry = guard.state.ledger[decision["request_id"]]
    assert entry["status"] == "RELEASED"
    assert guard.state.global_reserved_usd == Decimal("0")
    assert guard.state.attempt_reserved_usd == Decimal("0")
    assert guard.state.global_accumulated_usd == Decimal("0")


def test_owned_stale_attempt_requires_reacquired_lock_and_preserves_metadata(tmp_path: Path) -> None:
    state = LunaEconomicState(execution_id="session", global_ceiling_usd=Decimal("1.00"))
    store = LunaEconomicStateStore(state, path=tmp_path / "state.json")
    owner = LunaBudgetGuard(hard_budget_usd=Decimal("1.00"), state=state, state_store=store)
    launch = tmp_path / "launch"
    locks = tmp_path / "locks"
    owner.begin_attempt("attempt", run_id="run", launch_root=launch, ownership_root=locks)
    owner._ownership.release()
    owner._ownership = None

    restored = LunaSharedBudgetSession.load(store.path)
    result = restored.reconcile_abandoned_attempt(
        attempt_id="attempt",
        run_id="run",
        launch_root=launch,
        reason="owner terminated",
        evidence={"owner_terminated": True, "dispatch_started": False},
    )
    assert result["previous_owner"]["process_instance_token"]
    assert restored.state.global_accumulated_usd == Decimal("0")
    persisted = LunaEconomicStateStore.load(store.path).state
    assert persisted.attempt_lifecycle == "ABORTED_RECONCILED"
    assert persisted.attempt_ownership is None


def test_owned_reconciliation_rejects_incoherent_run_identity(tmp_path: Path) -> None:
    state = LunaEconomicState(execution_id="session", global_ceiling_usd=Decimal("1.00"))
    store = LunaEconomicStateStore(state, path=tmp_path / "state.json")
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("1.00"), state=state, state_store=store)
    guard.begin_attempt("attempt", run_id="run", launch_root=tmp_path / "launch", ownership_root=tmp_path / "locks")
    guard._ownership.release()
    guard._ownership = None
    session = LunaSharedBudgetSession.load(store.path)
    with pytest.raises(ProviderError, match="RUN_OWNERSHIP_MISMATCH"):
        session.reconcile_abandoned_attempt(
            attempt_id="attempt", run_id="other", reason="test", evidence={}
        )
