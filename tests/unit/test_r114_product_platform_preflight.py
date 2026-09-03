from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.fabric import FabricPlatformObservation, FabricPlatformResolutionStatus, load_platform_registry
from pd_agent.product import (
    ExecutionService,
    ExecutionServiceError,
    ProductCatalog,
    ProductFabricTaskContractError,
    ProductFabricTaskContractResolver,
    ProjectService,
)
from pd_agent.product.models import ProjectRecord, TaskRecord
from pd_agent.project import DetectedValue, ProjectInspector


FIXTURE = Path("benchmarks/projects/v0_5_fabric_base")
REQUEST = (
    "Add a craftable utility block called Server Core, register the matching "
    "block item, and add its English display-name resource and crafting recipe."
)


def _records(root: Path) -> tuple[ProjectRecord, TaskRecord]:
    project = ProjectRecord(name="fixture", workspace_ref=str(root.resolve()))
    task = TaskRecord(project_id=project.project_id, request=REQUEST)
    return project, task


def test_r114_product_preflight_resolves_current_fixture_from_profile() -> None:
    snapshot = ProjectInspector().inspect(FIXTURE.resolve())
    project, task = _records(FIXTURE)

    contract = ProductFabricTaskContractResolver().resolve(project, task, snapshot)

    assert contract.environment_constraints.minecraft_version == "1.21.11"
    assert contract.environment_constraints.loader_version == "0.19.3"
    assert contract.environment_constraints.fabric_api_version == "0.141.6+1.21.11"
    assert contract.environment_constraints.yarn_version == "1.21.11+build.6"
    assert contract.environment_constraints.java_version == "21"
    assert contract.environment_constraints.extra["loom_version"] == "1.13.3"
    assert contract.environment_constraints.extra["platform_id"] == "fabric-minecraft-1.21.11"
    assert contract.validation_requirements


def test_r114_product_preflight_reinspects_currentness() -> None:
    snapshot = ProjectInspector().inspect(FIXTURE.resolve())
    project, task = _records(FIXTURE)
    changed_versions = dict(snapshot.detected_versions)
    changed_versions["minecraft"] = DetectedValue("1.20.1", "test-mutation")

    with pytest.raises(ProductFabricTaskContractError) as raised:
        ProductFabricTaskContractResolver().resolve(project, task, replace(snapshot, detected_versions=changed_versions))

    assert raised.value.code == "UNSUPPORTED_PLATFORM"


def test_r114_target_shaped_platform_fails_closed_without_profile() -> None:
    snapshot = ProjectInspector().inspect(FIXTURE.resolve())
    project, task = _records(FIXTURE)
    changed_versions = {
        **snapshot.detected_versions,
        "minecraft": DetectedValue("26.1.2", "target-profile"),
        "loader": DetectedValue("0.20.0", "target-profile"),
        "fabric_api": DetectedValue("0.200.0+26.1.2", "target-profile"),
        "loom": DetectedValue("1.15.0", "target-profile"),
        "mappings": DetectedValue("1.26.1+build.1", "target-profile"),
    }

    with pytest.raises(ProductFabricTaskContractError) as raised:
        ProductFabricTaskContractResolver().resolve(project, task, replace(snapshot, detected_versions=changed_versions))

    assert raised.value.code == "UNSUPPORTED_PLATFORM"


def test_r114_execution_preflight_blocks_before_record_or_worker(tmp_path: Path) -> None:
    catalog = ProductCatalog(tmp_path / "product-data")
    projects = ProjectService(catalog)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = projects.register_project("Demo", workspace)
    task = projects.create_task(project.project_id, REQUEST)
    calls: list[str] = []

    class Runner:
        def preflight(self, _project, _task):  # noqa: ANN001
            calls.append("preflight")
            raise ProductFabricTaskContractError("unsupported", code="UNSUPPORTED_PLATFORM")

        def run(self, *_args):  # noqa: ANN001
            raise AssertionError("worker must not run after platform preflight failure")

    service = ExecutionService(
        catalog,
        SimpleNamespace(storage=None),
        projects,
        product_runner=Runner(),
    )
    try:
        with pytest.raises(ExecutionServiceError) as raised:
            service.start(task.task_id)
        assert getattr(raised.value, "code", None) == "UNSUPPORTED_PLATFORM"
        assert calls == ["preflight"]
        assert catalog.snapshot()["executions"] == {}
    finally:
        service.shutdown()


def test_r114_application_uses_one_registry_and_capability_authority() -> None:
    registry = load_platform_registry(Path("src/pd_agent/fabric/data/platform_profiles.json"))
    resolver = ProductFabricTaskContractResolver(platform_registry=registry)

    assert resolver.platform_registry is registry
    assert registry.resolve(FabricPlatformObservation(
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        fabric_api_version="0.141.6+1.21.11",
        loom_version="1.13.3",
        mappings_version="1.21.11+build.6",
    )).status is FabricPlatformResolutionStatus.SUPPORTED
