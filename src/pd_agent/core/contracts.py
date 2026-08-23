"""Provider-neutral core contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


MAX_PROVIDER_CONTINUATION_BYTES = 8_192


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


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationViolation:
    """Deterministic description of one validation violation."""

    code: str
    requirement: str
    observed: Any
    message: str
    evidence_refs: tuple[str, ...] = ()

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "requirement": self.requirement,
            "observed": self.observed,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidationViolation":
        return cls(
            code=str(data["code"]),
            requirement=str(data["requirement"]),
            observed=data.get("observed"),
            message=str(data["message"]),
            evidence_refs=tuple(str(item) for item in data.get("evidence_refs", [])),
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
