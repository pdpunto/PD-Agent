from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pd_agent.build import BuildOrchestrationStatus, FabricBuildOrchestrator
from pd_agent.core import (
    BuildResult,
    FabricRequirement,
    FabricTaskContract,
    FailureFactStatus,
    RunState,
    TaskProgressLedger,
)
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot
from pd_agent.validation import PreBuildWorkspaceValidator


def _contract(*, artifact: bool = False) -> FabricTaskContract:
    kind = "artifact" if artifact else "build"
    return FabricTaskContract(
        task_id="task",
        revision="1",
        goal="build a mod",
        requirements=(FabricRequirement(requirement_id="r1", description="source"),),
        validation_requirements=(),
    )


def _snapshot(root: Path) -> ProjectSnapshot:
    return ProjectSnapshot(project_root=root, status=ProjectInspectionStatus.READY, target_subproject=root)


def _result(success: bool) -> BuildResult:
    return BuildResult(attempt=1, command_display="build", cwd=None, started_at=datetime.now(timezone.utc), duration_seconds=0.1, exit_code=0 if success else 1, stdout_log="", stderr_log="" if success else "cannot find symbol")


class FakeBuildRunner:
    def __init__(self, result: BuildResult) -> None:
        self.result = result
        self.calls = 0

    def run(self, project_snapshot, run_state, limits):
        self.calls += 1
        run_state.record_build_attempt()
        run_state.record_build_result(self.result)
        return self.result


def test_prebuild_failure_prevents_build(tmp_path: Path) -> None:
    runner = FakeBuildRunner(_result(True))
    orchestrator = FabricBuildOrchestrator(build_runner=runner, prebuild_validator=PreBuildWorkspaceValidator())
    state = RunState(task="task")
    outcome = orchestrator.ensure_build(project_snapshot=_snapshot(tmp_path), run_state=state, contract=_contract(), limits=object(), prebuild_contract={"required_resources": [{"path": "missing.json"}]})
    assert outcome.status is BuildOrchestrationStatus.PREBUILD_FAILED
    assert runner.calls == 0
    assert state.build_attempt_count == 0


def test_build_fail_is_normalized_and_persisted(tmp_path: Path) -> None:
    contract = _contract()
    state = RunState(task="task", progress_ledger=TaskProgressLedger(contract_identity=contract.identity()))
    outcome = FabricBuildOrchestrator(build_runner=FakeBuildRunner(_result(False))).ensure_build(project_snapshot=_snapshot(tmp_path), run_state=state, contract=contract, limits=object(), source_revision="a" * 64)
    assert outcome.status is BuildOrchestrationStatus.BUILD_FAILED
    assert outcome.normalized_failure is not None
    assert state.progress_ledger is not None
    assert state.progress_ledger.failures[0].status is FailureFactStatus.ACTIVE


def test_success_binding_is_reused_without_redundant_build(tmp_path: Path) -> None:
    contract = _contract()
    runner = FakeBuildRunner(_result(True))
    orchestrator = FabricBuildOrchestrator(build_runner=runner)
    state = RunState(task="task")
    first = orchestrator.ensure_build(project_snapshot=_snapshot(tmp_path), run_state=state, contract=contract, limits=object(), source_revision="a" * 64)
    second = orchestrator.ensure_build(project_snapshot=_snapshot(tmp_path), run_state=state, contract=contract, limits=object(), source_revision="a" * 64)
    assert first.status is BuildOrchestrationStatus.BUILT
    assert second.status is BuildOrchestrationStatus.REUSED
    assert runner.calls == 1


def test_new_source_revision_requires_build_and_resolves_eligible_failure(tmp_path: Path) -> None:
    contract = _contract()
    runner = FakeBuildRunner(_result(False))
    state = RunState(task="task", progress_ledger=TaskProgressLedger(contract_identity=contract.identity()))
    orchestrator = FabricBuildOrchestrator(build_runner=runner)
    failed = orchestrator.ensure_build(project_snapshot=_snapshot(tmp_path), run_state=state, contract=contract, limits=object(), source_revision="a" * 64)
    runner.result = _result(True)
    passed = orchestrator.ensure_build(project_snapshot=_snapshot(tmp_path), run_state=state, contract=contract, limits=object(), source_revision="b" * 64)
    assert failed.status is BuildOrchestrationStatus.BUILD_FAILED
    assert passed.status is BuildOrchestrationStatus.BUILT
    assert [fact.status for fact in state.progress_ledger.failures] == [FailureFactStatus.ACTIVE, FailureFactStatus.RESOLVED]


def test_build_pass_does_not_mark_requirements_satisfied(tmp_path: Path) -> None:
    contract = _contract()
    state = RunState(task="task", progress_ledger=TaskProgressLedger(contract_identity=contract.identity()))
    FabricBuildOrchestrator(build_runner=FakeBuildRunner(_result(True))).ensure_build(project_snapshot=_snapshot(tmp_path), run_state=state, contract=contract, limits=object(), source_revision="a" * 64)
    assert state.progress_ledger is not None
    assert state.progress_ledger.satisfied_requirement_ids == ()
