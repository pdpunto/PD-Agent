from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pd_agent.artifacts import ArtifactValidator
from pd_agent.brain import KnowledgeEnvironment
from pd_agent.context import ContextManager
from pd_agent.core import AgentResponse, BuildResult, FabricRequirement, FabricTaskContract, RunStatus
from pd_agent.fabric import FabricNormalOrchestrator
from pd_agent.fabric.orchestration import FabricOrchestrationStatus
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot


class FakeInspector:
    def __init__(self, status=ProjectInspectionStatus.READY):
        self.status = status

    def inspect(self, root):
        return ProjectSnapshot(project_root=Path(root), status=self.status)


class FakeProvider:
    def __init__(self, response=None):
        self.response = response or AgentResponse(assistant_message="done")
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return self.response


class FakeBuildRunner:
    def __init__(self):
        self.calls = 0

    def run(self, project_snapshot, run_state, limits):
        self.calls += 1
        return BuildResult(attempt=self.calls, command_display="build", cwd=None, started_at=datetime.now(timezone.utc), duration_seconds=0.1, exit_code=0, stdout_log="", stderr_log="")


def _contract() -> FabricTaskContract:
    return FabricTaskContract(task_id="normal-task", revision="1", goal="add a Fabric feature", requirements=(FabricRequirement(requirement_id="r1", description="source change"),))


def _orchestrator(provider=None, inspector=None, build=None):
    return FabricNormalOrchestrator(provider=provider or FakeProvider(), build_runner=build or FakeBuildRunner(), artifact_validator=ArtifactValidator(), context_manager=ContextManager(), project_inspector=inspector or FakeInspector())


def test_normal_run_creates_contract_plan_ledger_and_uses_gate(tmp_path: Path) -> None:
    result = _orchestrator().run(_contract(), tmp_path, brain_enabled=False)
    assert result.contract_identity == _contract().identity()
    assert result.status.value == "INCOMPLETE"
    assert result.completion.pending_requirement_ids == ("r1",)


def test_provider_done_does_not_force_complete(tmp_path: Path) -> None:
    result = _orchestrator().run(_contract(), tmp_path, brain_enabled=False)
    assert result.completion.complete is False
    assert result.completion.reason == "required current evidence is incomplete"


def test_inspection_failure_is_blocked_without_provider_call(tmp_path: Path) -> None:
    provider = FakeProvider()
    result = _orchestrator(provider, FakeInspector(ProjectInspectionStatus.BLOCKED)).run(_contract(), tmp_path)
    assert result.status.value == "BLOCKED"
    assert provider.calls == 0


def test_brain_off_does_not_need_knowledge_service(tmp_path: Path) -> None:
    result = _orchestrator().run(_contract(), tmp_path, brain_enabled=False)
    assert result.status.value == "INCOMPLETE"


def test_mapping_input_is_structured_contract(tmp_path: Path) -> None:
    result = _orchestrator().run(_contract().to_dict(), tmp_path, brain_enabled=False)
    assert result.contract_identity == _contract().identity()


def test_normal_path_reuses_one_agent_runtime_and_build_boundary(tmp_path: Path) -> None:
    provider = FakeProvider()
    build = FakeBuildRunner()
    result = _orchestrator(provider, build=build).run(_contract(), tmp_path, brain_enabled=False)
    assert provider.calls >= 1
    assert build.calls == 1
    assert result.run_id


def test_legacy_terminal_state_is_not_completion_authority(tmp_path: Path) -> None:
    result = _orchestrator().run(_contract(), tmp_path, brain_enabled=False)
    assert result.status in {FabricOrchestrationStatus.INCOMPLETE, FabricOrchestrationStatus.BLOCKED}
    assert RunStatus.COMPLETED.value == "COMPLETED"


def test_product_module_does_not_import_benchmark() -> None:
    import inspect
    import pd_agent.fabric.orchestration as module

    assert "pd_agent.benchmark" not in inspect.getsource(module)
