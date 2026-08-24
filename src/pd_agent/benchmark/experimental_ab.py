"""Isolated, non-official Gemini/Luna mini A/B orchestration contracts.

This module deliberately does not use the official scheduler, runner, or
aggregator.  It owns only the small amount of state needed to compare two
providers without creating F9 benchmark evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from .scheduler import BenchmarkScheduledAttempt


TASK_ID = "F6-T2"
TASK_VERSION = "5"
TARGET_VALID_RUNS = 2
MAX_ATTEMPTS_PER_CELL = 3
MAX_TOTAL_ATTEMPTS = 6
GLOBAL_OPENAI_EXPOSURE_CAP_USD = Decimal("3.00")
CANONICAL_ORDER = ("gemini-0", "luna-0", "luna-1", "gemini-1")


class ExperimentalABStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    INCOMPLETE = "INCOMPLETE"
    RATE_LIMIT_PAUSED = "RATE_LIMIT_PAUSED"
    BUDGET_PAUSED = "BUDGET_PAUSED"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    return value


def _stable_hash(value: Any) -> str:
    payload = json.dumps(_json(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True, kw_only=True)
class ExperimentalABCell:
    provider: str
    model: str
    config_id: str
    config_hash: str
    target_valid_runs: int = TARGET_VALID_RUNS
    max_attempts: int = MAX_ATTEMPTS_PER_CELL
    attempts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def valid(self) -> list[dict[str, Any]]:
        return [item for item in self.attempts if item.get("status") == "COMPLETED" and item.get("outcome") in {"PASS", "FAIL"}]

    @property
    def passes(self) -> int:
        return sum(item.get("outcome") == "PASS" for item in self.valid)

    @property
    def fails(self) -> int:
        return sum(item.get("outcome") == "FAIL" for item in self.valid)

    @property
    def blocked(self) -> int:
        return sum(item.get("status") == "BLOCKED" for item in self.attempts)

    @property
    def invalid(self) -> int:
        return sum(item.get("status") == "INVALID" for item in self.attempts)

    @property
    def complete(self) -> bool:
        return len(self.valid) >= self.target_valid_runs

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "config_id": self.config_id,
                "config_hash": self.config_hash, "target_valid_runs": self.target_valid_runs,
                "max_attempts": self.max_attempts, "attempts": _json(self.attempts)}


@dataclass(slots=True)
class ExperimentalABSchedule:
    attempts: tuple[BenchmarkScheduledAttempt, ...]
    target_valid_runs: int = TARGET_VALID_RUNS
    max_attempts_per_cell: int = MAX_ATTEMPTS_PER_CELL
    scheduling_seed: int = 0

    @classmethod
    def create(cls, *, gemini_config_id: str, gemini_config_hash: str, luna_config_id: str, luna_config_hash: str) -> "ExperimentalABSchedule":
        specs = (("gemini-0", "gemini", gemini_config_id, gemini_config_hash, 0, 0),
                 ("luna-0", "luna", luna_config_id, luna_config_hash, 0, 1),
                 ("luna-1", "luna", luna_config_id, luna_config_hash, 1, 2),
                 ("gemini-1", "gemini", gemini_config_id, gemini_config_hash, 1, 3))
        attempts = tuple(BenchmarkScheduledAttempt(
            scheduled_attempt_id=f"ab-{name}", task_id=TASK_ID, task_version=TASK_VERSION,
            config_id=config_id, config_hash=config_hash, repetition_index=repetition,
            attempt_index=1, scheduling_position=position, replacement=False)
            for name, _provider, config_id, config_hash, repetition, position in specs)
        return cls(attempts=attempts)

    @property
    def hash(self) -> str:
        return _stable_hash({"target_valid_runs": self.target_valid_runs, "max_attempts_per_cell": self.max_attempts_per_cell,
                             "scheduling_seed": self.scheduling_seed, "attempts": [item.to_dict() for item in self.attempts]})

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "task_id": TASK_ID, "task_version": TASK_VERSION,
                "target_valid_runs": self.target_valid_runs, "max_attempts_per_cell": self.max_attempts_per_cell,
                "scheduling_seed": self.scheduling_seed, "canonical_order": list(CANONICAL_ORDER),
                "attempts": [item.to_dict() for item in self.attempts], "schedule_hash": self.hash}

    def append_replacement(self, original: BenchmarkScheduledAttempt) -> BenchmarkScheduledAttempt:
        replacement = BenchmarkScheduledAttempt(
            scheduled_attempt_id=f"ab-{original.config_id}-replacement-{original.attempt_index + 1}",
            task_id=original.task_id, task_version=original.task_version, config_id=original.config_id,
            config_hash=original.config_hash, repetition_index=original.repetition_index,
            attempt_index=original.attempt_index + 1, scheduling_position=len(self.attempts),
            replacement=True, replacement_for_attempt_index=original.attempt_index)
        self.attempts = (*self.attempts, replacement)
        return replacement


@dataclass(slots=True)
class ExperimentalABState:
    execution_id: str
    status: ExperimentalABStatus = ExperimentalABStatus.RUNNING
    pending_attempt_id: str | None = None
    consumed_attempts: int = 0
    replacements: int = 0
    global_openai_exposure_usd: Decimal = Decimal("0.00")
    pause_reason: str | None = None
    run_ids: list[str] = field(default_factory=list)

    def reserve_luna_attempt(self, amount: Decimal = Decimal("1.00")) -> None:
        amount = Decimal(amount)
        projected = self.global_openai_exposure_usd + amount
        if projected > GLOBAL_OPENAI_EXPOSURE_CAP_USD:
            self.status = ExperimentalABStatus.BUDGET_BLOCKED
            self.pause_reason = "global OpenAI exposure cap exceeded before physical request"
            raise RuntimeError(self.pause_reason)
        self.global_openai_exposure_usd = projected

    def pause_rate_limit(self, attempt_id: str, reason: str) -> None:
        self.pending_attempt_id = attempt_id
        self.pause_reason = reason
        self.status = ExperimentalABStatus.RATE_LIMIT_PAUSED

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "experimental": True, "non_official": True,
                "execution_id": self.execution_id, "status": self.status.value,
                "pending_attempt_id": self.pending_attempt_id, "consumed_attempts": self.consumed_attempts,
                "replacements": self.replacements, "global_openai_exposure_usd": str(self.global_openai_exposure_usd),
                "pause_reason": self.pause_reason, "run_ids": list(self.run_ids)}


@dataclass(slots=True)
class ExperimentalABController:
    """Small state machine for one isolated A/B batch."""

    schedule: ExperimentalABSchedule
    state: ExperimentalABState
    cells: dict[str, ExperimentalABCell]
    recorded_attempt_ids: set[str] = field(default_factory=set)

    def next_attempt(self) -> BenchmarkScheduledAttempt | None:
        if self.state.status in {ExperimentalABStatus.RATE_LIMIT_PAUSED, ExperimentalABStatus.BUDGET_PAUSED,
                                 ExperimentalABStatus.BUDGET_BLOCKED, ExperimentalABStatus.COMPLETED}:
            return next((item for item in self.schedule.attempts if item.scheduled_attempt_id == self.state.pending_attempt_id), None)
        return next((item for item in self.schedule.attempts if item.scheduled_attempt_id not in self.recorded_attempt_ids), None)

    def record(self, attempt: BenchmarkScheduledAttempt, summary: Mapping[str, Any]) -> None:
        if attempt.scheduled_attempt_id in self.recorded_attempt_ids:
            raise ValueError("experimental A/B attempt already recorded")
        if self.state.pending_attempt_id and attempt.scheduled_attempt_id != self.state.pending_attempt_id:
            raise ValueError("resume must continue the exact pending attempt")
        cell = self.cells[attempt.config_id]
        normalized = dict(summary)
        cell.attempts.append(normalized)
        self.recorded_attempt_ids.add(attempt.scheduled_attempt_id)
        self.state.consumed_attempts += 1
        self.state.pending_attempt_id = None
        if normalized.get("run_id"):
            self.state.run_ids.append(str(normalized["run_id"]))
        if normalized.get("status") in {"BLOCKED", "INVALID"} and not cell.complete and len(cell.attempts) < cell.max_attempts:
            self.state.replacements += 1
            self.schedule.append_replacement(attempt)
        if all(item.complete for item in self.cells.values()):
            self.state.status = ExperimentalABStatus.COMPLETED
        elif self.state.consumed_attempts >= MAX_TOTAL_ATTEMPTS:
            self.state.status = ExperimentalABStatus.INCOMPLETE

    def pause(self, attempt: BenchmarkScheduledAttempt, *, rate_limit: bool, reason: str) -> None:
        if rate_limit:
            self.state.pause_rate_limit(attempt.scheduled_attempt_id, reason)
        else:
            self.state.status = ExperimentalABStatus.BUDGET_PAUSED
            self.state.pending_attempt_id = attempt.scheduled_attempt_id
            self.state.pause_reason = reason


def validate_ab_configs(configs: list[Any]) -> None:
    if len(configs) != 2:
        raise ValueError("experimental A/B requires exactly Gemini and Luna configs")
    providers = {str(item.provider).casefold() for item in configs}
    if providers != {"gemini", "openai"}:
        raise ValueError("A/B providers must be exactly gemini and openai")
    for config in configs:
        if not config.brain_enabled:
            raise ValueError("Brain must remain enabled for both A/B cells")
        if config.provider.casefold() == "gemini" and config.model != "gemini-3.5-flash-lite":
            raise ValueError("Gemini model drift")
        if config.provider.casefold() == "openai" and (config.model != "gpt-5.6-luna" or config.model_config.get("reasoning") != {"effort": "medium"}):
            raise ValueError("Luna model/reasoning drift")


def classify_attempt(*, status: str, outcome: str | None, failure_code: str | None = None) -> dict[str, Any]:
    """Normalize a run summary without turning a valid FAIL into a replacement."""
    if status == "COMPLETED" and outcome in {"PASS", "FAIL"}:
        return {"status": "COMPLETED", "outcome": outcome, "failure_code": failure_code}
    return {"status": status, "outcome": None, "failure_code": failure_code}


def aggregate_experimental_runs(runs: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_provider: dict[str, dict[str, Any]] = {}
    for run in runs:
        provider = str(run["provider"])
        bucket = by_provider.setdefault(provider, {"attempts": 0, "valid": 0, "PASS": 0, "FAIL": 0, "BLOCKED": 0, "INVALID": 0, "cost_usd": None})
        bucket["attempts"] += 1
        status = run.get("status")
        outcome = run.get("outcome")
        if status == "COMPLETED" and outcome in {"PASS", "FAIL"}:
            bucket["valid"] += 1
            bucket[outcome] += 1
        elif status in {"BLOCKED", "INVALID"}:
            bucket[status] += 1
        if provider.casefold() == "openai" and run.get("cost_usd") is not None:
            bucket["cost_usd"] = str(Decimal(str(bucket["cost_usd"] or "0")) + Decimal(str(run["cost_usd"])))
    return {"experimental": True, "non_official": True, "providers": by_provider}


def provider_for_config(config: Any, *, api_key: str, budget_guard: Any | None = None, client: Any | None = None) -> Any:
    """Build a provider; construction is side-effect free and never calls an API."""
    from pd_agent.providers import GeminiProvider, OpenAIProvider

    if config.provider.casefold() == "gemini":
        return GeminiProvider(model=config.model, api_key=api_key, provider_retry_limit=config.execution_limits.provider_retry_limit, client=client)
    if config.provider.casefold() == "openai":
        return OpenAIProvider(model=config.model, api_key=api_key, provider_retry_limit=config.execution_limits.provider_retry_limit, budget_guard=budget_guard, client=client)
    raise ValueError(f"unsupported experimental provider: {config.provider}")
