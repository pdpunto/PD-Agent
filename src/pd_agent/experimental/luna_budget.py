"""Small, experimental hard-budget guard for the non-official Luna smoke."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from pd_agent.core.errors import ProviderError


LUNA_EXPERIMENTAL_HARD_BUDGET_USD = Decimal("1.00")


@dataclass(frozen=True, slots=True)
class LunaPricingSnapshot:
    """Pricing isolated to the experimental Luna smoke."""

    date: str = "2026-08-23"
    model: str = "gpt-5.6-luna"
    processing: str = "Standard"
    short_context_input_per_million: Decimal = Decimal("0.20")
    short_context_cached_input_per_million: Decimal = Decimal("0.02")
    short_context_output_per_million: Decimal = Decimal("1.20")
    long_context_threshold_tokens: int = 272_000
    long_context_input_multiplier: Decimal = Decimal("2.0")
    long_context_output_multiplier: Decimal = Decimal("1.5")
    max_context_tokens: int = 1_050_000
    max_output_tokens: int = 128_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "model": self.model,
            "processing": self.processing,
            "short_context_input_per_million": float(self.short_context_input_per_million),
            "short_context_cached_input_per_million": float(self.short_context_cached_input_per_million),
            "short_context_output_per_million": float(self.short_context_output_per_million),
            "long_context_threshold_tokens": self.long_context_threshold_tokens,
            "long_context_input_multiplier": float(self.long_context_input_multiplier),
            "long_context_output_multiplier": float(self.long_context_output_multiplier),
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_tokens_billed_as": "output",
        }


@dataclass(slots=True)
class LunaBudgetGuard:
    """Fail-closed accounting and pre-request reservation for one smoke."""

    hard_budget_usd: Decimal = LUNA_EXPERIMENTAL_HARD_BUDGET_USD
    pricing: LunaPricingSnapshot = field(default_factory=LunaPricingSnapshot)
    accumulated_cost_usd: Decimal = Decimal("0")
    physical_request_count: int = 0
    provider_retry_count: int = 0
    logical_provider_turn_count: int = 0
    last_reserve: Decimal | None = None
    last_decision: str | None = None
    abort_reason: str | None = None
    response_records: list[dict[str, Any]] = field(default_factory=list)

    def begin_logical_turn(self) -> None:
        self.logical_provider_turn_count += 1

    def before_request(self, payload: Mapping[str, Any], *, retry_count: int) -> dict[str, Any]:
        if self.abort_reason is not None:
            raise self._blocked(self.abort_reason)
        self._validate_state(retry_count=retry_count)
        input_tokens = self._conservative_input_tokens(payload)
        if input_tokens > self.pricing.max_context_tokens:
            raise self._abort("CONTEXT_BOUND_UNDETERMINED")
        reserve = self._worst_case_cost(input_tokens)
        remaining = self.hard_budget_usd - self.accumulated_cost_usd
        self.last_reserve = reserve
        self.last_decision = "ALLOW" if reserve <= remaining else "BLOCK"
        if reserve > remaining:
            raise self._abort("BUDGET_BLOCKED")
        self.physical_request_count += 1
        self.provider_retry_count = retry_count
        return {
            "physical_request_count": self.physical_request_count,
            "provider_retry_count": self.provider_retry_count,
            "input_tokens_estimate": input_tokens,
            "projected_worst_case_cost_usd": float(reserve),
            "accumulated_cost_usd": float(self.accumulated_cost_usd),
            "remaining_budget_usd": float(remaining),
            "decision": self.last_decision,
        }

    def account_response(self, usage: Any) -> dict[str, Any]:
        normalized = self._usage_mapping(usage)
        input_tokens = self._required_int(normalized, "input_tokens")
        output_tokens = self._required_int(normalized, "output_tokens")
        total_tokens = self._required_int(normalized, "total_tokens")
        if total_tokens != input_tokens + output_tokens:
            raise self._abort("INCOHERENT_USAGE")
        cached_tokens = self._nested_int(normalized, "input_tokens_details", "cached_tokens")
        if cached_tokens is None:
            cached_tokens = normalized.get("cached_input_tokens", 0)
        reasoning_tokens = self._nested_int(normalized, "output_tokens_details", "reasoning_tokens")
        if reasoning_tokens is None:
            reasoning_tokens = normalized.get("reasoning_tokens", 0)
        if not isinstance(cached_tokens, int) or not isinstance(reasoning_tokens, int):
            raise self._abort("INCOHERENT_USAGE")
        if cached_tokens < 0 or cached_tokens > input_tokens or reasoning_tokens < 0 or reasoning_tokens > output_tokens:
            raise self._abort("INCOHERENT_USAGE")
        long_context = input_tokens > self.pricing.long_context_threshold_tokens
        input_rate = self.pricing.short_context_input_per_million
        cached_rate = self.pricing.short_context_cached_input_per_million
        output_rate = self.pricing.short_context_output_per_million
        if long_context:
            input_rate *= self.pricing.long_context_input_multiplier
            cached_rate *= self.pricing.long_context_input_multiplier
            output_rate *= self.pricing.long_context_output_multiplier
        uncached_tokens = input_tokens - cached_tokens
        derived = (
            Decimal(uncached_tokens) / Decimal(1_000_000) * input_rate
            + Decimal(cached_tokens) / Decimal(1_000_000) * cached_rate
            + Decimal(output_tokens) / Decimal(1_000_000) * output_rate
        )
        self.accumulated_cost_usd += derived
        if self.accumulated_cost_usd > self.hard_budget_usd:
            raise self._abort("ACCUMULATED_COST_EXCEEDED")
        record = {
            "input_tokens": input_tokens,
            "cached_tokens": cached_tokens,
            "uncached_input_tokens": uncached_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "long_context": long_context,
            "derived_cost_usd": float(derived),
            "accumulated_cost_usd": float(self.accumulated_cost_usd),
            "remaining_budget_usd": float(self.hard_budget_usd - self.accumulated_cost_usd),
        }
        self.response_records.append(record)
        return record

    def on_failure_without_usage(self, *, retry_count: int) -> None:
        self.provider_retry_count = retry_count
        raise self._abort("UNKNOWN_BILLABLE_USAGE")

    def metadata(self) -> dict[str, Any]:
        return {
            "experimental": True,
            "non_official": True,
            "hard_budget_usd": float(self.hard_budget_usd),
            "pricing_snapshot": self.pricing.to_dict(),
            "logical_provider_turn_count": self.logical_provider_turn_count,
            "physical_request_count": self.physical_request_count,
            "provider_retry_count": self.provider_retry_count,
            "accumulated_cost_usd": float(self.accumulated_cost_usd),
            "remaining_budget_usd": float(self.hard_budget_usd - self.accumulated_cost_usd),
            "last_reserve_usd": float(self.last_reserve) if self.last_reserve is not None else None,
            "last_budget_decision": self.last_decision,
            "abort_reason": self.abort_reason,
        }

    def _conservative_input_tokens(self, payload: Mapping[str, Any]) -> int:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return len(encoded)

    def _worst_case_cost(self, input_tokens: int) -> Decimal:
        long_context = input_tokens > self.pricing.long_context_threshold_tokens
        input_rate = self.pricing.short_context_input_per_million
        output_rate = self.pricing.short_context_output_per_million
        if long_context:
            input_rate *= self.pricing.long_context_input_multiplier
            output_rate *= self.pricing.long_context_output_multiplier
        return (
            Decimal(input_tokens) / Decimal(1_000_000) * input_rate
            + Decimal(self.pricing.max_output_tokens) / Decimal(1_000_000) * output_rate
        )

    def _validate_state(self, *, retry_count: int) -> None:
        if retry_count < 0 or retry_count > self.physical_request_count:
            raise self._abort("PHYSICAL_COUNTER_INCOHERENT")
        if self.accumulated_cost_usd < 0 or self.accumulated_cost_usd > self.hard_budget_usd:
            raise self._abort("ACCUMULATED_COST_EXCEEDED")

    def _usage_mapping(self, usage: Any) -> dict[str, Any]:
        if isinstance(usage, Mapping):
            return dict(usage)
        if hasattr(usage, "model_dump") and callable(usage.model_dump):
            dumped = usage.model_dump()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        if hasattr(usage, "to_dict") and callable(usage.to_dict):
            dumped = usage.to_dict()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        raise self._abort("UNKNOWN_BILLABLE_USAGE")

    def _nested_int(self, value: Mapping[str, Any], parent: str, key: str) -> int | None:
        child = value.get(parent)
        if isinstance(child, Mapping):
            raw = child.get(key)
            return raw if isinstance(raw, int) and not isinstance(raw, bool) else None
        return None

    def _required_int(self, value: Mapping[str, Any], key: str) -> int:
        raw = value.get(key)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            raise self._abort("UNKNOWN_BILLABLE_USAGE")
        return raw

    def _abort(self, reason: str) -> ProviderError:
        self.abort_reason = reason
        return ProviderError(
            f"experimental Luna budget guard blocked: {reason}",
            kind="budget_blocked",
            provider="openai",
            retryable=False,
            details={"experimental": True, "non_official": True, "abort_reason": reason},
        )

    def _blocked(self, reason: str) -> ProviderError:
        return self._abort(reason)


def build_luna_experimental_manifest(*, execution_id: str, run_id: str, launch_root: str, task_id: str, task_version: str) -> dict[str, Any]:
    """Build only safe, non-official identity metadata for a future smoke."""

    return {
        "schema_version": 1,
        "execution_id": execution_id,
        "run_id": run_id,
        "launch_root": launch_root,
        "dataset_id": "PD_AGENT_BENCHMARK_DATASET_V0.5_5",
        "task_id": task_id,
        "task_version": task_version,
        "provider": "openai",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "medium",
        "experimental": True,
        "non_official": True,
        "hard_budget_usd": 1.0,
        "pricing_snapshot": LunaPricingSnapshot().to_dict(),
        "official_repetition": None,
        "official_attempt": None,
        "replacement": False,
    }
