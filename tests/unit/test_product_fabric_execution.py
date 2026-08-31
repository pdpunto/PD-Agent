from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pd_agent.core import (
    FabricEnvironmentConstraints,
    FabricRequirement,
    FabricTaskContract,
    RunStateError,
    RunStatus,
)
from pd_agent.fabric import FabricNormalOrchestrator
from pd_agent.product import (
    ExecutionRecord,
    FabricProductExecutionRunner,
    ProductFabricTaskContractError,
    ProductFabricTaskContractResolver,
    ProjectRecord,
    TaskRecord,
)
from pd_agent.project import DetectedValue, FabricManifest, ProjectInspectionStatus, ProjectSnapshot
from pd_agent.reporting import FinalReport, RunStorage


REQUEST = (
    "Add a craftable utility block called Server Core to Example Mod, register the matching "
    "block item, and add its English display-name resource and crafting recipe while preserving "
    "the existing mod id and entrypoints."
)


def _snapshot(root: Path) -> ProjectSnapshot:
    return ProjectSnapshot(
        project_root=root,
        status=ProjectInspectionStatus.READY,
        fabric_manifests=(FabricManifest(path=root / "fabric.mod.json", mod_id="examplemod", version="1", environment="*"),),
        source_roots=(root / "src" / "main" / "java",),
        resource_roots=(root / "src" / "main" / "resources",),
        detected_versions={
            "minecraft_version": DetectedValue("1.21.11", "test"),
            "loader_version": DetectedValue("0.19.3", "test"),
            "fabric_api_version": DetectedValue("0.141.6+1.21.11", "test"),
            "yarn_version": DetectedValue("1.21.11+build.6", "test"),
            "loom": DetectedValue("1.13.3", "test"),
            "java_version": DetectedValue("21", "test"),
        },
    )


def _records(tmp_path: Path) -> tuple[ProjectRecord, TaskRecord, ProjectSnapshot]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = ProjectRecord(project_id=str(uuid4()), name="Demo", workspace_ref=str(workspace))
    task = TaskRecord(task_id=str(uuid4()), project_id=project.project_id, request=REQUEST)
    return project, task, _snapshot(workspace)


def test_resolver_preserves_product_task_and_builds_conditional_contract(tmp_path: Path) -> None:
    project, task, snapshot = _records(tmp_path)

    contract = ProductFabricTaskContractResolver().resolve(project, task, snapshot)

    assert contract.task_id == task.task_id
    assert contract.goal == REQUEST
    assert contract.validation_requirements
    assert {item.kind for item in contract.validation_requirements} == {"build", "artifact", "minecraft"}
    assert contract.environment_constraints.minecraft_version == "1.21.11"
    assert contract.environment_constraints.extra["loom_version"] == "1.13.3"
    assert contract.environment_constraints.extra["mappings_namespace"] == "yarn"
    assert contract.mutation_expectations


def test_resolver_rejects_unsupported_or_wrong_owner(tmp_path: Path) -> None:
    project, task, snapshot = _records(tmp_path)
    resolver = ProductFabricTaskContractResolver()
    unsupported = TaskRecord(task_id=str(uuid4()), project_id=project.project_id, request="do something ambiguous")

    with pytest.raises(ProductFabricTaskContractError, match="not supported"):
        resolver.resolve(project, unsupported, snapshot)
    wrong_project = ProjectRecord(project_id=str(uuid4()), name="Other", workspace_ref=project.workspace_ref)
    with pytest.raises(ProductFabricTaskContractError, match="does not belong"):
        resolver.resolve(wrong_project, task, snapshot)


def test_resolver_accepts_canonical_spanish_server_core_request(tmp_path: Path) -> None:
    project, _task, snapshot = _records(tmp_path)
    task = TaskRecord(
        task_id=str(uuid4()),
        project_id=project.project_id,
        request=(
            "Añade un bloque utilitario craftable llamado Server Core, incluyendo su "
            "block item, recursos en_us y receta, preservando el mod y los entrypoints existentes."
        ),
    )

    contract = ProductFabricTaskContractResolver().resolve(project, task, snapshot)

    assert contract.goal == task.request


def test_resolver_rejects_partial_server_core_wording(tmp_path: Path) -> None:
    project, _task, snapshot = _records(tmp_path)
    task = TaskRecord(task_id=str(uuid4()), project_id=project.project_id, request="Add Server Core")

    with pytest.raises(ProductFabricTaskContractError, match="not supported"):
        ProductFabricTaskContractResolver().resolve(project, task, snapshot)


def test_product_runner_delegates_contract_workspace_and_identity(tmp_path: Path) -> None:
    project, task, snapshot = _records(tmp_path)
    execution_id = str(uuid4())
    execution = ExecutionRecord(execution_id=execution_id, task_id=task.task_id, run_id=execution_id)
    calls: list[tuple[object, Path, str]] = []

    class FakeResolver:
        def resolve(self, received_project, received_task, received_snapshot):
            assert received_project == project
            assert received_task == task
            assert received_snapshot == snapshot
            return "contract"

    class FakeOrchestrator:
        def run(self, contract, root, *, run_id):
            calls.append((contract, root, run_id))
            return "result"

    result = FabricProductExecutionRunner(FakeOrchestrator(), FakeResolver(), SimpleNamespace(inspect=lambda _: snapshot)).run(execution, project, task)

    assert result == "result"
    assert calls == [("contract", snapshot.project_root, execution_id)]


def test_product_runner_rejects_identity_mismatch(tmp_path: Path) -> None:
    project, task, _snapshot_value = _records(tmp_path)
    execution = ExecutionRecord(execution_id=str(uuid4()), task_id=task.task_id, run_id=str(uuid4()))

    with pytest.raises(ProductFabricTaskContractError, match="execution_id must equal run_id"):
        FabricProductExecutionRunner(object()).run(execution, project, task)


def test_fabric_orchestrator_persists_supplied_identity_and_rejects_collision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import pd_agent.fabric.orchestration as module

    project, _task, snapshot = _records(tmp_path)
    storage = RunStorage(tmp_path / "runs")

    class FakeRuntime:
        def __init__(self, **_kwargs):
            pass

        def run(self, *, run_state, **_kwargs):
            return run_state, FinalReport(run_id=run_state.run_id, final_state=run_state.state, summary="test")

    monkeypatch.setattr(module, "AgentRuntime", FakeRuntime)
    orchestrator = FabricNormalOrchestrator(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
        context_manager=object(),
        project_inspector=SimpleNamespace(inspect=lambda _: snapshot),
        reporting=storage,
    )
    contract = FabricTaskContract(
        task_id="product-task",
        revision="1",
        goal="test",
        requirements=(FabricRequirement(requirement_id="r1", description="change"),),
        environment_constraints=FabricEnvironmentConstraints(),
    )
    supplied = str(uuid4())

    result = orchestrator.run(contract, snapshot.project_root, brain_enabled=False, run_id=supplied)

    assert result.run_id == supplied
    assert storage.read_run_state(supplied).run_id == supplied
    assert all(event.run_id == supplied for event in storage.read_events(supplied))
    with pytest.raises(RunStateError, match="already exists"):
        orchestrator.run(contract, snapshot.project_root, brain_enabled=False, run_id=supplied)


def test_product_module_does_not_depend_on_benchmark() -> None:
    import pd_agent.product.fabric as module

    assert "pd_agent.benchmark" not in inspect.getsource(module)
