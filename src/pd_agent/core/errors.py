"""Normalized PD Agent errors."""

from __future__ import annotations


class PDAgentError(Exception):
    """Base error for PD Agent."""


class ConfigurationError(PDAgentError):
    """Invalid configuration."""


class ProjectInspectionError(PDAgentError):
    """Project inspection failed."""


class SecurityViolation(PDAgentError):
    """Security boundary violated."""


class ToolValidationError(PDAgentError):
    """Tool input or schema invalid."""


class ToolExecutionError(PDAgentError):
    """Tool execution failed."""


class ProviderError(PDAgentError):
    """Provider-level failure."""

    def __init__(
        self,
        message: str,
        *,
        kind: str | None = None,
        request_id: str | None = None,
        status_code: int | None = None,
        retryable: bool | None = None,
        provider: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.request_id = request_id
        self.status_code = status_code
        self.retryable = False if retryable is None else retryable
        self.provider = provider
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {
            "message": self.message,
            "kind": self.kind,
            "request_id": self.request_id,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "provider": self.provider,
            "details": dict(self.details),
        }


class BuildError(PDAgentError):
    """Build failure."""


class ArtifactValidationError(PDAgentError):
    """Artifact validation failure."""


class LimitReachedError(PDAgentError):
    """Execution limit reached."""


class RunStateError(PDAgentError):
    """Run state invalid."""


class StateTransitionError(RunStateError):
    """Invalid run state transition."""
