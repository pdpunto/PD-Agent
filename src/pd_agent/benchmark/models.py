"""Benchmark foundation models and canonical serialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from pd_agent.core import ExecutionLimits


SCHEMA_VERSION = 1


class BenchmarkSchemaError(ValueError):
    """Raised when a benchmark payload has an unsupported schema."""


class BenchmarkExecutionStatus(StrEnum):
    """Execution status for a benchmark run."""

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"


class BenchmarkTaskOutcome(StrEnum):
    """Task outcome for a benchmark run."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class BenchmarkFailureOrigin(StrEnum):
    """Failure origin classification."""

    AGENT = "AGENT"
    PROVIDER = "PROVIDER"
    BUILD_ENVIRONMENT = "BUILD_ENVIRONMENT"
    MINECRAFT_HARNESS = "MINECRAFT_HARNESS"
    BENCHMARK_INFRA = "BENCHMARK_INFRA"
    CONFIGURATION = "CONFIGURATION"
    UNKNOWN = "UNKNOWN"


class BenchmarkFailureCode(StrEnum):
    """Failure codes used by benchmark runs."""

    AGENT_TASK_FAILURE = "AGENT_TASK_FAILURE"
    AGENT_BUILD_FAILURE = "AGENT_BUILD_FAILURE"
    AGENT_FUNCTIONAL_FAILURE = "AGENT_FUNCTIONAL_FAILURE"
    PROVIDER_AUTH = "PROVIDER_AUTH"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    BUILD_ENV_FAILURE = "BUILD_ENV_FAILURE"
    HARNESS_CRASH = "HARNESS_CRASH"
    HARNESS_TIMEOUT = "HARNESS_TIMEOUT"
    HARNESS_INFRA_ERROR = "HARNESS_INFRA_ERROR"
    EXECUTION_LIMIT = "EXECUTION_LIMIT"
    BENCHMARK_CONTAMINATION = "BENCHMARK_CONTAMINATION"
    UNKNOWN = "UNKNOWN"


class BenchmarkComparisonStatus(StrEnum):
    """Summary status for a benchmark comparison."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    INCONCLUSIVE = "INCONCLUSIVE"


def _is_secret_key(key: object) -> bool:
    text = str(key).casefold()
    return text in {
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "auth_token",
        "bearer_token",
        "client_secret",
        "secret",
        "password",
        "passwd",
        "private_key",
        "token",
    }


def _json_ready(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_ready(value.to_dict())
    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            if not _is_secret_key(key)
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return [_json_ready(item) for item in sorted(value, key=repr)]
    return value


def _canonical_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    return _json_ready(dict(data))


def _canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(_canonical_payload(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema_version_or_raise(data: Mapping[str, Any], *, model: str) -> int:
    raw = data.get("schema_version")
    if raw is None:
        raise BenchmarkSchemaError(f"{model} payload missing schema_version")
    version = int(raw)
    if version != SCHEMA_VERSION:
        raise BenchmarkSchemaError(f"unsupported {model} schema_version: {version}")
    return version


def _non_empty_text(value: Any, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    raise TypeError("expected string sequence")


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkTaskReference:
    """Reference to one benchmark task version."""

    schema_version: int = SCHEMA_VERSION
    task_id: str
    task_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _non_empty_text(self.task_id, field_name="task_id"))
        object.__setattr__(self, "task_version", _non_empty_text(self.task_version, field_name="task_version"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_version": self.task_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkTaskReference":
        _schema_version_or_raise(data, model="BenchmarkTaskReference")
        return cls(task_id=str(data["task_id"]), task_version=str(data["task_version"]))


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkFixtureReference:
    """Reference plus identity for a fixture."""

    schema_version: int = SCHEMA_VERSION
    fixture_ref: str
    fixture_identity: str | None = None
    identity_algorithm: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fixture_ref", _non_empty_text(self.fixture_ref, field_name="fixture_ref"))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.fixture_identity is not None:
            object.__setattr__(self, "fixture_identity", _non_empty_text(self.fixture_identity, field_name="fixture_identity"))
        if self.identity_algorithm is not None:
            object.__setattr__(self, "identity_algorithm", _non_empty_text(self.identity_algorithm, field_name="identity_algorithm"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fixture_ref": self.fixture_ref,
            "fixture_identity": self.fixture_identity,
            "identity_algorithm": self.identity_algorithm,
            "metadata": _json_ready(dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkFixtureReference":
        _schema_version_or_raise(data, model="BenchmarkFixtureReference")
        return cls(
            fixture_ref=str(data["fixture_ref"]),
            fixture_identity=data.get("fixture_identity"),
            identity_algorithm=data.get("identity_algorithm"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkValidationRequirements:
    """Objective validation requirements for a task."""

    schema_version: int = SCHEMA_VERSION
    build: bool = False
    artifact: bool = False
    minecraft: bool = False
    source_change: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "build": self.build,
            "artifact": self.artifact,
            "minecraft": self.minecraft,
            "source_change": self.source_change,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkValidationRequirements":
        _schema_version_or_raise(data, model="BenchmarkValidationRequirements")
        return cls(
            build=bool(data.get("build", False)),
            artifact=bool(data.get("artifact", False)),
            minecraft=bool(data.get("minecraft", False)),
            source_change=bool(data.get("source_change", False)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkAcceptanceSpec:
    """Acceptance contract metadata."""

    schema_version: int = SCHEMA_VERSION
    acceptance_type: str
    spec: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "acceptance_type", _non_empty_text(self.acceptance_type, field_name="acceptance_type"))
        object.__setattr__(self, "spec", dict(self.spec))
        object.__setattr__(self, "notes", tuple(_tuple_of_strings(self.notes)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "acceptance_type": self.acceptance_type,
            "spec": _json_ready(dict(self.spec)),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkAcceptanceSpec":
        _schema_version_or_raise(data, model="BenchmarkAcceptanceSpec")
        return cls(
            acceptance_type=str(data["acceptance_type"]),
            spec=dict(data.get("spec", {})),
            notes=tuple(str(item) for item in data.get("notes", [])),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkEnvironmentRequirements:
    """Version-sensitive environment requirements for a task."""

    schema_version: int = SCHEMA_VERSION
    minecraft_version: str | None = None
    loader_version: str | None = None
    loom_version: str | None = None
    yarn_version: str | None = None
    java_version: str | None = None
    fabric_api_version: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra", dict(self.extra))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "minecraft_version": self.minecraft_version,
            "loader_version": self.loader_version,
            "loom_version": self.loom_version,
            "yarn_version": self.yarn_version,
            "java_version": self.java_version,
            "fabric_api_version": self.fabric_api_version,
            "extra": _json_ready(dict(self.extra)),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkEnvironmentRequirements":
        _schema_version_or_raise(data, model="BenchmarkEnvironmentRequirements")
        return cls(
            minecraft_version=data.get("minecraft_version"),
            loader_version=data.get("loader_version"),
            loom_version=data.get("loom_version"),
            yarn_version=data.get("yarn_version"),
            java_version=data.get("java_version"),
            fabric_api_version=data.get("fabric_api_version"),
            extra=dict(data.get("extra", {})),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkDataset:
    """Versioned dataset manifest model."""

    schema_version: int = SCHEMA_VERSION
    dataset_id: str
    dataset_version: str
    tasks: tuple[BenchmarkTaskReference, ...] = ()
    description: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _non_empty_text(self.dataset_id, field_name="dataset_id"))
        object.__setattr__(self, "dataset_version", _non_empty_text(self.dataset_version, field_name="dataset_version"))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "tags", tuple(_tuple_of_strings(self.tags)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "tasks": [task.to_dict() for task in self.tasks],
            "description": self.description,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkDataset":
        _schema_version_or_raise(data, model="BenchmarkDataset")
        return cls(
            dataset_id=str(data["dataset_id"]),
            dataset_version=str(data["dataset_version"]),
            tasks=tuple(BenchmarkTaskReference.from_dict(item) for item in data.get("tasks", [])),
            description=data.get("description"),
            tags=tuple(str(item) for item in data.get("tags", [])),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkTask:
    """Single benchmark task definition."""

    schema_version: int = SCHEMA_VERSION
    task_id: str
    task_version: str
    description: str
    prompt: str
    fixture: BenchmarkFixtureReference
    validation: BenchmarkValidationRequirements
    acceptance: BenchmarkAcceptanceSpec
    environment: BenchmarkEnvironmentRequirements
    tags: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _non_empty_text(self.task_id, field_name="task_id"))
        object.__setattr__(self, "task_version", _non_empty_text(self.task_version, field_name="task_version"))
        object.__setattr__(self, "description", _non_empty_text(self.description, field_name="description"))
        object.__setattr__(self, "prompt", _non_empty_text(self.prompt, field_name="prompt"))
        object.__setattr__(self, "tags", tuple(_tuple_of_strings(self.tags)))
        object.__setattr__(self, "notes", tuple(_tuple_of_strings(self.notes)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "description": self.description,
            "prompt": self.prompt,
            "fixture": self.fixture.to_dict(),
            "validation": self.validation.to_dict(),
            "acceptance": self.acceptance.to_dict(),
            "environment": self.environment.to_dict(),
            "tags": list(self.tags),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkTask":
        _schema_version_or_raise(data, model="BenchmarkTask")
        return cls(
            task_id=str(data["task_id"]),
            task_version=str(data["task_version"]),
            description=str(data["description"]),
            prompt=str(data["prompt"]),
            fixture=BenchmarkFixtureReference.from_dict(dict(data["fixture"])),
            validation=BenchmarkValidationRequirements.from_dict(dict(data["validation"])),
            acceptance=BenchmarkAcceptanceSpec.from_dict(dict(data["acceptance"])),
            environment=BenchmarkEnvironmentRequirements.from_dict(dict(data["environment"])),
            tags=tuple(str(item) for item in data.get("tags", [])),
            notes=tuple(str(item) for item in data.get("notes", [])),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkConfig:
    """Benchmark execution configuration."""

    schema_version: int = SCHEMA_VERSION
    config_id: str
    provider: str
    model: str
    brain_enabled: bool
    model_config: Mapping[str, Any] = field(default_factory=dict)
    provider_config: Mapping[str, Any] = field(default_factory=dict)
    execution_limits: Any | None = None
    knowledge_config: Mapping[str, Any] = field(default_factory=dict)
    target_repetition_count: int = 1
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_id", _non_empty_text(self.config_id, field_name="config_id"))
        object.__setattr__(self, "provider", _non_empty_text(self.provider, field_name="provider"))
        object.__setattr__(self, "model", _non_empty_text(self.model, field_name="model"))
        object.__setattr__(self, "model_config", dict(self.model_config))
        object.__setattr__(self, "provider_config", dict(self.provider_config))
        object.__setattr__(self, "knowledge_config", dict(self.knowledge_config))
        object.__setattr__(self, "notes", tuple(_tuple_of_strings(self.notes)))
        if int(self.target_repetition_count) <= 0:
            raise ValueError("target_repetition_count must be positive")
        object.__setattr__(self, "target_repetition_count", int(self.target_repetition_count))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "config_id": self.config_id,
            "provider": self.provider,
            "model": self.model,
            "brain_enabled": self.brain_enabled,
            "model_config": _json_ready(dict(self.model_config)),
            "provider_config": _json_ready(dict(self.provider_config)),
            "execution_limits": _json_ready(self.execution_limits),
            "knowledge_config": _json_ready(dict(self.knowledge_config)),
            "target_repetition_count": self.target_repetition_count,
            "notes": list(self.notes),
        }

    def config_hash(self) -> str:
        payload = self._hash_payload()
        digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        return digest

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "brain_enabled": self.brain_enabled,
            "model_config": _json_ready(dict(self.model_config)),
            "provider_config": _json_ready(dict(self.provider_config)),
            "execution_limits": _json_ready(self.execution_limits),
            "knowledge_config": _json_ready(dict(self.knowledge_config)),
            "target_repetition_count": self.target_repetition_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkConfig":
        _schema_version_or_raise(data, model="BenchmarkConfig")
        execution_limits = data.get("execution_limits")
        if isinstance(execution_limits, Mapping):
            execution_limits = ExecutionLimits.from_dict(dict(execution_limits))
        return cls(
            config_id=str(data["config_id"]),
            provider=str(data["provider"]),
            model=str(data["model"]),
            brain_enabled=bool(data["brain_enabled"]),
            model_config=dict(data.get("model_config", {})),
            provider_config=dict(data.get("provider_config", {})),
            execution_limits=execution_limits,
            knowledge_config=dict(data.get("knowledge_config", {})),
            target_repetition_count=int(data.get("target_repetition_count", 1)),
            notes=tuple(str(item) for item in data.get("notes", [])),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkMetrics:
    """Normalized optional metrics."""

    schema_version: int = SCHEMA_VERSION
    duration_seconds: float | None = None
    tool_call_count: int | None = None
    build_count: int | None = None
    agent_step_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra", dict(self.extra))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "duration_seconds": self.duration_seconds,
            "tool_call_count": self.tool_call_count,
            "build_count": self.build_count,
            "agent_step_count": self.agent_step_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "extra": _json_ready(dict(self.extra)),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkMetrics":
        _schema_version_or_raise(data, model="BenchmarkMetrics")
        return cls(
            duration_seconds=data.get("duration_seconds"),
            tool_call_count=data.get("tool_call_count"),
            build_count=data.get("build_count"),
            agent_step_count=data.get("agent_step_count"),
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            total_tokens=data.get("total_tokens"),
            cost=data.get("cost"),
            extra=dict(data.get("extra", {})),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkMetricSummary:
    """Descriptive summary for one numeric metric."""

    schema_version: int = SCHEMA_VERSION
    median: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    observations: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", int(self.observations))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "median": self.median,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "observations": self.observations,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkMetricSummary":
        _schema_version_or_raise(data, model="BenchmarkMetricSummary")
        return cls(
            median=data.get("median"),
            minimum=data.get("minimum"),
            maximum=data.get("maximum"),
            observations=int(data.get("observations", 0)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkAggregateMetrics:
    """Aggregated descriptive metrics for a comparison cell."""

    schema_version: int = SCHEMA_VERSION
    duration_seconds: BenchmarkMetricSummary | None = None
    tool_call_count: BenchmarkMetricSummary | None = None
    build_count: BenchmarkMetricSummary | None = None
    agent_step_count: BenchmarkMetricSummary | None = None
    input_tokens: BenchmarkMetricSummary | None = None
    output_tokens: BenchmarkMetricSummary | None = None
    total_tokens: BenchmarkMetricSummary | None = None
    cost: BenchmarkMetricSummary | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra", dict(self.extra))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "duration_seconds": self.duration_seconds.to_dict() if self.duration_seconds is not None else None,
            "tool_call_count": self.tool_call_count.to_dict() if self.tool_call_count is not None else None,
            "build_count": self.build_count.to_dict() if self.build_count is not None else None,
            "agent_step_count": self.agent_step_count.to_dict() if self.agent_step_count is not None else None,
            "input_tokens": self.input_tokens.to_dict() if self.input_tokens is not None else None,
            "output_tokens": self.output_tokens.to_dict() if self.output_tokens is not None else None,
            "total_tokens": self.total_tokens.to_dict() if self.total_tokens is not None else None,
            "cost": self.cost.to_dict() if self.cost is not None else None,
            "extra": _json_ready(dict(self.extra)),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkAggregateMetrics":
        _schema_version_or_raise(data, model="BenchmarkAggregateMetrics")
        legacy_keys = {"median", "minimum", "maximum", "observations"}
        if legacy_keys.intersection(data.keys()):
            return cls(
                duration_seconds=BenchmarkMetricSummary.from_dict(data),
            )
        return cls(
            duration_seconds=(
                BenchmarkMetricSummary.from_dict(dict(data["duration_seconds"]))
                if data.get("duration_seconds") is not None
                else None
            ),
            tool_call_count=(
                BenchmarkMetricSummary.from_dict(dict(data["tool_call_count"]))
                if data.get("tool_call_count") is not None
                else None
            ),
            build_count=(
                BenchmarkMetricSummary.from_dict(dict(data["build_count"]))
                if data.get("build_count") is not None
                else None
            ),
            agent_step_count=(
                BenchmarkMetricSummary.from_dict(dict(data["agent_step_count"]))
                if data.get("agent_step_count") is not None
                else None
            ),
            input_tokens=(
                BenchmarkMetricSummary.from_dict(dict(data["input_tokens"]))
                if data.get("input_tokens") is not None
                else None
            ),
            output_tokens=(
                BenchmarkMetricSummary.from_dict(dict(data["output_tokens"]))
                if data.get("output_tokens") is not None
                else None
            ),
            total_tokens=(
                BenchmarkMetricSummary.from_dict(dict(data["total_tokens"]))
                if data.get("total_tokens") is not None
                else None
            ),
            cost=(
                BenchmarkMetricSummary.from_dict(dict(data["cost"]))
                if data.get("cost") is not None
                else None
            ),
            extra=dict(data.get("extra", {})),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkRun:
    """One isolated benchmark run."""

    schema_version: int = SCHEMA_VERSION
    benchmark_run_id: str
    task_id: str
    task_version: str
    config_id: str
    config_hash: str
    repetition_index: int
    attempt_index: int = 1
    pd_agent_commit: str | None = None
    fixture_hash: str | None = None
    environment_snapshot: Mapping[str, Any] = field(default_factory=dict)
    underlying_run_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    execution_status: BenchmarkExecutionStatus = BenchmarkExecutionStatus.INVALID
    task_outcome: BenchmarkTaskOutcome = BenchmarkTaskOutcome.NOT_EVALUATED
    failure_origin: BenchmarkFailureOrigin = BenchmarkFailureOrigin.UNKNOWN
    failure_code: BenchmarkFailureCode = BenchmarkFailureCode.UNKNOWN
    metrics: BenchmarkMetrics | None = None
    evidence_refs: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_run_id", _non_empty_text(self.benchmark_run_id, field_name="benchmark_run_id"))
        object.__setattr__(self, "task_id", _non_empty_text(self.task_id, field_name="task_id"))
        object.__setattr__(self, "task_version", _non_empty_text(self.task_version, field_name="task_version"))
        object.__setattr__(self, "config_id", _non_empty_text(self.config_id, field_name="config_id"))
        object.__setattr__(self, "config_hash", _non_empty_text(self.config_hash, field_name="config_hash"))
        object.__setattr__(self, "repetition_index", int(self.repetition_index))
        object.__setattr__(self, "attempt_index", int(self.attempt_index))
        object.__setattr__(self, "environment_snapshot", dict(self.environment_snapshot))
        object.__setattr__(
            self,
            "execution_status",
            BenchmarkExecutionStatus(str(self.execution_status)),
        )
        object.__setattr__(
            self,
            "task_outcome",
            BenchmarkTaskOutcome(str(self.task_outcome)),
        )
        object.__setattr__(
            self,
            "failure_origin",
            BenchmarkFailureOrigin(str(self.failure_origin)),
        )
        object.__setattr__(
            self,
            "failure_code",
            BenchmarkFailureCode(str(self.failure_code)),
        )
        object.__setattr__(self, "evidence_refs", tuple(_tuple_of_strings(self.evidence_refs)))
        object.__setattr__(self, "notes", tuple(_tuple_of_strings(self.notes)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_run_id": self.benchmark_run_id,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "config_id": self.config_id,
            "config_hash": self.config_hash,
            "repetition_index": self.repetition_index,
            "attempt_index": self.attempt_index,
            "pd_agent_commit": self.pd_agent_commit,
            "fixture_hash": self.fixture_hash,
            "environment_snapshot": _json_ready(dict(self.environment_snapshot)),
            "underlying_run_id": self.underlying_run_id,
            "started_at": self.started_at.isoformat() if self.started_at is not None else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at is not None else None,
            "duration_seconds": self.duration_seconds,
            "execution_status": self.execution_status.value,
            "task_outcome": self.task_outcome.value,
            "failure_origin": self.failure_origin.value,
            "failure_code": self.failure_code.value,
            "metrics": self.metrics.to_dict() if self.metrics is not None else None,
            "evidence_refs": list(self.evidence_refs),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkRun":
        _schema_version_or_raise(data, model="BenchmarkRun")
        return cls(
            benchmark_run_id=str(data["benchmark_run_id"]),
            task_id=str(data["task_id"]),
            task_version=str(data["task_version"]),
            config_id=str(data["config_id"]),
            config_hash=str(data["config_hash"]),
            repetition_index=int(data["repetition_index"]),
            attempt_index=int(data.get("attempt_index", 1)),
            pd_agent_commit=data.get("pd_agent_commit"),
            fixture_hash=data.get("fixture_hash"),
            environment_snapshot=dict(data.get("environment_snapshot", {})),
            underlying_run_id=data.get("underlying_run_id"),
            started_at=(datetime.fromisoformat(str(data["started_at"])) if data.get("started_at") is not None else None),
            finished_at=(datetime.fromisoformat(str(data["finished_at"])) if data.get("finished_at") is not None else None),
            duration_seconds=data.get("duration_seconds"),
            execution_status=BenchmarkExecutionStatus(str(data.get("execution_status", BenchmarkExecutionStatus.INVALID.value))),
            task_outcome=BenchmarkTaskOutcome(str(data.get("task_outcome", BenchmarkTaskOutcome.NOT_EVALUATED.value))),
            failure_origin=BenchmarkFailureOrigin(str(data.get("failure_origin", BenchmarkFailureOrigin.UNKNOWN.value))),
            failure_code=BenchmarkFailureCode(str(data.get("failure_code", BenchmarkFailureCode.UNKNOWN.value))),
            metrics=(BenchmarkMetrics.from_dict(dict(data["metrics"])) if data.get("metrics") is not None else None),
            evidence_refs=tuple(str(item) for item in data.get("evidence_refs", [])),
            notes=tuple(str(item) for item in data.get("notes", [])),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkComparisonCell:
    """Aggregated results for one task/config pair."""

    schema_version: int = SCHEMA_VERSION
    task_id: str
    task_version: str
    config_id: str
    config_hash: str
    attempted: int
    valid: int
    passed: int
    failed: int
    blocked: int
    invalid: int
    target_valid: int
    complete: bool
    metrics: BenchmarkAggregateMetrics | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _non_empty_text(self.task_id, field_name="task_id"))
        object.__setattr__(self, "task_version", _non_empty_text(self.task_version, field_name="task_version"))
        object.__setattr__(self, "config_id", _non_empty_text(self.config_id, field_name="config_id"))
        object.__setattr__(self, "config_hash", _non_empty_text(self.config_hash, field_name="config_hash"))
        for field_name in ("attempted", "valid", "passed", "failed", "blocked", "invalid", "target_valid"):
            object.__setattr__(self, field_name, int(getattr(self, field_name)))
        object.__setattr__(self, "notes", tuple(_tuple_of_strings(self.notes)))

    @property
    def success_rate(self) -> float | None:
        if self.valid <= 0:
            return None
        return self.passed / self.valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "config_id": self.config_id,
            "config_hash": self.config_hash,
            "attempted": self.attempted,
            "valid": self.valid,
            "passed": self.passed,
            "failed": self.failed,
            "blocked": self.blocked,
            "invalid": self.invalid,
            "target_valid": self.target_valid,
            "complete": self.complete,
            "metrics": self.metrics.to_dict() if self.metrics is not None else None,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkComparisonCell":
        _schema_version_or_raise(data, model="BenchmarkComparisonCell")
        return cls(
            task_id=str(data["task_id"]),
            task_version=str(data["task_version"]),
            config_id=str(data["config_id"]),
            config_hash=str(data.get("config_hash", data["config_id"])),
            attempted=int(data["attempted"]),
            valid=int(data["valid"]),
            passed=int(data["passed"]),
            failed=int(data["failed"]),
            blocked=int(data["blocked"]),
            invalid=int(data["invalid"]),
            target_valid=int(data["target_valid"]),
            complete=bool(data["complete"]),
            metrics=(
                BenchmarkAggregateMetrics.from_dict(dict(data["metrics"]))
                if data.get("metrics") is not None
                else None
            ),
            notes=tuple(str(item) for item in data.get("notes", [])),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkComparison:
    """Aggregate comparison contract."""

    schema_version: int = SCHEMA_VERSION
    dataset_id: str
    dataset_version: str
    configs: tuple[BenchmarkConfig, ...] = ()
    runs_expected: int = 0
    runs_valid: int = 0
    runs_blocked: int = 0
    runs_invalid: int = 0
    cell_results: tuple[BenchmarkComparisonCell, ...] = ()
    aggregate_metadata: Mapping[str, Any] = field(default_factory=dict)
    comparison_status: BenchmarkComparisonStatus = BenchmarkComparisonStatus.INCOMPLETE
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _non_empty_text(self.dataset_id, field_name="dataset_id"))
        object.__setattr__(self, "dataset_version", _non_empty_text(self.dataset_version, field_name="dataset_version"))
        object.__setattr__(self, "configs", tuple(self.configs))
        object.__setattr__(self, "cell_results", tuple(self.cell_results))
        object.__setattr__(self, "aggregate_metadata", dict(self.aggregate_metadata))
        object.__setattr__(self, "runs_expected", int(self.runs_expected))
        object.__setattr__(self, "runs_valid", int(self.runs_valid))
        object.__setattr__(self, "runs_blocked", int(self.runs_blocked))
        object.__setattr__(self, "runs_invalid", int(self.runs_invalid))
        object.__setattr__(
            self,
            "comparison_status",
            BenchmarkComparisonStatus(str(self.comparison_status)),
        )
        object.__setattr__(self, "notes", tuple(_tuple_of_strings(self.notes)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "configs": [config.to_dict() for config in self.configs],
            "runs_expected": self.runs_expected,
            "runs_valid": self.runs_valid,
            "runs_blocked": self.runs_blocked,
            "runs_invalid": self.runs_invalid,
            "cell_results": [cell.to_dict() for cell in self.cell_results],
            "aggregate_metadata": _json_ready(dict(self.aggregate_metadata)),
            "comparison_status": self.comparison_status.value,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkComparison":
        _schema_version_or_raise(data, model="BenchmarkComparison")
        return cls(
            dataset_id=str(data["dataset_id"]),
            dataset_version=str(data["dataset_version"]),
            configs=tuple(BenchmarkConfig.from_dict(dict(item)) for item in data.get("configs", [])),
            runs_expected=int(data.get("runs_expected", 0)),
            runs_valid=int(data.get("runs_valid", 0)),
            runs_blocked=int(data.get("runs_blocked", 0)),
            runs_invalid=int(data.get("runs_invalid", 0)),
            cell_results=tuple(
                BenchmarkComparisonCell.from_dict(dict(item)) for item in data.get("cell_results", [])
            ),
            aggregate_metadata=dict(data.get("aggregate_metadata", {})),
            comparison_status=BenchmarkComparisonStatus(str(data.get("comparison_status", BenchmarkComparisonStatus.INCOMPLETE.value))),
            notes=tuple(str(item) for item in data.get("notes", [])),
        )


__all__ = [
    "BenchmarkAcceptanceSpec",
    "BenchmarkComparison",
    "BenchmarkComparisonCell",
    "BenchmarkComparisonStatus",
    "BenchmarkAggregateMetrics",
    "BenchmarkConfig",
    "BenchmarkDataset",
    "BenchmarkEnvironmentRequirements",
    "BenchmarkExecutionStatus",
    "BenchmarkFailureCode",
    "BenchmarkFailureOrigin",
    "BenchmarkFixtureReference",
    "BenchmarkMetricSummary",
    "BenchmarkMetrics",
    "BenchmarkSchemaError",
    "BenchmarkTask",
    "BenchmarkTaskOutcome",
    "BenchmarkTaskReference",
    "BenchmarkValidationRequirements",
    "SCHEMA_VERSION",
]
