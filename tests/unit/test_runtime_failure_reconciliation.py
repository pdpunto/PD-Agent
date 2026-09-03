from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from pd_agent.build import BuildOrchestrationResult, BuildOrchestrationStatus
from pd_agent.core import (
    ArtifactIdentity,
    BuildResult,
    FailureFact,
    FailureFactStatus,
    RunState,
    RuntimeAttemptIdentity,
    TaskProgressLedger,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
)
from pd_agent.minecraft import RuntimeOrchestrationStatus, RuntimeValidationOutcome
from pd_agent.runtime import FabricRepairOrchestrator, FailureReconciler, RepairStatus, RepairTurnResult


SHA = "a" * 64
CONTRACT = ("task", "1", "f" * 64)


def _failure(category: str = "COMPILATION_ERROR", requirements: tuple[str, ...] = ("r1",)) -> FailureFact:
    return FailureFact(
        failure_id="failure-1",
        status=FailureFactStatus.ACTIVE,
        requirement_ids=requirements,
        code="BUILD_ERROR",
        category=category,
        evidence_refs=("evidence/failure.json",),
    )


def _state() -> RunState:
    return RunState(task="task", progress_ledger=TaskProgressLedger(contract_identity=CONTRACT))


def _artifact(build_id: str = "build-2", artifact_id: str = SHA, source_revision: str = SHA) -> ArtifactIdentity:
    return ArtifactIdentity(
        artifact_identity=artifact_id,
        sha256=SHA,
        producing_build_attempt_id=build_id,
        source_revision=source_revision,
        contract_identity=CONTRACT,
    )


def _build(source: str = SHA, artifact: ArtifactIdentity | None = None) -> BuildOrchestrationResult:
    artifact = artifact or _artifact(source_revision=source)
    result = BuildResult(
        attempt=2,
        command_display="gradle build",
        cwd=None,
        started_at=datetime.now(timezone.utc),
        duration_seconds=0.1,
        exit_code=0,
        stdout_log="",
        stderr_log="",
    )
    return BuildOrchestrationResult(
        status=BuildOrchestrationStatus.BUILT,
        source_revision=source,
        build_attempt_id=artifact.producing_build_attempt_id,
        build_result=result,
        artifact_identity=artifact,
    )


def _runtime(artifact: ArtifactIdentity, *, requirement: str = "r1", revision: str = "v1") -> RuntimeValidationOutcome:
    validation = ValidationResult(stage=ValidationStage.RUNTIME, status=ValidationStatus.PASS, summary="runtime passed", evidence_refs=("runtime/pass.json",))
    identity = RuntimeAttemptIdentity(
        runtime_attempt_id="runtime-2",
        artifact_identity=artifact.artifact_identity,
        validation_revision=revision,
        requirement_ids=(requirement,),
        result_refs=("runtime/pass.json",),
        status="PASS",
    )
    return RuntimeValidationOutcome(status=RuntimeOrchestrationStatus.VALIDATED, validation_result=validation, runtime_identity=identity)


def test_blocked_failure_does_not_trigger_repair() -> None:
    calls = []
    result = FabricRepairOrchestrator(repair_turn=lambda request: calls.append(request)).repair_build(
        run_state=_state(), failure=_failure("BLOCKED"), project_root=Path.cwd(), build=lambda source: None
    )
    assert result.status is RepairStatus.NOT_ELIGIBLE
    assert calls == []


def test_provider_text_without_file_changed_is_not_a_repair(tmp_path: Path) -> None:
    (tmp_path / "source.txt").write_text("old", encoding="utf-8")
    result = FabricRepairOrchestrator(repair_turn=lambda request: RepairTurnResult(provider_result="fixed")).repair_build(
        run_state=_state(), failure=_failure(), project_root=tmp_path, build=lambda source: (_ for _ in ()).throw(AssertionError("build must not run"))
    )
    assert result.status is RepairStatus.STAGNATED


def test_file_changed_new_revision_builds_and_resolves_failure(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"

    def repair(request):
        source.write_text("new", encoding="utf-8")
        return RepairTurnResult(changed_files=("source.txt",), evidence_refs=("repair/turn.json",))

    state = _state()
    result = FabricRepairOrchestrator(repair_turn=repair).repair_build(
        run_state=state, failure=_failure(), project_root=tmp_path, build=lambda revision: _build(revision)
    )
    assert result.status is RepairStatus.REPAIRED
    assert result.source_revision_before != result.source_revision_after
    assert [item.status for item in state.progress_ledger.failures] == [FailureFactStatus.ACTIVE, FailureFactStatus.RESOLVED]


def test_unrelated_build_does_not_resolve_failure() -> None:
    state = _state()
    artifact = ArtifactIdentity(artifact_identity=SHA, sha256=SHA, producing_build_attempt_id="build-2", source_revision=SHA, contract_identity=("other", "1", "e" * 64))
    assert not FailureReconciler().reconcile_build(state, _failure(), build=_build(artifact=artifact), source_revision=SHA)
    assert len(state.progress_ledger.failures) == 0


def test_runtime_pass_requires_current_artifact_revision_and_requirements() -> None:
    state = _state()
    failure = _failure(category="RUNTIME")
    artifact = _artifact()
    outcome = _runtime(artifact)
    reconciler = FailureReconciler()
    assert reconciler.reconcile_runtime(state, failure, runtime=outcome, artifact=artifact, requirement_ids=("r1",), validation_revision="v1")
    assert len(state.progress_ledger.failures) == 1


def test_runtime_resolution_deduplicates_evidence_refs_preserving_order() -> None:
    state = _state()
    failure = _failure(category="RUNTIME")
    artifact = _artifact()
    outcome = _runtime(artifact)
    identity = replace(outcome.runtime_identity, result_refs=("runtime/pass.json", "runtime/pass.json", "runtime/second.json"))
    outcome = replace(outcome, runtime_identity=identity)

    assert FailureReconciler().reconcile_runtime(
        state, failure, runtime=outcome, artifact=artifact, requirement_ids=("r1",), validation_revision="v1"
    )
    resolved = state.progress_ledger.failures[0]
    assert resolved.resolution_evidence_refs == ("runtime/pass.json", "runtime/second.json")


def test_runtime_old_artifact_or_wrong_requirement_does_not_resolve() -> None:
    state = _state()
    failure = _failure(category="RUNTIME")
    artifact = _artifact()
    old = _runtime(ArtifactIdentity(artifact_identity="b" * 64, sha256=SHA, producing_build_attempt_id="build-old", source_revision=SHA, contract_identity=CONTRACT))
    reconciler = FailureReconciler()
    assert not reconciler.reconcile_runtime(state, failure, runtime=old, artifact=artifact, requirement_ids=("r1",), validation_revision="v1")
    assert not reconciler.reconcile_runtime(state, failure, runtime=_runtime(artifact, requirement="other"), artifact=artifact, requirement_ids=("r1",), validation_revision="v1")


def test_runtime_resolution_keeps_unrelated_active_failure() -> None:
    state = _state()
    first = _failure(category="RUNTIME", requirements=("r1",))
    second = replace(first, failure_id="failure-2", requirement_ids=("r2",), fingerprint=None)
    state.progress_ledger = replace(state.progress_ledger, failures=(first, second))
    artifact = _artifact()

    assert FailureReconciler().reconcile_runtime(
        state,
        first,
        runtime=_runtime(artifact, requirement="r1"),
        artifact=artifact,
        requirement_ids=("r1",),
        validation_revision="v1",
    )
    latest = {item.failure_id: item for item in state.progress_ledger.failures}
    assert latest["failure-1"].status is FailureFactStatus.RESOLVED
    assert latest["failure-2"].status is FailureFactStatus.ACTIVE


def test_repair_cycle_limit_is_enforced_and_context_is_bounded(tmp_path: Path) -> None:
    seen = []
    source = tmp_path / "source.txt"

    def repair(request):
        seen.append(request)
        source.write_text("new", encoding="utf-8")
        return RepairTurnResult(changed_files=("source.txt",))

    orchestrator = FabricRepairOrchestrator(repair_turn=repair, max_cycles=1)
    first = orchestrator.repair_build(run_state=_state(), failure=_failure(), project_root=tmp_path, build=lambda revision: _build(revision))
    second = orchestrator.repair_build(run_state=_state(), failure=_failure(), project_root=tmp_path, build=lambda revision: _build(revision))
    assert first.status is RepairStatus.REPAIRED
    assert second.status is RepairStatus.BLOCKED
    assert seen[0].failure_code == "BUILD_ERROR"
    assert not hasattr(seen[0], "raw_logs")
