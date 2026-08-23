"""Canonical terminal reasons emitted by the agent runtime."""

from __future__ import annotations

TOOL_REJECTED = "tool rejected"
REPEATED_RECOVERABLE_TOOL_REJECTION = (
    "repeated recoverable tool rejection without operational progress"
)
REPEATED_BUILD_FAILURE = "repeated build failure"
SEMANTIC_REPAIR_NO_MUTATION = "semantic repair produced no mutation"
REPEATED_UNRESOLVED_MUTATION_TARGETS = (
    "repeated unresolved mutation targets without operational progress"
)
REPEATED_ACTION_GATE_VIOLATION = (
    "repeated action gate violation without operational progress"
)

AGENT_TERMINAL_FAILURE_REASONS = frozenset(
    {
        TOOL_REJECTED,
        REPEATED_RECOVERABLE_TOOL_REJECTION,
        REPEATED_BUILD_FAILURE,
        SEMANTIC_REPAIR_NO_MUTATION,
        REPEATED_UNRESOLVED_MUTATION_TARGETS,
        REPEATED_ACTION_GATE_VIOLATION,
    }
)


def is_agent_terminal_failure(reason: str | None) -> bool:
    """Return whether a persisted reason is an agent-attributable terminal failure."""

    return reason in AGENT_TERMINAL_FAILURE_REASONS


__all__ = [
    "AGENT_TERMINAL_FAILURE_REASONS",
    "REPEATED_ACTION_GATE_VIOLATION",
    "REPEATED_BUILD_FAILURE",
    "REPEATED_RECOVERABLE_TOOL_REJECTION",
    "REPEATED_UNRESOLVED_MUTATION_TARGETS",
    "SEMANTIC_REPAIR_NO_MUTATION",
    "TOOL_REJECTED",
    "is_agent_terminal_failure",
]
