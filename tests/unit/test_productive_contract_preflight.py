from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pd_agent.config import load_config
from pd_agent.minecraft import runtime_spec_from_requirement
from pd_agent.minecraft import MinecraftTestRunner, MinecraftTestSpec, UnsupportedMinecraftEnvironmentError
from pd_agent.project import DetectedValue
from pd_agent.product.application import build_product_application
from pd_agent.product.models import ProjectRecord, TaskRecord
from pd_agent.project import ProjectInspector


FIXTURE = Path("tests/fixtures/l11_fabric_fixture")
REQUEST_EN = (
    "Add a craftable utility block called Server Core to Example Mod, register "
    "the matching block item, and add its English display-name resource and "
    "crafting recipe while preserving the existing mod id and entrypoints."
)
REQUEST_ES = (
    "Añade un bloque utilitario craftable llamado Server Core, incluyendo su "
    "block item, recursos en_us y receta, preservando el mod y los entrypoints existentes."
)


def _application(tmp_path: Path):
    config = replace(
        load_config(),
        provider="openai",
        model="gpt-5.6-luna",
        runs_dir=tmp_path / "runs",
    )
    return build_product_application(
        config,
        economic_budget_usd="0.50",
        product_data_root=tmp_path / "product-data",
    )


@pytest.mark.parametrize("task_request", [REQUEST_EN, REQUEST_ES])
def test_product_server_core_resolves_structured_runtime_requirement(tmp_path: Path, task_request: str) -> None:
    application = _application(tmp_path)
    try:
        snapshot = ProjectInspector().inspect(FIXTURE.resolve())
        project = ProjectRecord(name="fixture", workspace_ref=str(FIXTURE.resolve()))
        task = TaskRecord(project_id=project.project_id, request=task_request)
        contract = application.fabric_resolver.resolve(project, task, snapshot)
        requirement = next(item for item in contract.validation_requirements if item.kind == "minecraft")

        runtime_spec = runtime_spec_from_requirement(requirement)

        assert requirement.spec["target_mod_id"] == "pdagentl11"
        assert runtime_spec.observations[0].selector["identifier"] == "pdagentl11:server_core"
        assert runtime_spec.observations[0].observation_type.value == "REGISTRY_ENTRY_PRESENT"
        assert runtime_spec.observation_requirements["server-core-registry"] == ("validation-minecraft",)
    finally:
        application.shutdown()


def test_product_server_core_rejects_missing_mod_identity(tmp_path: Path) -> None:
    application = _application(tmp_path)
    try:
        snapshot = ProjectInspector().inspect(FIXTURE.resolve())
        broken = replace(snapshot, fabric_manifests=tuple(
            replace(manifest, mod_id=None) for manifest in snapshot.fabric_manifests
        ))
        project = ProjectRecord(name="fixture", workspace_ref=str(FIXTURE.resolve()))
        task = TaskRecord(project_id=project.project_id, request=REQUEST_EN)

        with pytest.raises(ValueError, match="exactly one Fabric mod id"):
            application.fabric_resolver.resolve(project, task, broken)
    finally:
        application.shutdown()


def test_productive_composition_fixes_output_budget_and_preview(tmp_path: Path) -> None:
    application = _application(tmp_path)
    try:
        provider = application.runtime.provider
        assert provider.model == "gpt-5.6-luna"
        assert application.runtime.controller.model_config["max_output_tokens"] == 16_384
        preview = provider.budget_guard.preview_budget(input_tokens=70_000, output_limit=16_384)
        assert preview["decision"] == "ALLOW"
        assert preview["output_tokens_limit"] == 16_384
        assert preview["reservation_usd"] == "0.03716080"
    finally:
        application.shutdown()


def test_project_inspector_versions_map_to_productive_contract(tmp_path: Path) -> None:
    application = _application(tmp_path)
    try:
        snapshot = ProjectInspector().inspect(FIXTURE.resolve())
        snapshot = replace(
            snapshot,
            detected_versions={
                **snapshot.detected_versions,
                "fabric_api": DetectedValue("0.141.6+1.21.11", "test-fabric-api"),
            },
        )
        project = ProjectRecord(name="fixture", workspace_ref=str(FIXTURE.resolve()))
        task = TaskRecord(project_id=project.project_id, request=REQUEST_EN)

        contract = application.fabric_resolver.resolve(project, task, snapshot)
        environment = contract.environment_constraints

        assert environment.minecraft_version == "1.21.11"
        assert environment.loader_version == "0.19.3"
        assert environment.fabric_api_version == "0.141.6+1.21.11"
        assert environment.yarn_version == "1.21.11+build.6"
        assert environment.java_version == "21"
        runtime_spec = runtime_spec_from_requirement(
            next(item for item in contract.validation_requirements if item.kind == "minecraft")
        )
        assert runtime_spec.observations[0].phase == "RUNTIME"
    finally:
        application.shutdown()


@pytest.mark.parametrize("missing_key", ["minecraft", "loader"])
def test_project_inspector_missing_required_version_fails_closed(tmp_path: Path, missing_key: str) -> None:
    application = _application(tmp_path)
    try:
        snapshot = ProjectInspector().inspect(FIXTURE.resolve())
        broken = replace(
            snapshot,
            detected_versions={key: value for key, value in snapshot.detected_versions.items() if key != missing_key},
        )
        project = ProjectRecord(name="fixture", workspace_ref=str(FIXTURE.resolve()))
        task = TaskRecord(project_id=project.project_id, request=REQUEST_EN)

        with pytest.raises(ValueError, match="missing required Fabric versions"):
            application.fabric_resolver.resolve(project, task, broken)
    finally:
        application.shutdown()


def test_unsupported_minecraft_version_remains_fail_closed(tmp_path: Path) -> None:
    application = _application(tmp_path)
    try:
        snapshot = ProjectInspector().inspect(FIXTURE.resolve())
        project = ProjectRecord(name="fixture", workspace_ref=str(FIXTURE.resolve()))
        task = TaskRecord(project_id=project.project_id, request=REQUEST_EN)
        contract = application.fabric_resolver.resolve(project, task, snapshot)
        requirement = next(item for item in contract.validation_requirements if item.kind == "minecraft")
        runtime_spec = runtime_spec_from_requirement(requirement)
        unsupported = MinecraftTestSpec(
            target_jar=FIXTURE / "build" / "libs" / "fixture.jar",
            target_mod_id=runtime_spec.observations[0].selector["identifier"].split(":", 1)[0],
            minecraft_version="0.0.0",
            loader_version="0.19.3",
            test_id="unsupported",
            timeout_seconds=30,
            observation_type="REGISTRY_ENTRY_PRESENT",
            observation_params={"registry_kind": "block", "identifier": "pdagentl11:server_core"},
        )

        with pytest.raises(UnsupportedMinecraftEnvironmentError, match="unsupported minecraft_version"):
            MinecraftTestRunner(FIXTURE.resolve()).validate_spec(unsupported, java_version="21")
    finally:
        application.shutdown()
