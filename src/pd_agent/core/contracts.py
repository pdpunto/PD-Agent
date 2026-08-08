"""Provider-neutral core contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


class ToolResultStatus(StrEnum):
    """Outcome of tool execution."""

    SUCCESS = "success"
    ERROR = "error"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


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
class AgentResponse:
    """Provider response."""

    assistant_message: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Mapping[str, Any] | None = None
    provider_metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assistant_message": self.assistant_message,
            "tool_calls": [call.to_dict() for call in self.tool_calls],
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
    tools: tuple[Mapping[str, Any], ...] = ()
    model_config: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "messages": [message.to_dict() for message in self.messages],
            "tools": [dict(tool) for tool in self.tools],
            "model_config": dict(self.model_config),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentRequest":
        return cls(
            messages=tuple(
                AgentMessage.from_dict(item) for item in data.get("messages", [])
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
