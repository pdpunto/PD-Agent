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


def test_request_is_allowed_and_usage_is_accounted() -> None:
    guard = LunaBudgetGuard()
    decision = guard.before_request({"input": [{"role": "user", "content": "hello"}]}, retry_count=0)
    record = guard.account_response(_usage())

    assert decision["decision"] == "ALLOW"
    assert record["uncached_input_tokens"] == 100
    assert record["reasoning_tokens"] == 10
    assert guard.accumulated_cost_usd < Decimal("1.00")


def test_configured_budget_is_used_for_guard_and_accounting() -> None:
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.25"))
    guard.before_request({"input": []}, retry_count=0)
    record = guard.account_response(_usage(input_tokens=1_000, output_tokens=500))

    assert guard.hard_budget_usd == Decimal("0.25")
    assert record["remaining_budget_usd"] == pytest.approx(0.2492)
    assert guard.metadata()["hard_budget_usd"] == 0.25
    manifest = build_luna_experimental_manifest(
        execution_id="execution",
        run_id="run",
        launch_root="C:/temp/luna",
        task_id="F6-T2",
        task_version="5",
        hard_budget_usd=Decimal("0.25"),
    )
    assert manifest["hard_budget_usd"] == 0.25


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
    guard = LunaBudgetGuard()
    guard.before_request({"input": []}, retry_count=0)
    record = guard.account_response(_usage(input_tokens=1_000, output_tokens=500, cached_tokens=800, reasoning_tokens=500))

    expected = Decimal("200") / Decimal("1_000_000") * Decimal("0.20") + Decimal("800") / Decimal("1_000_000") * Decimal("0.02") + Decimal("500") / Decimal("1_000_000") * Decimal("1.20")
    assert Decimal(str(record["derived_cost_usd"])) == expected


def test_cache_write_is_accounted_at_official_multiplier() -> None:
    guard = LunaBudgetGuard()
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
    guard = LunaBudgetGuard()
    guard.before_request({"input": []}, retry_count=0)
    record = guard.account_response(_usage(input_tokens=300_000, output_tokens=1_000))

    assert record["long_context"] is True
    assert Decimal(str(record["derived_cost_usd"])) == Decimal("0.1218")


def test_reservation_uses_cache_write_worst_case() -> None:
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.25"))
    payload = {"input": []}
    decision = guard.before_request(payload, retry_count=0)

    input_tokens = guard._conservative_input_tokens(payload)
    expected = (
        Decimal(input_tokens) / Decimal("1_000_000") * Decimal("0.20") * Decimal("1.25")
        + Decimal("128000") / Decimal("1_000_000") * Decimal("1.20")
    )
    assert Decimal(str(decision["projected_worst_case_cost_usd"])) == expected
    assert decision["decision"] == "ALLOW"


def test_reservation_equal_remaining_allows_and_greater_blocks() -> None:
    payload = {"input": []}
    reference = LunaBudgetGuard()
    reserve = reference._worst_case_cost(reference._conservative_input_tokens(payload))

    equal = LunaBudgetGuard(hard_budget_usd=reserve)
    assert equal.before_request(payload, retry_count=0)["decision"] == "ALLOW"

    greater = LunaBudgetGuard(hard_budget_usd=reserve - Decimal("0.0000001"))
    with pytest.raises(ProviderError) as error:
        greater.before_request(payload, retry_count=0)
    assert error.value.details["abort_reason"] == "BUDGET_BLOCKED"


def test_retry_is_checked_by_guard() -> None:
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.10"))
    with pytest.raises(ProviderError):
        guard.before_request({"input": []}, retry_count=0)
    assert guard.physical_request_count == 0


def test_retry_uses_same_configured_budget() -> None:
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.25"))
    guard.before_request({"input": []}, retry_count=0)
    guard.account_response(_usage(input_tokens=1_000, output_tokens=500))
    decision = guard.before_request({"input": []}, retry_count=1)

    assert decision["remaining_budget_usd"] < 0.25
    assert guard.hard_budget_usd == Decimal("0.25")


def test_missing_usage_fails_closed() -> None:
    guard = LunaBudgetGuard()
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
    guard = LunaBudgetGuard()
    guard.before_request({"input": []}, retry_count=0)
    with pytest.raises(ProviderError) as error:
        guard.account_response(usage)
    assert error.value.details["abort_reason"] == reason


def test_physical_counter_incoherence_fails_closed() -> None:
    guard = LunaBudgetGuard()
    with pytest.raises(ProviderError) as error:
        guard.before_request({"input": []}, retry_count=1)
    assert error.value.details["abort_reason"] == "PHYSICAL_COUNTER_INCOHERENT"


def test_failed_request_without_usage_blocks_retries() -> None:
    guard = LunaBudgetGuard()
    guard.before_request({"input": []}, retry_count=0)
    with pytest.raises(ProviderError) as error:
        guard.on_failure_without_usage(retry_count=0)
    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"
    assert guard.abort_reason == "UNKNOWN_BILLABLE_USAGE"


def test_context_bound_fails_closed_when_conservative_bytes_exceed_model_limit() -> None:
    guard = LunaBudgetGuard()
    oversized = {"input": [{"role": "user", "content": "x" * 1_100_000}]}
    with pytest.raises(ProviderError) as error:
        guard.before_request(oversized, retry_count=0)
    assert error.value.details["abort_reason"] == "CONTEXT_BOUND_UNDETERMINED"


def test_metadata_is_experimental_and_contains_no_secret_or_encrypted_reasoning() -> None:
    guard = LunaBudgetGuard()
    guard.begin_logical_turn()
    metadata = guard.metadata()
    serialized = json.dumps(metadata)

    assert metadata["experimental"] is True
    assert metadata["non_official"] is True
    assert "OPENAI_API_KEY" not in serialized
    assert "encrypted_content" not in serialized


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
    guard = LunaBudgetGuard()
    result = OpenAIProvider(model="gpt-5.6-luna", client=client, budget_guard=guard).execute(_request())

    assert client.responses.calls == 1
    assert result.provider_metadata["experimental"] is True
    assert result.provider_metadata["physical_request_count"] == 1
    assert result.usage["derived_cost_usd"] > 0


def test_provider_budget_block_happens_before_responses_create() -> None:
    client = _Client(response=SimpleNamespace(usage=_usage(), output=[]))
    guard = LunaBudgetGuard(hard_budget_usd=Decimal("0.10"))

    with pytest.raises(ProviderError) as error:
        OpenAIProvider(model="gpt-5.6-luna", client=client, budget_guard=guard).execute(_request())

    assert error.value.kind == "budget_blocked"
    assert client.responses.calls == 0


def test_provider_failure_without_usage_does_not_retry_with_budget_guard() -> None:
    client = _Client(error=RuntimeError("transport failure"))
    guard = LunaBudgetGuard()

    with pytest.raises(ProviderError) as error:
        OpenAIProvider(model="gpt-5.6-luna", client=client, budget_guard=guard).execute(_request())

    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"
    assert client.responses.calls == 1
