from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pd_agent.context import ContextManager
from pd_agent.core import (
    RunState,
    RunStatus,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    ValidationViolation,
)
from pd_agent.reporting import RunEventType
from pd_agent.runtime import AgentRuntime


def _failure(*, code: str = "SAME_ROOT_CAUSE", category: str = "invalid") -> ValidationResult:
    return ValidationResult(
        stage=ValidationStage.PRE_BUILD,
        status=ValidationStatus.REPAIRABLE_FAIL,
        summary="invalid source",
        violations=(ValidationViolation(
            code=code,
            requirement="source",
            observed={"category": category},
            expected="valid source",
            actual="invalid source",
            message="the root cause remains",
            phase="PRE_BUILD",
            evidence_refs=("src/Main.java",),
        ),),
    )


def _pass() -> ValidationResult:
    return ValidationResult(
        stage=ValidationStage.PRE_BUILD,
        status=ValidationStatus.PASS,
        summary="valid source",
    )


def _runtime(tmp_path: Path, validator: object, events: list[object]) -> AgentRuntime:
    return AgentRuntime(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
        context_manager=ContextManager(),
        pre_build_validator=validator,
        reporting=SimpleNamespace(append_event=events.append),
    )


def _state(tmp_path: Path) -> RunState:
    state = RunState(project_root=tmp_path, task="r35")
    state.transition_to(RunStatus.INSPECTING)
    state.transition_to(RunStatus.PLANNING)
    state.transition_to(RunStatus.EDITING)
    state.record_changed_file("src/Main.java")
    return state


def test_r35_same_failure_is_reported_after_ineffective_repair(tmp_path: Path) -> None:
    class Validator:
        def validate(self, *_args):
            return _failure()

    events: list[object] = []
    runtime = _runtime(tmp_path, Validator(), events)
    state = _state(tmp_path)
    history: list[object] = []
    snapshot = SimpleNamespace(project_root=tmp_path)

    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"

    feedback = history[-1].content
    repair_events = [event for event in events if event.event_type is RunEventType.SEMANTIC_REPAIR_FEEDBACK]
    assert "REPEATED_FAILURE_AFTER_INEFFECTIVE_REPAIR" in feedback
    assert "previous_failure_signature:" in feedback
    assert "src/Main.java" in feedback
    assert len(repair_events) == 2
    assert repair_events[0].payload["classification"] == "FIRST_FAILURE"
    assert repair_events[0].payload["previous_repair_attempt_ref"] is None
    assert repair_events[0].payload["previous_failure_signature"] is None
    assert repair_events[0].payload["previous_mutation_refs"] == []
    assert repair_events[-1].payload["classification"] == "REPEATED_FAILURE_AFTER_INEFFECTIVE_REPAIR"
    assert repair_events[-1].payload["ineffective_repair"] is True
    assert repair_events[-1].payload["previous_repair_attempt_ref"] is not None
    assert state.ineffective_repair is True
    assert state.ineffective_repair_ref == state.last_repair_attempt_ref


def test_r35_successful_repair_clears_ineffective_marker(tmp_path: Path) -> None:
    class Validator:
        results = iter((_failure(), _failure(), _pass()))

        def validate(self, *_args):
            return next(self.results)

    events: list[object] = []
    runtime = _runtime(tmp_path, Validator(), events)
    state = _state(tmp_path)
    history: list[object] = []
    snapshot = SimpleNamespace(project_root=tmp_path)

    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "PASS"
    assert state.ineffective_repair is False
    assert state.ineffective_repair_ref is None


def test_r35_different_failure_is_not_marked_ineffective(tmp_path: Path) -> None:
    class Validator:
        results = iter((_failure(code="FIRST", category="first"), _failure(code="SECOND", category="second")))

        def validate(self, *_args):
            return next(self.results)

    events: list[object] = []
    runtime = _runtime(tmp_path, Validator(), events)
    state = _state(tmp_path)
    history: list[object] = []
    snapshot = SimpleNamespace(project_root=tmp_path)

    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    assert "REPEATED_FAILURE_AFTER_INEFFECTIVE_REPAIR" not in history[-1].content
    assert state.ineffective_repair is False
    assert events[-1].payload["classification"] == "FIRST_FAILURE"


def test_r35_third_same_failure_fails_closed(tmp_path: Path) -> None:
    class Validator:
        def validate(self, *_args):
            return _failure()

    runtime = _runtime(tmp_path, Validator(), [])
    state = _state(tmp_path)
    history: list[object] = []
    snapshot = SimpleNamespace(project_root=tmp_path)

    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "FAILED"
    assert state.termination_reason == "repeated semantic validation failure"


def test_r35_repair_evidence_round_trips_through_run_state(tmp_path: Path) -> None:
    state = _state(tmp_path)
    signature = "failure-signature"
    attempt_ref = state.record_repair_attempt(signature)
    state.record_ineffective_repair()

    restored = RunState.from_dict(state.to_dict())

    assert restored.repair_attempt_count == 1
    assert restored.last_repair_attempt_ref == attempt_ref
    assert restored.last_repair_failure_signature == signature
    assert restored.last_repair_mutation_refs == ("src/Main.java",)
    assert restored.ineffective_repair is True
    assert restored.ineffective_repair_ref == attempt_ref
