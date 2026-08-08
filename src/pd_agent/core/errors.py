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

