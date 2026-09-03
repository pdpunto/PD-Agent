from __future__ import annotations

from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from pd_agent.fabric import FabricNormalOrchestrator
from pd_agent.product import (
    ExecutionRecord,
    ExecutionService,
    ExecutionServiceError,
    ProductCatalog,
    ProductFabricTaskContractError,
    ProductFabricTaskContractResolver,
    ProjectService,
)
from pd_agent.product.fabric import FabricProductExecutionRunner
from pd_agent.project import ProjectInspector


FIXTURE = Path("benchmarks/projects/v0_5_fabric_base")
REQUEST = (
    "Add a craftable utility block called Server Core, register the matching "
    "block item, and add its English display-name resource and crafting recipe."
)


def _imported_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "imported-fabric"
    shutil.copytree(FIXTURE, workspace)
    return workspace


def _runner() -> FabricProductExecutionRunner:
    return FabricProductExecutionRunner(
        orchestrator=SimpleNamespace(),
        resolver=ProductFabricTaskContractResolver(),
        inspector=ProjectInspector(),
    )


def test_imported_supported_workspace_needs_no_bootstrap_manifest(tmp_path: Path) -> None:
    workspace = _imported_workspace(tmp_path)
    manifests = tuple(workspace.rglob("bootstrap-manifest.json"))
    assert not manifests

    projects = ProjectService(ProductCatalog(tmp_path / "product-data"))
    project = projects.import_project("Imported Fabric", workspace)
    task = projects.create_task(project.project_id, REQUEST)
    contract = _runner().preflight(project, task)

    assert contract.environment_constraints.minecraft_version == "1.21.11"
    assert contract.environment_constraints.extra["platform_id"] == "fabric-minecraft-1.21.11"
    assert contract.environment_constraints.extra["project_root"] == str(workspace.resolve())


def test_imported_currentness_mutation_fails_and_restore_passes(tmp_path: Path) -> None:
    workspace = _imported_workspace(tmp_path)
    projects = ProjectService(ProductCatalog(tmp_path / "product-data"))
    project = projects.register_project("Imported Fabric", workspace)
    task_one = projects.create_task(project.project_id, REQUEST)
    task_two = projects.create_task(project.project_id, REQUEST)
    runner = _runner()

    first = runner.preflight(project, task_one)
    properties = workspace / "gradle.properties"
    original = properties.read_text(encoding="utf-8")
    properties.write_text(original.replace("minecraft_version=1.21.11", "minecraft_version=1.20.1"), encoding="utf-8")
    try:
        with pytest.raises(ProductFabricTaskContractError) as raised:
            runner.preflight(project, task_two)
        assert raised.value.code == "UNSUPPORTED_PLATFORM"
    finally:
        properties.write_text(original, encoding="utf-8")

    restored = runner.preflight(project, task_two)
    assert first.environment_constraints == restored.environment_constraints
    assert first.validation_requirements == restored.validation_requirements


def test_stale_manifest_and_historical_metadata_cannot_authorize_current_platform(tmp_path: Path) -> None:
    workspace = _imported_workspace(tmp_path)
    projects = ProjectService(ProductCatalog(tmp_path / "product-data"))
    project = projects.register_project("Imported Fabric", workspace)
    task = projects.create_task(project.project_id, REQUEST)
    runner = _runner()
    runner.preflight(project, task)
    projects.catalog.add_execution(ExecutionRecord(task_id=task.task_id))

    properties = workspace / "gradle.properties"
    original = properties.read_text(encoding="utf-8")
    properties.write_text(original.replace("loader_version=0.19.3", "loader_version=0.20.0"), encoding="utf-8")
    try:
        with pytest.raises(ProductFabricTaskContractError) as raised:
            runner.preflight(project, task)
        assert raised.value.code == "UNSUPPORTED_PLATFORM"
    finally:
        properties.write_text(original, encoding="utf-8")


def test_consecutive_tasks_reinspect_same_imported_workspace(tmp_path: Path) -> None:
    workspace = _imported_workspace(tmp_path)
    projects = ProjectService(ProductCatalog(tmp_path / "product-data"))
    project = projects.register_project("Imported Fabric", workspace)
    runner = _runner()

    task_one = projects.create_task(project.project_id, REQUEST)
    task_two = projects.create_task(project.project_id, REQUEST)
    first = runner.preflight(project, task_one)
    second = runner.preflight(project, task_two)

    assert first.environment_constraints == second.environment_constraints
    assert first.validation_requirements == second.validation_requirements
    assert task_one.task_id != task_two.task_id


def test_currentness_failure_after_history_creates_no_new_execution_or_worker(tmp_path: Path) -> None:
    workspace = _imported_workspace(tmp_path)
    catalog = ProductCatalog(tmp_path / "product-data")
    projects = ProjectService(catalog)
    project = projects.register_project("Imported Fabric", workspace)
    task = projects.create_task(project.project_id, REQUEST)
    runner = _runner()
    runner.preflight(project, task)
    historical = ExecutionRecord(task_id=task.task_id)
    catalog.add_execution(historical)
    calls: list[str] = []

    class ProductRunner:
        def preflight(self, received_project, received_task):  # noqa: ANN001
            calls.append("preflight")
            return runner.preflight(received_project, received_task)

        def run(self, *_args):  # noqa: ANN001
            calls.append("worker")
            raise AssertionError("worker must not run after currentness failure")

    properties = workspace / "gradle.properties"
    original = properties.read_text(encoding="utf-8")
    properties.write_text(original.replace("fabric_api_version=0.141.6+1.21.11", "fabric_api_version=0.141.7+1.21.11"), encoding="utf-8")
    service = ExecutionService(catalog, SimpleNamespace(storage=None), projects, product_runner=ProductRunner())
    try:
        with pytest.raises(ExecutionServiceError) as raised:
            service.start(task.task_id)
        assert raised.value.code == "UNSUPPORTED_PLATFORM"
        assert calls == ["preflight"]
        assert tuple(catalog.snapshot()["executions"]) == (historical.execution_id,)
    finally:
        service.shutdown()
        properties.write_text(original, encoding="utf-8")


def test_product_runtime_uses_current_contract_environment_for_brain_boundary(tmp_path: Path) -> None:
    workspace = _imported_workspace(tmp_path)
    projects = ProjectService(ProductCatalog(tmp_path / "product-data"))
    project = projects.register_project("Imported Fabric", workspace)
    task = projects.create_task(project.project_id, REQUEST)
    contract = _runner().preflight(project, task)

    environment = FabricNormalOrchestrator._knowledge_environment(contract)

    assert environment.minecraft_version == "1.21.11"
    assert environment.loader_version == "0.19.3"
    assert environment.fabric_api_version == "0.141.6+1.21.11"
    assert environment.mappings_version == "1.21.11+build.6"
    assert environment.java_version == "21"
