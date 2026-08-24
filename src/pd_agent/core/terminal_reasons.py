"""Canonical terminal reasons emitted by the agent runtime."""

from __future__ import annotations

TOOL_REJECTED = "tool rejected"
REPEATED_RECOVERABLE_TOOL_REJECTION = (
    "repeated recoverable tool rejection without operational progress"
)
REPEATED_BUILD_FAILURE = "repeated build failure"
DIAGNOSIS_NO_CORRECTION = "diagnosis produced no correction"
REPEATED_SEMANTIC_VALIDATION_FAILURE = "repeated semantic validation failure"
REPEATED_NO_OP_TOOL_CALLS = "repeated no-op tool calls"
EXPLORATION_STALLED = "exploration stalled without operational progress"
PENDING_MUTATION_TARGETS_BLOCK_BUILD = "pending mutation targets block build"
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
        DIAGNOSIS_NO_CORRECTION,
        REPEATED_SEMANTIC_VALIDATION_FAILURE,
        REPEATED_NO_OP_TOOL_CALLS,
        EXPLORATION_STALLED,
        PENDING_MUTATION_TARGETS_BLOCK_BUILD,
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
    "DIAGNOSIS_NO_CORRECTION",
    "EXPLORATION_STALLED",
    "PENDING_MUTATION_TARGETS_BLOCK_BUILD",
    "REPEATED_ACTION_GATE_VIOLATION",
    "REPEATED_BUILD_FAILURE",
    "REPEATED_RECOVERABLE_TOOL_REJECTION",
    "REPEATED_NO_OP_TOOL_CALLS",
    "REPEATED_SEMANTIC_VALIDATION_FAILURE",
    "REPEATED_UNRESOLVED_MUTATION_TARGETS",
    "SEMANTIC_REPAIR_NO_MUTATION",
    "TOOL_REJECTED",
    "is_agent_terminal_failure",
]
