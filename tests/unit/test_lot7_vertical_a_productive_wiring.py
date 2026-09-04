from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from pd_agent.minecraft import MinecraftObservationType, runtime_spec_from_requirement
from pd_agent.product.fabric import ProductFabricTaskContractResolver
from pd_agent.product.models import ProjectRecord, TaskRecord
from pd_agent.project import DetectedValue, FabricManifest, ProjectInspectionStatus, ProjectSnapshot


REQUEST = (
    "Add a craftable utility block named Copper Beacon, including its block item, "
    "assets and crafting recipe, while preserving the existing mod and entrypoints."
)


def _snapshot(root: Path, *, platform: str = "fabric-minecraft-1.21.11") -> ProjectSnapshot:
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
            "platform_id": DetectedValue(platform, "test"),
        },
    )


def test_lot7_product_request_composes_parameterized_vertical_a() -> None:
    root = Path(".tmp") / "lot7-product-workspace"
    project = ProjectRecord(project_id=str(uuid4()), name="demo", workspace_ref=str(root))
    task = TaskRecord(task_id=str(uuid4()), project_id=project.project_id, request=REQUEST)

    contract = ProductFabricTaskContractResolver().resolve(project, task, _snapshot(root))

    assert contract.required_capabilities == ("Fabric project", "craftable utility block")
    resource_paths = {item.path for item in contract.mutation_expectations if item.role == "resource"}
    assert resource_paths
    assert any(path and path.endswith("CopperBeaconBlock.java") for path in (item.path for item in contract.mutation_expectations if item.role == "source"))
    assert any(path and path.endswith("CopperBeaconBlockItem.java") for path in (item.path for item in contract.mutation_expectations if item.role == "source"))
    assert all("copper_beacon" in path for path in resource_paths if "/lang/" not in path)
    assert all("server_core" not in (item.path or "") for item in contract.mutation_expectations)
    assert all("examplemod" in path for path in resource_paths)

    runtime = [item for item in contract.validation_requirements if item.kind == "minecraft"]
    assert len(runtime) == 1
    spec = runtime_spec_from_requirement(runtime[0])
    assert spec.observations[0].selector["identifier"].startswith("examplemod:")
    assert contract.environment_constraints.extra["platform_id"] == "fabric-minecraft-1.21.11"
    assert [item.observation_type for item in spec.observations] == [
        MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        MinecraftObservationType.BLOCK_ITEM_ASSOCIATION,
    ]
    assert spec.observations[0].selector["identifier"] == "examplemod:copper_beacon"
    assert spec.observations[1].selector["identifier"] == "examplemod:copper_beacon"
    assert spec.observations[2].selector["block_id"] == "examplemod:copper_beacon"


def test_lot7_contract_keeps_platform_identity_for_262_without_yarn() -> None:
    root = Path(".tmp") / "lot7-262-workspace"
    project = ProjectRecord(project_id=str(uuid4()), name="demo", workspace_ref=str(root))
    task = TaskRecord(task_id=str(uuid4()), project_id=project.project_id, request=REQUEST)
    snapshot = _snapshot(root, platform="fabric-minecraft-26.2")
    detected_versions = {
        key: value for key, value in snapshot.detected_versions.items()
        if key not in {"yarn", "yarn_version"}
    }
    snapshot = replace(snapshot, detected_versions={
        **detected_versions,
        "minecraft_version": DetectedValue("26.2", "test"),
        "fabric_api_version": DetectedValue("0.158.0+26.2", "test"),
        "java_version": DetectedValue("25", "test"),
        "loom": DetectedValue("1.17-SNAPSHOT", "test"),
        "mapping_family": DetectedValue("UNOBFUSCATED", "test"),
    })

    contract = ProductFabricTaskContractResolver().resolve(project, task, snapshot)

    assert contract.environment_constraints.extra["platform_id"] == "fabric-minecraft-26.2"
    assert contract.environment_constraints.yarn_version is None
