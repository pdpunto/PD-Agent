"""Run state and execution limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

from .contracts import ArtifactResult, BuildResult, FabricTaskContract, ValidationResult
from .errors import LimitReachedError, RunStateError, StateTransitionError
from .progress import ExecutionPlan, TaskProgressLedger


def generate_run_id() -> str:
    """Generate canonical run_id."""

    return str(uuid4())


class RunStatus(StrEnum):
    """Closed set of run states."""

    INITIALIZING = "INITIALIZING"
    INSPECTING = "INSPECTING"
    PLANNING = "PLANNING"
    EDITING = "EDITING"
    BUILDING = "BUILDING"
    DIAGNOSING = "DIAGNOSING"
    CORRECTING = "CORRECTING"
    VALIDATING_ARTIFACT = "VALIDATING_ARTIFACT"
    VALIDATING_FUNCTIONAL = "VALIDATING_FUNCTIONAL"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    LIMIT_REACHED = "LIMIT_REACHED"
    ABORTED = "ABORTED"

    def is_terminal(self) -> bool:
        return self in TERMINAL_STATUSES


TERMINAL_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.BLOCKED,
        RunStatus.LIMIT_REACHED,
        RunStatus.ABORTED,
    }
)

NON_SUCCESS_TERMINAL_STATUSES = frozenset(
    {
        RunStatus.FAILED,
        RunStatus.BLOCKED,
        RunStatus.LIMIT_REACHED,
        RunStatus.ABORTED,
    }
)

VALID_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.INITIALIZING: frozenset({RunStatus.INSPECTING, *NON_SUCCESS_TERMINAL_STATUSES}),
    RunStatus.INSPECTING: frozenset(
        {RunStatus.PLANNING, *NON_SUCCESS_TERMINAL_STATUSES}
    ),
    RunStatus.PLANNING: frozenset({RunStatus.EDITING, *NON_SUCCESS_TERMINAL_STATUSES}),
    RunStatus.EDITING: frozenset({RunStatus.BUILDING, RunStatus.CORRECTING, *NON_SUCCESS_TERMINAL_STATUSES}),
    RunStatus.BUILDING: frozenset(
        {
            RunStatus.VALIDATING_ARTIFACT,
            RunStatus.DIAGNOSING,
            *NON_SUCCESS_TERMINAL_STATUSES,
        }
    ),
    RunStatus.DIAGNOSING: frozenset({RunStatus.CORRECTING, *NON_SUCCESS_TERMINAL_STATUSES}),
    RunStatus.CORRECTING: frozenset({RunStatus.EDITING, RunStatus.BUILDING, *NON_SUCCESS_TERMINAL_STATUSES}),
    RunStatus.VALIDATING_ARTIFACT: frozenset(
        {RunStatus.VALIDATING_FUNCTIONAL, RunStatus.REPORTING, *NON_SUCCESS_TERMINAL_STATUSES}
    ),
    RunStatus.VALIDATING_FUNCTIONAL: frozenset(
        {RunStatus.REPORTING, RunStatus.CORRECTING, *NON_SUCCESS_TERMINAL_STATUSES}
    ),
    RunStatus.REPORTING: frozenset(
        {RunStatus.COMPLETED, *NON_SUCCESS_TERMINAL_STATUSES}
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.BLOCKED: frozenset(),
    RunStatus.LIMIT_REACHED: frozenset(),
    RunStatus.ABORTED: frozenset(),
}


def _coerce_status(value: RunStatus | str) -> RunStatus:
    try:
        return value if isinstance(value, RunStatus) else RunStatus(str(value))
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise RunStateError(f"Invalid run state: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Conservative default limits for v0.1."""

    max_agent_steps: int = 40
    max_tool_calls: int = 120
    max_build_attempts: int = 5
    provider_retry_limit: int = 2
    process_timeout_seconds: int = 600
    max_tool_output_bytes: int = 1_000_000
    max_context_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        for field_name in (
            "max_agent_steps",
            "max_tool_calls",
            "max_build_attempts",
            "provider_retry_limit",
            "process_timeout_seconds",
            "max_tool_output_bytes",
            "max_context_bytes",
        ):
            value = getattr(self, field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")

    def to_dict(self) -> dict[str, int]:
        return {
            "max_agent_steps": self.max_agent_steps,
            "max_tool_calls": self.max_tool_calls,
            "max_build_attempts": self.max_build_attempts,
            "provider_retry_limit": self.provider_retry_limit,
            "process_timeout_seconds": self.process_timeout_seconds,
            "max_tool_output_bytes": self.max_tool_output_bytes,
            "max_context_bytes": self.max_context_bytes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionLimits":
        return cls(
            max_agent_steps=int(data.get("max_agent_steps", 40)),
            max_tool_calls=int(data.get("max_tool_calls", 120)),
            max_build_attempts=int(data.get("max_build_attempts", 5)),
            provider_retry_limit=int(data.get("provider_retry_limit", 2)),
            process_timeout_seconds=int(data.get("process_timeout_seconds", 600)),
            max_tool_output_bytes=int(data.get("max_tool_output_bytes", 1_000_000)),
            max_context_bytes=int(data.get("max_context_bytes", 2_000_000)),
        )


@dataclass(slots=True)
class RunState:
    """Mutable state for one run."""

    run_id: str = field(default_factory=generate_run_id)
    project_root: Path | None = None
    task: str | None = None
    state: RunStatus = RunStatus.INITIALIZING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    project_snapshot: Mapping[str, Any] | None = None
    current_plan: str | None = None
    task_contract: FabricTaskContract | None = None
    execution_plan: ExecutionPlan | None = None
    progress_ledger: TaskProgressLedger | None = None
    changed_files: tuple[str, ...] = ()
    pending_mutation_targets: tuple[str, ...] = ()
    completed_mutation_targets: tuple[str, ...] = ()
    tool_call_count: int = 0
    agent_step_count: int = 0
    logical_provider_request_count: int = 0
    build_attempt_count: int = 0
    consecutive_recoverable_rejections: int = 0
    build_results: tuple[BuildResult, ...] = ()
    artifact_result: ArtifactResult | None = None
    validation_results: tuple[ValidationResult, ...] = ()
    last_validation_signature: str | None = None
    validation_repeat_count: int = 0
    last_error: str | None = None
    provider_error_kind: str | None = None
    provider_error_message: str | None = None
    termination_reason: str | None = None

    def __post_init__(self) -> None:
        self.run_id = str(UUID(self.run_id))
        self.state = _coerce_status(self.state)

    def can_transition_to(self, next_state: RunStatus) -> bool:
        next_state = _coerce_status(next_state)
        if self.state.is_terminal():
            return False
        return next_state in VALID_TRANSITIONS[self.state]

    def transition_to(self, next_state: RunStatus) -> None:
        next_state = _coerce_status(next_state)
        if not self.can_transition_to(next_state):
            raise StateTransitionError(
                f"Invalid transition {self.state.value} -> {next_state.value}"
            )
        self.state = next_state

    def record_agent_step(self) -> None:
        self.agent_step_count += 1

    def record_logical_provider_request(self) -> None:
        self.logical_provider_request_count += 1

    def record_tool_call(self) -> None:
        self.tool_call_count += 1

    def record_build_attempt(self) -> None:
        self.build_attempt_count += 1

    def record_validation_result(self, result: ValidationResult, signature: str | None = None) -> None:
        self.validation_results = (*self.validation_results, result)
        if result.status.value != "REPAIRABLE_FAIL" or signature is None:
            return
        if signature == self.last_validation_signature:
            self.validation_repeat_count += 1
        else:
            self.last_validation_signature = signature
            self.validation_repeat_count = 0

    def reset_validation_stall(self) -> None:
        self.last_validation_signature = None
        self.validation_repeat_count = 0

    def record_changed_file(self, path: Path | str) -> None:
        normalized = Path(path).as_posix()
        if not normalized:
            return
        if normalized in self.changed_files:
            return
        self.changed_files = (*self.changed_files, normalized)

    def set_pending_mutation_targets(self, paths: tuple[Path | str, ...] | list[Path | str]) -> None:
        normalized = tuple(
            dict.fromkeys(
                path if str(path).startswith("role:") else Path(path).as_posix()
                for path in paths
                if str(path)
            )
        )
        completed = set(self.completed_mutation_targets)
        self.pending_mutation_targets = tuple(path for path in normalized if path not in completed)

    def record_completed_mutation_target(self, path: Path | str) -> bool:
        normalized = Path(path).as_posix()
        matching_target = normalized if normalized in self.pending_mutation_targets else None
        if matching_target is None and normalized.startswith("src/main/java/"):
            if "role:source" in self.pending_mutation_targets:
                matching_target = "role:source"
        if matching_target is None:
            return False
        self.pending_mutation_targets = tuple(
            item for item in self.pending_mutation_targets if item != matching_target
        )
        if matching_target not in self.completed_mutation_targets:
            self.completed_mutation_targets = (*self.completed_mutation_targets, matching_target)
        return True

    def record_build_result(self, result: BuildResult) -> None:
        self.build_results = (*self.build_results, result)

    def limit_violations(self, limits: ExecutionLimits) -> tuple[str, ...]:
        violations: list[str] = []
        if self.agent_step_count >= limits.max_agent_steps:
            violations.append("max_agent_steps")
        if self.tool_call_count >= limits.max_tool_calls:
            violations.append("max_tool_calls")
        if self.build_attempt_count >= limits.max_build_attempts:
            violations.append("max_build_attempts")
        return tuple(violations)

    def within_limits(self, limits: ExecutionLimits) -> bool:
        return not self.limit_violations(limits)

    def raise_if_limits_reached(self, limits: ExecutionLimits) -> None:
        violations = self.limit_violations(limits)
        if violations:
            raise LimitReachedError(", ".join(violations))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_root": str(self.project_root) if self.project_root else None,
            "task": self.task,
            "state": self.state.value,
            "started_at": self.started_at.isoformat(),
            "project_snapshot": (
                dict(self.project_snapshot) if self.project_snapshot is not None else None
            ),
            "current_plan": self.current_plan,
            "task_contract": self.task_contract.to_dict() if self.task_contract is not None else None,
            "execution_plan": self.execution_plan.to_dict() if self.execution_plan is not None else None,
            "progress_ledger": self.progress_ledger.to_dict() if self.progress_ledger is not None else None,
            "changed_files": list(self.changed_files),
            "pending_mutation_targets": list(self.pending_mutation_targets),
            "completed_mutation_targets": list(self.completed_mutation_targets),
            "tool_call_count": self.tool_call_count,
            "agent_step_count": self.agent_step_count,
            "logical_provider_request_count": self.logical_provider_request_count,
            "build_attempt_count": self.build_attempt_count,
            "consecutive_recoverable_rejections": self.consecutive_recoverable_rejections,
            "build_results": [item.to_dict() for item in self.build_results],
            "artifact_result": (
                self.artifact_result.to_dict() if self.artifact_result is not None else None
            ),
            "validation_results": [item.to_dict() for item in self.validation_results],
            "last_validation_signature": self.last_validation_signature,
            "validation_repeat_count": self.validation_repeat_count,
            "last_error": self.last_error,
            "provider_error_kind": self.provider_error_kind,
            "provider_error_message": self.provider_error_message,
            "termination_reason": self.termination_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunState":
        return cls(
            run_id=str(data.get("run_id", generate_run_id())),
            project_root=Path(data["project_root"]) if data.get("project_root") else None,
            task=data.get("task"),
            state=_coerce_status(data.get("state", RunStatus.INITIALIZING.value)),
            started_at=datetime.fromisoformat(
                str(data.get("started_at", datetime.now(timezone.utc).isoformat()))
            ),
            project_snapshot=(
                dict(data["project_snapshot"])
                if data.get("project_snapshot") is not None
                else None
            ),
            current_plan=data.get("current_plan"),
            task_contract=(FabricTaskContract.from_dict(data["task_contract"]) if data.get("task_contract") is not None else None),
            execution_plan=(ExecutionPlan.from_dict(data["execution_plan"]) if data.get("execution_plan") is not None else None),
            progress_ledger=(TaskProgressLedger.from_dict(data["progress_ledger"]) if data.get("progress_ledger") is not None else None),
            changed_files=tuple(data.get("changed_files", ())),
            pending_mutation_targets=tuple(data.get("pending_mutation_targets", ())),
            completed_mutation_targets=tuple(data.get("completed_mutation_targets", ())),
            tool_call_count=int(data.get("tool_call_count", 0)),
            agent_step_count=int(data.get("agent_step_count", 0)),
            logical_provider_request_count=int(data.get("logical_provider_request_count", 0)),
            build_attempt_count=int(data.get("build_attempt_count", 0)),
            consecutive_recoverable_rejections=int(data.get("consecutive_recoverable_rejections", 0)),
            build_results=tuple(
                BuildResult.from_dict(item) for item in data.get("build_results", [])
            ),
            artifact_result=(
                ArtifactResult.from_dict(data["artifact_result"])
                if data.get("artifact_result") is not None
                else None
            ),
            validation_results=tuple(
                ValidationResult.from_dict(item) for item in data.get("validation_results", [])
            ),
            last_validation_signature=data.get("last_validation_signature"),
            validation_repeat_count=int(data.get("validation_repeat_count", 0)),
            last_error=data.get("last_error"),
            provider_error_kind=data.get("provider_error_kind"),
            provider_error_message=data.get("provider_error_message"),
            termination_reason=data.get("termination_reason"),
        )
