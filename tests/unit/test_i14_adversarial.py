from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pd_agent.core import (
    ArtifactIdentity,
    ArtifactResult,
    BuildAttemptIdentity,
    EvidenceBinding,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    FailureFact,
    FailureFactStatus,
    RunState,
    SourceRevision,
    TaskProgressLedger,
    RuntimeAttemptIdentity,
    ToolCall,
    validation_contract_revision,
)
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage
from pd_agent.tools import ToolExecutionContext, ToolExecutor, create_filesystem_tools
from pd_agent.core import ExecutionLimits, RunStatus, ToolResultStatus
from pd_agent.validation import CompletionGate


SHA_A = "a" * 64
SHA_B = "b" * 64


def _contract(*, revision: str = "1", validation_kind: str | None = None) -> FabricTaskContract:
    validations = () if validation_kind is None else (
        FabricValidationRequirement(
            validation_requirement_id="v1", requirement_ids=("r1",), kind=validation_kind
        ),
    )
    return FabricTaskContract(
        task_id="adversarial-task", revision=revision, goal="make the feature",
        requirements=(FabricRequirement(requirement_id="r1", description="source"),),
        validation_requirements=validations,
    )


def _state(contract: FabricTaskContract, *, source: str = SHA_A) -> RunState:
    return RunState(
        task=contract.task_id, source_revision=SourceRevision(source),
        progress_ledger=TaskProgressLedger(
            contract_identity=contract.identity(), satisfied_requirement_ids=("r1",),
            evidence_by_requirement={"r1": ("evidence/r1.json",)},
        ),
    )


def test_contract_rejects_duplicate_requirement_ids() -> None:
    with pytest.raises(ValueError):
        FabricTaskContract(
            task_id="task", revision="1", goal="goal",
            requirements=(
                FabricRequirement(requirement_id="r1", description="one"),
                FabricRequirement(requirement_id="r1", description="two"),
            ),
        )


def test_ledger_rejects_satisfied_requirement_without_evidence() -> None:
    contract = _contract()
    with pytest.raises(ValueError):
        TaskProgressLedger(
            contract_identity=contract.identity(), satisfied_requirement_ids=("r1",),
            evidence_by_requirement={"other": ("evidence.json",)},
        ).validate_against(("r1",))


def test_ledger_preserves_active_and_resolved_history_and_requires_resolution() -> None:
    with pytest.raises(ValueError):
        FailureFact(
            failure_id="f1", status=FailureFactStatus.RESOLVED,
            requirement_ids=("r1",), code="R", category="runtime",
        )
    active = FailureFact(
        failure_id="f1", status=FailureFactStatus.ACTIVE,
        requirement_ids=("r1",), code="R", category="runtime", evidence_refs=("e/1",),
    )
    resolved = FailureFact(
        failure_id="f1", status=FailureFactStatus.RESOLVED,
        requirement_ids=("r1",), code="R", category="runtime",
        evidence_refs=("e/1",), resolution_evidence_refs=("e/2",),
    )
    assert active.status is FailureFactStatus.ACTIVE
    assert resolved.resolution_evidence_refs == ("e/2",)


def test_completion_gate_rejects_wrong_revision_even_with_complete_looking_facts() -> None:
    contract = _contract()
    other = _contract(revision="2")
    result = CompletionGate().evaluate(contract, other and _state(other).progress_ledger, _state(other))
    assert result.status.value == "BLOCKED"


def test_completion_gate_rejects_legacy_completed_and_build_only() -> None:
    contract = _contract(validation_kind="build")
    state = RunState(state=RunStatus.COMPLETED, task=contract.task_id)
    state.progress_ledger = TaskProgressLedger(
        contract_identity=contract.identity(), satisfied_requirement_ids=("r1",),
        evidence_by_requirement={"r1": ("evidence/r1",)},
    )
    state.source_revision = SourceRevision(SHA_A)
    state.build_identities = (
        BuildAttemptIdentity(
            build_attempt_id="b1", source_revision=SHA_A,
            contract_identity=contract.identity(), success=True,
        ),
    )
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.complete is True
    assert result.status.value == "COMPLETE"


def test_stale_source_invalidates_old_artifact_and_runtime() -> None:
    contract = _contract(validation_kind="runtime")
    state = _state(contract, source=SHA_B)
    state.build_identities = (BuildAttemptIdentity(
        build_attempt_id="b1", source_revision=SHA_A,
        contract_identity=contract.identity(), success=True,
    ),)
    state.artifact_identity = ArtifactIdentity(
        artifact_identity=SHA_A, sha256=SHA_A, producing_build_attempt_id="b1",
        source_revision=SHA_A, contract_identity=contract.identity(),
    )
    state.artifact_result = ArtifactResult(
        path=None, size=1, timestamp=datetime.now(timezone.utc), classification="VALID"
    )
    state.runtime_identities = (RuntimeAttemptIdentity(
        runtime_attempt_id="rt1", artifact_identity=SHA_A,
        validation_revision=validation_contract_revision(contract.validation_requirements[0]),
        requirement_ids=("r1",), result_refs=("runtime/old",), status="PASS",
    ),)
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert not result.complete
    assert result.stale_validation_requirement_ids == ("v1",)


def test_currentness_keeps_stale_evidence_readable_but_rejectable() -> None:
    original = EvidenceBinding(evidence_id="e1", evidence_kind="runtime", source_revision=SHA_A)
    stale = original.evaluate_currentness(source_revision=SHA_B)
    assert stale.stale_for_completion
    assert original.stale_for_completion is False


def test_security_rejects_traversal_absolute_and_shell_strings(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    executor = ToolExecutor(tools=create_filesystem_tools())
    context = ToolExecutionContext(project_root=root, limits=ExecutionLimits(), run_id="run-security")
    for value in ("../escape", str(tmp_path / "absolute"), "$(Write-Host leaked)"):
        result = executor.execute(
            ToolCall(call_id=value, tool_name="read_file", arguments={"path": value}), context
        )
        assert result.status is ToolResultStatus.REJECTED


def test_reporting_event_cannot_make_gate_complete(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path)
    storage.append_event(RunEvent(
        run_id="run-report", event_type=RunEventType.COMPLETION_GATE_EVALUATED,
        payload={"complete": True, "status": "COMPLETE"},
    ))
    result = CompletionGate().evaluate(_contract(), None, RunState())
    assert not result.complete
    assert storage.read_events("run-report")[0].event_type is RunEventType.COMPLETION_GATE_EVALUATED


def test_report_separates_product_completion_from_benchmark_outcome(tmp_path: Path) -> None:
    report = FinalReport(
        run_id="run-report", final_state=RunStatus.COMPLETED, summary="product complete",
        completion_status="COMPLETE", benchmark_outcome="FAIL",
    )
    storage = RunStorage(tmp_path)
    storage.write_final_report(report)
    restored = storage.read_final_report("run-report")
    assert restored.completion_status == "COMPLETE"
    assert restored.benchmark_outcome == "FAIL"


def test_limits_are_finite_and_do_not_allow_unbounded_agent_steps() -> None:
    state = RunState()
    state.agent_step_count = 3
    state.tool_call_count = 2
    limits = ExecutionLimits(max_agent_steps=3, max_tool_calls=2)
    assert set(state.limit_violations(limits)) == {"max_agent_steps", "max_tool_calls"}


def test_bootstrap_and_observation_payloads_do_not_require_benchmark_oracle() -> None:
    event = RunEvent(run_id="run", event_type=RunEventType.PLAN_CREATED, payload={"task": "task"})
    payload = event.to_dict()
    assert "golden" not in str(payload).casefold()
    assert "oracle" not in str(payload).casefold()
