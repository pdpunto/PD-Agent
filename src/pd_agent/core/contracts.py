"""Provider-neutral core contracts."""

from __future__ import annotations

import json
import hashlib
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


MAX_PROVIDER_CONTINUATION_BYTES = 8_192

_CONTRACT_SCHEMA_VERSION = 1
_UNSAFE_CONTROL_KEYS = frozenset(
    {
        "command",
        "commands",
        "exec",
        "executable",
        "reflection",
        "shell",
        "script",
        "scripts",
    }
)


def _json_ready(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_ready(value.to_dict())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return [_json_ready(item) for item in sorted(value, key=repr)]
    return value


class ToolResultStatus(StrEnum):
    """Outcome of tool execution."""

    SUCCESS = "success"
    ERROR = "error"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class ValidationStage(StrEnum):
    """Stage at which a validation result was produced."""

    PRE_BUILD = "PRE_BUILD"
    POST_ARTIFACT = "POST_ARTIFACT"
    RUNTIME = "RUNTIME"


class ValidationStatus(StrEnum):
    """Provider-neutral validation outcome."""

    PASS = "PASS"
    REPAIRABLE_FAIL = "REPAIRABLE_FAIL"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"


def _validation_text(value: Any, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _validation_json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _validation_json_ready(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if isinstance(value, tuple):
        return [_validation_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_validation_json_ready(item) for item in value]
    if isinstance(value, set):
        return [_validation_json_ready(item) for item in sorted(value, key=repr)]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _contract_json_ready(value: Any, *, field_name: str, reject_control_keys: bool = True) -> Any:
    """Return strict JSON data without accepting executable/control payloads."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must contain finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{field_name} keys must be non-empty strings")
            normalized_key = key.strip()
            if reject_control_keys and normalized_key.casefold() in _UNSAFE_CONTROL_KEYS:
                raise ValueError(f"{field_name} contains unsupported control key: {normalized_key}")
            result[normalized_key] = _contract_json_ready(
                item,
                field_name=f"{field_name}.{normalized_key}",
                reject_control_keys=reject_control_keys,
            )
        return result
    if isinstance(value, (list, tuple)):
        return [
            _contract_json_ready(item, field_name=f"{field_name}[{index}]", reject_control_keys=reject_control_keys)
            for index, item in enumerate(value)
        ]
    raise ValueError(f"{field_name} must contain JSON-compatible values")


def _contract_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _contract_ids(values: Any, *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise ValueError(f"{field_name} must be a sequence of IDs")
    normalized = tuple(_contract_text(value, field_name=field_name) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicate IDs")
    return normalized


def _canonical_contract_payload(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricRequirement:
    """Stable, provider-neutral obligation in a Fabric task."""

    requirement_id: str
    description: str
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", _contract_text(self.requirement_id, field_name="requirement_id"))
        object.__setattr__(self, "description", _contract_text(self.description, field_name="description"))
        if not isinstance(self.required, bool):
            raise ValueError("required must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {"requirement_id": self.requirement_id, "description": self.description, "required": self.required}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricRequirement":
        return cls(
            requirement_id=data["requirement_id"],
            description=data["description"],
            required=data.get("required", True),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricValidationRequirement:
    """Typed, data-only validation obligation linked to requirements."""

    validation_requirement_id: str
    requirement_ids: tuple[str, ...]
    kind: str
    required: bool = True
    spec: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "validation_requirement_id", _contract_text(self.validation_requirement_id, field_name="validation_requirement_id"))
        object.__setattr__(self, "requirement_ids", _contract_ids(self.requirement_ids, field_name="requirement_ids"))
        object.__setattr__(self, "kind", _contract_text(self.kind, field_name="kind").casefold())
        if not isinstance(self.required, bool):
            raise ValueError("required must be a boolean")
        if not isinstance(self.spec, Mapping):
            raise ValueError("spec must be a mapping")
        object.__setattr__(self, "spec", _contract_json_ready(self.spec, field_name="spec"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_requirement_id": self.validation_requirement_id,
            "requirement_ids": list(self.requirement_ids),
            "kind": self.kind,
            "required": self.required,
            "spec": dict(self.spec),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricValidationRequirement":
        return cls(
            validation_requirement_id=data["validation_requirement_id"],
            requirement_ids=tuple(data["requirement_ids"]),
            kind=data["kind"],
            required=data.get("required", True),
            spec=data.get("spec", {}),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricKnowledgeSignal:
    """Brain/provider-neutral signal used to derive future knowledge needs."""

    signal_id: str
    query: str
    category: str | None = None
    required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_id", _contract_text(self.signal_id, field_name="signal_id"))
        object.__setattr__(self, "query", _contract_text(self.query, field_name="query"))
        if self.category is not None:
            object.__setattr__(self, "category", _contract_text(self.category, field_name="category"))
        if not isinstance(self.required, bool):
            raise ValueError("required must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {"signal_id": self.signal_id, "query": self.query, "category": self.category, "required": self.required}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricKnowledgeSignal":
        return cls(
            signal_id=data["signal_id"],
            query=data["query"],
            category=data.get("category"),
            required=data.get("required", False),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricMutationExpectation:
    """Declarative mutation expectation, never an executable instruction."""

    expectation_id: str
    role: str
    path: str | None = None
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "expectation_id", _contract_text(self.expectation_id, field_name="expectation_id"))
        object.__setattr__(self, "role", _contract_text(self.role, field_name="role"))
        if self.path is not None:
            path = _contract_text(self.path, field_name="path").replace("\\", "/")
            if path.startswith("/") or ".." in path.split("/"):
                raise ValueError("path must be a relative confined path")
            object.__setattr__(self, "path", path)
        if not isinstance(self.required, bool):
            raise ValueError("required must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {"expectation_id": self.expectation_id, "role": self.role, "path": self.path, "required": self.required}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricMutationExpectation":
        return cls(
            expectation_id=data["expectation_id"],
            role=data["role"],
            path=data.get("path"),
            required=data.get("required", True),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricEnvironmentConstraints:
    """Serializable environment constraints for a Fabric task."""

    minecraft_version: str | None = None
    loader_version: str | None = None
    fabric_api_version: str | None = None
    yarn_version: str | None = None
    java_version: str | None = None
    platform: str = "fabric"
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("minecraft_version", "loader_version", "fabric_api_version", "yarn_version", "java_version", "platform"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _contract_text(value, field_name=field_name))
        if self.platform.casefold() != "fabric":
            raise ValueError("platform must be fabric")
        if not isinstance(self.extra, Mapping):
            raise ValueError("extra must be a mapping")
        object.__setattr__(self, "extra", _contract_json_ready(self.extra, field_name="extra"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "minecraft_version": self.minecraft_version,
            "loader_version": self.loader_version,
            "fabric_api_version": self.fabric_api_version,
            "yarn_version": self.yarn_version,
            "java_version": self.java_version,
            "platform": self.platform,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricEnvironmentConstraints":
        return cls(**{key: data.get(key) for key in ("minecraft_version", "loader_version", "fabric_api_version", "yarn_version", "java_version", "platform", "extra") if key in data})


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricTaskContract:
    """Immutable, persistible representation of the general task WHAT."""

    task_id: str
    revision: str
    goal: str
    requirements: tuple[FabricRequirement, ...]
    required_capabilities: tuple[str, ...] = ()
    completion_criteria: tuple[str, ...] = ()
    validation_requirements: tuple[FabricValidationRequirement, ...] = ()
    knowledge_signals: tuple[FabricKnowledgeSignal, ...] = ()
    mutation_expectations: tuple[FabricMutationExpectation, ...] = ()
    environment_constraints: FabricEnvironmentConstraints = field(default_factory=FabricEnvironmentConstraints)
    schema_version: int = _CONTRACT_SCHEMA_VERSION
    fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _contract_text(self.task_id, field_name="task_id"))
        object.__setattr__(self, "revision", _contract_text(self.revision, field_name="revision"))
        object.__setattr__(self, "goal", _contract_text(self.goal, field_name="goal"))
        if not isinstance(self.schema_version, int) or self.schema_version != _CONTRACT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {_CONTRACT_SCHEMA_VERSION}")
        requirements = tuple(self.requirements)
        if len({item.requirement_id for item in requirements}) != len(requirements):
            raise ValueError("requirements must not contain duplicate requirement IDs")
        if not all(isinstance(item, FabricRequirement) for item in requirements):
            raise ValueError("requirements must contain FabricRequirement values")
        object.__setattr__(self, "requirements", requirements)
        for field_name in ("required_capabilities", "completion_criteria"):
            values = _contract_ids(getattr(self, field_name), field_name=field_name)
            object.__setattr__(self, field_name, values)
        validations = tuple(self.validation_requirements)
        if len({item.validation_requirement_id for item in validations}) != len(validations):
            raise ValueError("validation_requirements must not contain duplicate IDs")
        requirement_ids = {item.requirement_id for item in requirements}
        for item in validations:
            if not isinstance(item, FabricValidationRequirement):
                raise ValueError("validation_requirements must contain FabricValidationRequirement values")
            if not set(item.requirement_ids).issubset(requirement_ids):
                raise ValueError("validation requirement references an unknown requirement")
        object.__setattr__(self, "validation_requirements", validations)
        signals = tuple(self.knowledge_signals)
        if len({item.signal_id for item in signals}) != len(signals):
            raise ValueError("knowledge_signals must not contain duplicate IDs")
        object.__setattr__(self, "knowledge_signals", signals)
        expectations = tuple(self.mutation_expectations)
        if len({item.expectation_id for item in expectations}) != len(expectations):
            raise ValueError("mutation_expectations must not contain duplicate IDs")
        object.__setattr__(self, "mutation_expectations", expectations)
        if not isinstance(self.environment_constraints, FabricEnvironmentConstraints):
            raise ValueError("environment_constraints must be FabricEnvironmentConstraints")
        payload = self._identity_payload()
        expected_fingerprint = hashlib.sha256(_canonical_contract_payload(payload).encode("utf-8")).hexdigest()
        if self.fingerprint is not None and self.fingerprint != expected_fingerprint:
            raise ValueError("fingerprint does not match canonical contract content")
        object.__setattr__(self, "fingerprint", expected_fingerprint)

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "revision": self.revision,
            "schema_version": self.schema_version,
            "goal": self.goal,
            "requirements": [item.to_dict() for item in self.requirements],
            "required_capabilities": list(self.required_capabilities),
            "completion_criteria": list(self.completion_criteria),
            "validation_requirements": [item.to_dict() for item in self.validation_requirements],
            "knowledge_signals": [item.to_dict() for item in self.knowledge_signals],
            "mutation_expectations": [item.to_dict() for item in self.mutation_expectations],
            "environment_constraints": self.environment_constraints.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._identity_payload(), "fingerprint": self.fingerprint}

    def canonical_json(self) -> str:
        return _canonical_contract_payload(self._identity_payload())

    def identity(self) -> tuple[str, str, str]:
        return self.task_id, self.revision, self.fingerprint or ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricTaskContract":
        return cls(
            task_id=data["task_id"],
            revision=data["revision"],
            schema_version=data.get("schema_version", _CONTRACT_SCHEMA_VERSION),
            fingerprint=data.get("fingerprint"),
            goal=data["goal"],
            requirements=tuple(FabricRequirement.from_dict(item) for item in data.get("requirements", [])),
            required_capabilities=tuple(data.get("required_capabilities", [])),
            completion_criteria=tuple(data.get("completion_criteria", [])),
            validation_requirements=tuple(FabricValidationRequirement.from_dict(item) for item in data.get("validation_requirements", [])),
            knowledge_signals=tuple(FabricKnowledgeSignal.from_dict(item) for item in data.get("knowledge_signals", [])),
            mutation_expectations=tuple(FabricMutationExpectation.from_dict(item) for item in data.get("mutation_expectations", [])),
            environment_constraints=FabricEnvironmentConstraints.from_dict(data.get("environment_constraints", {})),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationViolation:
    """Deterministic description of one validation violation."""

    code: str
    requirement: str
    observed: Any
    message: str
    evidence_refs: tuple[str, ...] = ()
    expected: Any = None
    actual: Any = None
    phase: str | None = None
    observation_id: str | None = None
    action_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _validation_text(self.code, field_name="code"))
        object.__setattr__(
            self,
            "requirement",
            _validation_text(self.requirement, field_name="requirement"),
        )
        object.__setattr__(self, "message", _validation_text(self.message, field_name="message"))
        refs = tuple(_validation_text(ref, field_name="evidence_ref") for ref in self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "observed", _validation_json_ready(self.observed))
        object.__setattr__(self, "expected", _validation_json_ready(self.expected))
        object.__setattr__(self, "actual", _validation_json_ready(self.actual))
        for name in ("phase", "observation_id", "action_id"):
            value = getattr(self, name)
            object.__setattr__(self, name, _validation_text(value, field_name=name) if value is not None else None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "requirement": self.requirement,
            "observed": self.observed,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
            "expected": self.expected,
            "actual": self.actual,
            "phase": self.phase,
            "observation_id": self.observation_id,
            "action_id": self.action_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidationViolation":
        return cls(
            code=str(data["code"]),
            requirement=str(data["requirement"]),
            observed=data.get("observed"),
            message=str(data["message"]),
            evidence_refs=tuple(str(item) for item in data.get("evidence_refs", [])),
            expected=data.get("expected"),
            actual=data.get("actual"),
            phase=data.get("phase"),
            observation_id=data.get("observation_id"),
            action_id=data.get("action_id"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationResult:
    """Serializable aggregate validation result."""

    stage: ValidationStage
    status: ValidationStatus
    summary: str
    violations: tuple[ValidationViolation, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", ValidationStage(self.stage))
        object.__setattr__(self, "status", ValidationStatus(self.status))
        object.__setattr__(self, "summary", _validation_text(self.summary, field_name="summary"))
        object.__setattr__(self, "violations", tuple(self.violations))
        refs = tuple(_validation_text(ref, field_name="evidence_ref") for ref in self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "summary": self.summary,
            "violations": [violation.to_dict() for violation in self.violations],
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidationResult":
        return cls(
            stage=ValidationStage(str(data["stage"])),
            status=ValidationStatus(str(data["status"])),
            summary=str(data["summary"]),
            violations=tuple(
                ValidationViolation.from_dict(item) for item in data.get("violations", [])
            ),
            evidence_refs=tuple(str(item) for item in data.get("evidence_refs", [])),
        )


@runtime_checkable
class PreBuildValidator(Protocol):
    """Generic workspace validator injected into the runtime."""

    def validate(self, project_root: Path, contract: Any) -> ValidationResult:
        """Validate cheap requirements before a build."""


@runtime_checkable
class FunctionalValidator(Protocol):
    """Generic post-artifact/runtime validator injected into the runtime."""

    def validate(
        self,
        project_root: Path,
        artifact: ArtifactResult,
        contract: Any,
        run_id: str,
    ) -> ValidationResult:
        """Validate the produced artifact or its runtime behavior."""


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """Single provider-neutral message."""

    role: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentMessage":
        return cls(
            role=str(data["role"]),
            content=str(data["content"]),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Provider tool call."""

    call_id: str
    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ToolCall":
        return cls(
            call_id=str(data["call_id"]),
            tool_name=str(data["tool_name"]),
            arguments=dict(data.get("arguments", {})),
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result returned by a tool."""

    call_id: str
    tool_name: str
    status: ToolResultStatus
    output: Any = None
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ToolResult":
        return cls(
            call_id=str(data["call_id"]),
            tool_name=str(data["tool_name"]),
            status=ToolResultStatus(str(data["status"])),
            output=data.get("output"),
            error=data.get("error"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class ProviderContinuation:
    """Opaque provider continuation metadata."""

    provider: str
    kind: str
    target_type: str
    target_id: str
    position: int | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        provider = str(self.provider).strip()
        kind = str(self.kind).strip()
        target_type = str(self.target_type).strip()
        target_id = str(self.target_id).strip()
        if not provider:
            raise ValueError("provider cannot be empty")
        if not kind:
            raise ValueError("kind cannot be empty")
        if not target_type:
            raise ValueError("target_type cannot be empty")
        if not target_id:
            raise ValueError("target_id cannot be empty")
        if self.position is not None and int(self.position) < 0:
            raise ValueError("position must be non-negative")
        payload = self._validate_payload(self.payload)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "target_type", target_type)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "position", int(self.position) if self.position is not None else None)
        object.__setattr__(self, "payload", payload)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "provider": self.provider,
            "kind": self.kind,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "position": self.position,
            "payload": _json_ready(self.payload),
        }
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderContinuation":
        return cls(
            provider=str(data["provider"]),
            kind=str(data["kind"]),
            target_type=str(data["target_type"]),
            target_id=str(data["target_id"]),
            position=(int(data["position"]) if data.get("position") is not None else None),
            payload=dict(data.get("payload", {})),
        )

    def _validate_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be mapping")
        data = _json_ready(dict(payload))
        try:
            encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
        except TypeError as exc:
            raise TypeError("payload must be JSON-safe") from exc
        if len(encoded.encode("utf-8")) > MAX_PROVIDER_CONTINUATION_BYTES:
            raise ValueError("payload exceeds provider continuation limit")
        if not isinstance(data, Mapping):
            raise TypeError("payload must serialize to mapping")
        return dict(data)


@dataclass(frozen=True, slots=True)
class AgentResponse:
    """Provider response."""

    assistant_message: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    provider_continuations: tuple[ProviderContinuation, ...] = ()
    usage: Mapping[str, Any] | None = None
    provider_metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assistant_message": self.assistant_message,
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "provider_continuations": [item.to_dict() for item in self.provider_continuations],
            "usage": dict(self.usage) if self.usage is not None else None,
            "provider_metadata": (
                dict(self.provider_metadata)
                if self.provider_metadata is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentResponse":
        return cls(
            assistant_message=data.get("assistant_message"),
            tool_calls=tuple(
                ToolCall.from_dict(item) for item in data.get("tool_calls", [])
            ),
            provider_continuations=tuple(
                ProviderContinuation.from_dict(item)
                for item in data.get("provider_continuations", [])
            ),
            usage=dict(data["usage"]) if data.get("usage") is not None else None,
            provider_metadata=(
                dict(data["provider_metadata"])
                if data.get("provider_metadata") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class AgentRequest:
    """Provider request."""

    messages: tuple[AgentMessage, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()
    provider_continuations: tuple[ProviderContinuation, ...] = ()
    tools: tuple[Mapping[str, Any], ...] = ()
    model_config: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "messages": [message.to_dict() for message in self.messages],
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "tool_results": [result.to_dict() for result in self.tool_results],
            "provider_continuations": [item.to_dict() for item in self.provider_continuations],
            "tools": [dict(tool) for tool in self.tools],
            "model_config": dict(self.model_config),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentRequest":
        return cls(
            messages=tuple(
                AgentMessage.from_dict(item) for item in data.get("messages", [])
            ),
            tool_calls=tuple(
                ToolCall.from_dict(item) for item in data.get("tool_calls", [])
            ),
            tool_results=tuple(
                ToolResult.from_dict(item) for item in data.get("tool_results", [])
            ),
            provider_continuations=tuple(
                ProviderContinuation.from_dict(item)
                for item in data.get("provider_continuations", [])
            ),
            tools=tuple(dict(tool) for tool in data.get("tools", [])),
            model_config=dict(data.get("model_config", {})),
        )


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Result of a Gradle build attempt."""

    attempt: int
    command_display: str
    cwd: Path | None
    started_at: datetime
    duration_seconds: float
    exit_code: int
    stdout_log: str
    stderr_log: str
    success: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "success", self.exit_code == 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "command_display": self.command_display,
            "cwd": str(self.cwd) if self.cwd is not None else None,
            "started_at": self.started_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "stdout_log": self.stdout_log,
            "stderr_log": self.stderr_log,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BuildResult":
        return cls(
            attempt=int(data["attempt"]),
            command_display=str(data["command_display"]),
            cwd=Path(data["cwd"]) if data.get("cwd") is not None else None,
            started_at=datetime.fromisoformat(str(data["started_at"])),
            duration_seconds=float(data["duration_seconds"]),
            exit_code=int(data["exit_code"]),
            stdout_log=str(data.get("stdout_log", "")),
            stderr_log=str(data.get("stderr_log", "")),
        )


@dataclass(frozen=True, slots=True)
class ArtifactResult:
    """Result of artifact validation."""

    path: Path | None
    size: int
    timestamp: datetime
    classification: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path is not None else None,
            "size": self.size,
            "timestamp": self.timestamp.isoformat(),
            "classification": self.classification,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactResult":
        return cls(
            path=Path(data["path"]) if data.get("path") is not None else None,
            size=int(data["size"]),
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            classification=str(data["classification"]),
            metadata=dict(data.get("metadata", {})),
        )


@runtime_checkable
class ModelProvider(Protocol):
    """Provider abstraction."""

    def execute(self, request: AgentRequest) -> AgentResponse:
        """Execute one provider turn."""


@runtime_checkable
class Tool(Protocol):
    """Runtime tool contract."""

    name: str
    description: str
    input_schema: Mapping[str, Any]

    def execute(self, context: Any, arguments: Mapping[str, Any]) -> ToolResult:
        """Execute tool."""


@runtime_checkable
class ContextSource(Protocol):
    """Context provider contract."""

    def get(self, request: Any) -> tuple[Any, ...]:
        """Return provider-ready context items."""
