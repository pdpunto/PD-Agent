from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import shutil
import zipfile

import pytest

from pd_agent.config import load_config
from pd_agent.artifacts import ArtifactClassification
from pd_agent.benchmark.dependencies import resolve_runtime_mod_dependencies
from pd_agent.core import ArtifactResult
from pd_agent.core import (
    AgentResponse,
    BuildResult,
    FabricRequirement,
    FabricTaskContract,
    TaskProgressLedger,
    ToolCall,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    ValidationViolation,
)
from pd_agent.minecraft import runtime_spec_from_requirement
from pd_agent.minecraft import MinecraftTestRunner, MinecraftTestSpec, UnsupportedMinecraftEnvironmentError
from pd_agent.project import DetectedValue
from pd_agent.product.application import build_product_application
from pd_agent.product.fabric import ProductFabricTaskContractResolver
from pd_agent.product.models import ProjectRecord, TaskRecord
from pd_agent.project import ProjectInspector
from pd_agent.validation import PreBuildWorkspaceValidator
from pd_agent.brain import KnowledgeService
from pd_agent.brain import BrainTrigger, FabricBrainOrchestrator


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
        assert runtime_spec.observation_requirements["vertical-a-block-registry"] == (requirement.validation_requirement_id,)
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


def test_productive_composition_wires_prebuild_validation_to_runtime_boundary(tmp_path: Path) -> None:
    application = _application(tmp_path)
    try:
        validator = application.runtime.controller.pre_build_validator

        assert isinstance(validator, PreBuildWorkspaceValidator)
        assert application.fabric_orchestrator.pre_build_validator is validator
    finally:
        application.shutdown()


def _prebuild_boundary_contract() -> FabricTaskContract:
    return FabricTaskContract(
        task_id="offline-boundary",
        revision="1",
        goal="make a source mutation",
        requirements=(FabricRequirement(requirement_id="source", description="source mutation"),),
    )


class _BoundaryProvider:
    def __init__(self, contents: tuple[str, ...]) -> None:
        self.contents = iter(contents)
        self.mutation_count = 0

    def execute(self, _request):
        try:
            content = next(self.contents)
        except StopIteration:
            return AgentResponse(assistant_message="continue")
        tool_name = "create_file" if self.mutation_count == 0 else "write_file"
        self.mutation_count += 1
        return AgentResponse(
            assistant_message="edit",
            tool_calls=(ToolCall(
                call_id=f"edit-{hash(content)}",
                tool_name=tool_name,
                arguments={
                    "path": "src/main/java/generated/Boundary.java",
                    "content": content,
                },
            ),),
        )


class _BoundaryBuildRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, _snapshot, state, _limits):
        self.calls += 1
        result = BuildResult(
            attempt=self.calls,
            command_display="offline fake build",
            cwd=state.project_root,
            started_at=datetime.now(timezone.utc),
            duration_seconds=0.01,
            exit_code=0,
            stdout_log="BUILD SUCCESSFUL",
            stderr_log="",
        )
        state.record_build_attempt()
        state.record_build_result(result)
        return result


class _BoundaryArtifactValidator:
    def validate(self, snapshot, _build, *, run_id):
        path = snapshot.project_root / "build" / "libs" / "offline.jar"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"offline artifact")
        return ArtifactResult(
            path=path,
            size=path.stat().st_size,
            timestamp=datetime.now(timezone.utc),
            classification="VALID",
        )


def _boundary_application(tmp_path: Path, contents: tuple[str, ...], *, functional_validator=None):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE, workspace)
    build_runner = _BoundaryBuildRunner()
    provider = _BoundaryProvider(contents)
    application = build_product_application(
        replace(load_config(), provider="openai", model="offline-test", runs_dir=tmp_path / "runs"),
        provider_factory=lambda _config: provider,
        build_runner=build_runner,
        artifact_validator=_BoundaryArtifactValidator(),
        product_data_root=tmp_path / "product-data",
        minecraft_runner_factory=lambda _root: None,
    )
    if functional_validator is not None:
        application.fabric_orchestrator.functional_validator = functional_validator
    return application, workspace, build_runner


def _invalid_block_source() -> str:
    return "new Block(AbstractBlock.Settings.create().strength(1.0f));\n"


def _valid_block_source() -> str:
    return "new Block(AbstractBlock.Settings.create().registryKey(key).strength(1.0f));\n"


def test_productive_boundary_blocks_invalid_source_before_build(tmp_path: Path) -> None:
    application, workspace, build_runner = _boundary_application(tmp_path, (_invalid_block_source(),))
    try:
        result = application.fabric_orchestrator.run(_prebuild_boundary_contract(), workspace, brain_enabled=False)
        assert build_runner.calls == 0, result.to_dict()
        assert any(
            violation.code == "FABRIC_BLOCK_IDENTITY_MISSING"
            for validation in result.report.validation_results
            for violation in validation.violations
        ), result.to_dict()
    finally:
        application.shutdown()


def test_productive_boundary_allows_valid_source_after_prebuild(tmp_path: Path) -> None:
    application, workspace, build_runner = _boundary_application(tmp_path, (_valid_block_source(),))
    try:
        result = application.fabric_orchestrator.run(_prebuild_boundary_contract(), workspace, brain_enabled=False)
        assert build_runner.calls == 1, result.report.to_dict() if result.report else result.to_dict()
    finally:
        application.shutdown()


class _OneRepairValidator:
    def __init__(self) -> None:
        self.calls = 0

    def validate(self, *_args):
        self.calls += 1
        if self.calls == 1:
            return ValidationResult(
                stage=ValidationStage.RUNTIME,
                status=ValidationStatus.REPAIRABLE_FAIL,
                summary="offline repair required",
                violations=(ValidationViolation(
                    code="OFFLINE_REPAIR_REQUIRED",
                    requirement="source",
                    observed={"category": "mismatch"},
                    message="offline repair required",
                ),),
            )
        return ValidationResult(
            stage=ValidationStage.RUNTIME,
            status=ValidationStatus.PASS,
            summary="offline runtime pass",
        )


def test_productive_boundary_rechecks_prebuild_after_invalid_then_valid_repair(tmp_path: Path) -> None:
    repair_validator = _OneRepairValidator()
    application, workspace, build_runner = _boundary_application(
        tmp_path,
        (_valid_block_source(), _invalid_block_source(), _valid_block_source()),
        functional_validator=repair_validator,
    )
    try:
        result = application.fabric_orchestrator.run(_prebuild_boundary_contract(), workspace, brain_enabled=False)
        assert result.report is not None, result.to_dict()
        assert any(
            violation.code == "FABRIC_BLOCK_IDENTITY_MISSING"
            for validation in result.report.validation_results
            for violation in validation.violations
        )
        assert build_runner.calls == 2
        assert repair_validator.calls == 2
    finally:
        application.shutdown()


def test_productive_composition_accepts_one_explicit_knowledge_service(tmp_path: Path) -> None:
    class Source:
        source_id = "r8-test-source"
        source_kind = "fixture"
        artifact_version = "r8"

        def supports(self, _need):
            return True

        def compatibility(self, _environment):
            from pd_agent.brain import CompatibilityStatus
            return CompatibilityStatus.COMPATIBLE

        def resolve(self, need, offline=False):
            from pd_agent.brain import KnowledgeItem, KnowledgeProvenance, KnowledgeRetrievalStatus, KnowledgeSourceResult, SourceAuthority
            item = KnowledgeItem(
                "r8-item", {"guidance": "runtime diagnostic"}, need.environment,
                SourceAuthority.AUTHORITATIVE_SOURCE,
                KnowledgeProvenance("r8-test-source", "fixture", "fixture://r8"),
            )
            return KnowledgeSourceResult(
                KnowledgeRetrievalStatus.SUCCESS, self.source_id, self.source_kind, need,
                items=(item,),
            )

    service = KnowledgeService((Source(),))
    application = build_product_application(
        replace(load_config(), provider="openai", model="gpt-5.6-luna", runs_dir=tmp_path / "runs"),
        economic_budget_usd="0.50",
        product_data_root=tmp_path / "product-data",
        knowledge_service=service,
    )
    try:
        assert application.fabric_orchestrator.knowledge_service is service
        assert application.fabric_orchestrator.repair_knowledge_source is service.sources[0]
        project = ProjectRecord(name="fixture", workspace_ref=str(FIXTURE.resolve()))
        assert application.fabric_orchestrator._knowledge_environment(  # noqa: SLF001
            application.fabric_resolver.resolve(
                project,
                TaskRecord(project_id=project.project_id, request=REQUEST_EN),
                ProjectInspector().inspect(FIXTURE.resolve()),
            )
        ).minecraft_version == "1.21.11"
    finally:
        application.shutdown()


def test_productive_brain_context_is_injected_and_brain_off_is_isolated(tmp_path: Path) -> None:
    class Source:
        source_id = "r8-context-source"
        source_kind = "fixture"
        artifact_version = "r8"

        def supports(self, _need):
            return True

        def compatibility(self, _environment):
            from pd_agent.brain import CompatibilityStatus
            return CompatibilityStatus.COMPATIBLE

        def resolve(self, need, offline=False):
            from pd_agent.brain import KnowledgeItem, KnowledgeProvenance, KnowledgeRetrievalStatus, KnowledgeSourceResult, SourceAuthority
            item = KnowledgeItem(
                "r8-context-item", {"guidance": "Fabric registry guidance"}, need.environment,
                SourceAuthority.AUTHORITATIVE_SOURCE,
                KnowledgeProvenance("r8-context-source", "fixture", "fixture://r8-context"),
            )
            return KnowledgeSourceResult(
                KnowledgeRetrievalStatus.SUCCESS, self.source_id, self.source_kind, need,
                items=(item,),
            )

    service = KnowledgeService((Source(),))
    application = build_product_application(
        replace(load_config(), provider="openai", model="gpt-5.6-luna", runs_dir=tmp_path / "runs"),
        economic_budget_usd="0.50",
        product_data_root=tmp_path / "product-data",
        knowledge_service=service,
    )
    try:
        project = ProjectRecord(name="fixture", workspace_ref=str(FIXTURE.resolve()))
        task = TaskRecord(project_id=project.project_id, request=REQUEST_EN)
        contract = application.fabric_resolver.resolve(project, task, ProjectInspector().inspect(FIXTURE.resolve()))
        environment = application.fabric_orchestrator._knowledge_environment(contract)  # noqa: SLF001
        assert environment.loom_version == "1.13.3"
        assert environment.mappings_namespace == "yarn"
        brain = FabricBrainOrchestrator(
            knowledge_service=application.fabric_orchestrator.knowledge_service,
            context_manager=application.runtime.controller.context_manager,
        )
        ledger = TaskProgressLedger(contract_identity=contract.identity())
        on = brain.prepare(
            contract=contract,
            environment=environment,
            ledger=ledger,
            trigger=BrainTrigger.PRE_CODE,
            brain_enabled=True,
        )
        assert on.retrieved_count > 0
        assert on.selected_count > 0
        assert on.injected_context_item_ids
        assert set(on.injected_context_item_ids) == {"r8-context-item"}
        assert any("r8-context-item" in message.content for message in on.provider_messages)
        assert on.ledger is not None
        assert on.ledger.knowledge_correlation

        off = brain.prepare(contract=contract, environment=environment, trigger=BrainTrigger.PRE_CODE, brain_enabled=False)
        assert off.retrieved_count == 0
        assert off.selected_count == 0
        assert off.injected_context_item_ids == ()
        assert off.provider_messages == ()
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
        assert environment.extra["loom_version"] == "1.13.3"
        assert environment.extra["mappings_namespace"] == "yarn"
        runtime_spec = runtime_spec_from_requirement(
            next(item for item in contract.validation_requirements if item.kind == "minecraft")
        )
        assert runtime_spec.observations[0].phase == "RUNTIME"
    finally:
        application.shutdown()


def test_harness_datapack_metadata_declares_current_format_bounds() -> None:
    harness_build = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "l11_minecraft_harness" / "build.gradle.kts"
    content = harness_build.read_text(encoding="utf-8")
    assert '\\"pack_format\\":94' in content
    assert '\\"min_format\\":94' in content
    assert '\\"max_format\\":94' in content


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


def test_r5_productive_resources_compose_offline(tmp_path: Path) -> None:
    project_root = Path("benchmarks/projects/v0_5_fabric_base").resolve()
    gradle_home = tmp_path / "gradle-home"
    dependency_dir = (
        gradle_home / "caches" / "modules-2" / "files-2.1"
        / "net.fabricmc.fabric-api" / "fabric-api" / "0.141.6+1.21.11" / "test-hash"
    )
    dependency_dir.mkdir(parents=True)
    dependency_path = dependency_dir / "fabric-api-0.141.6+1.21.11.jar"
    with zipfile.ZipFile(dependency_path, "w") as archive:
        archive.writestr("fabric.mod.json", '{"id":"fabric-api","version":"test"}')

    snapshot = ProjectInspector().inspect(project_root)
    dependencies = resolve_runtime_mod_dependencies(
        project_root,
        gradle_user_home=gradle_home,
        project_snapshot=snapshot,
    )
    assert len(dependencies) == 1
    assert dependencies[0].path == dependency_path.resolve()
    assert dependencies[0].coordinate == "net.fabricmc.fabric-api:fabric-api:0.141.6+1.21.11"

    project = ProjectRecord(name="fixture", workspace_ref=str(project_root))
    task = TaskRecord(project_id=project.project_id, request=REQUEST_EN)
    contract = ProductFabricTaskContractResolver().resolve(project, task, snapshot)
    requirement = next(item for item in contract.validation_requirements if item.kind == "minecraft")
    artifact_path = next(project_root.glob("build/loom-cache/**/*.jar"))
    artifact = ArtifactResult(
        path=artifact_path,
        size=artifact_path.stat().st_size,
        timestamp=datetime.now(timezone.utc),
        classification=ArtifactClassification.VALID.value,
    )
    from pd_agent.validation.runtime import _minecraft_spec

    spec = _minecraft_spec(
        project_root,
        contract,
        requirement,
        artifact,
        runtime_mod_jars=tuple(item.path for item in dependencies),
    )
    assert spec.target_jar == artifact_path.relative_to(project_root)
    assert spec.runtime_mod_jars == (dependency_path.resolve(),)
    assert spec.target_mod_id == "examplemod"
    assert spec.observation_requests[0].selector["identifier"] == "examplemod:server_core"


def test_r5_product_application_exposes_canonical_harness(tmp_path: Path) -> None:
    application = _application(tmp_path)
    try:
        runner = application.fabric_orchestrator.minecraft_runner_factory(FIXTURE.resolve())
        assert runner.harness_root == (Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "l11_minecraft_harness").resolve()
        assert runner.harness_root.exists()
    finally:
        application.shutdown()


def test_r6_product_application_passes_gradle_home_as_a_path(tmp_path: Path) -> None:
    application = _application(tmp_path)
    try:
        assert application.fabric_orchestrator.gradle_user_home == (Path.home() / ".gradle")
        assert isinstance(application.fabric_orchestrator.gradle_user_home, Path)
    finally:
        application.shutdown()
