from __future__ import annotations

from dataclasses import replace
from threading import Event
import json
from pathlib import Path
import shutil

from pd_agent.build import GradleBuildRunner
from pd_agent.config import load_config
from pd_agent.core import (
    AgentResponse,
    RuntimeAttemptIdentity,
    ToolCall,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    compute_source_revision,
    validation_contract_revision,
)
from pd_agent.fabric.planning import CapabilityPlanner
import pd_agent.fabric.orchestration as fabric_orchestration
from pd_agent.product import ProductExecutionStatus, build_product_application
from pd_agent.project import ProjectInspector


REQUEST = (
    "Add a craftable utility block called Server Core with a matching block item, "
    "en_us resources and recipe while preserving the existing mod and entrypoints."
)
FIXTURE = Path("tests/fixtures/l11_fabric_fixture")


class _DeterministicProvider:
    def __init__(self, java_source: str) -> None:
        self.java_source = java_source
        self.calls = 0

    def execute(self, _request):  # noqa: ANN001
        self.calls += 1
        if self.calls > 1:
            return AgentResponse(assistant_message="finished")
        return AgentResponse(
            assistant_message="apply the Server Core source and resources",
            tool_calls=(
                ToolCall(
                    call_id="edit-java",
                    tool_name="write_file",
                    arguments={
                        "path": "src/main/java/dev/pdpunto/l11/ExampleMod.java",
                        "content": self.java_source,
                    },
                ),
                ToolCall(
                    call_id="create-lang",
                    tool_name="create_file",
                    arguments={
                        "path": "src/main/resources/assets/pdagentl11/lang/en_us.json",
                        "content": json.dumps({"block.pdagentl11.server_core": "Server Core"}),
                    },
                ),
                ToolCall(
                    call_id="create-recipe",
                    tool_name="create_file",
                    arguments={
                        "path": "src/main/resources/data/pdagentl11/recipe/server_core.json",
                        "content": json.dumps({
                            "type": "minecraft:crafting_shaped",
                            "pattern": ["III", "ICI", "III"],
                            "key": {
                                "I": {"item": "minecraft:iron_ingot"},
                                "C": {"item": "minecraft:crafting_table"},
                            },
                            "result": {"id": "pdagentl11:server_core", "count": 1},
                        }),
                    },
                ),
            ),
        )


class _OfflineFunctionalValidator:
    def bind_run_state(self, run_state) -> None:  # noqa: ANN001
        self.run_state = run_state

    def validate(self, _project_root, artifact, contract, run_id):  # noqa: ANN001
        requirement = next(item for item in contract.validation_requirements if item.kind == "minecraft")
        source = compute_source_revision(self.run_state.project_root).revision
        self.run_state.runtime_identities = (*self.run_state.runtime_identities, RuntimeAttemptIdentity(
            runtime_attempt_id=run_id,
            artifact_identity=self.run_state.artifact_identity.artifact_identity,
            validation_revision=validation_contract_revision(requirement),
            requirement_ids=requirement.requirement_ids,
            result_refs=("offline/runtime/server-core",),
            status="PASS",
        ))
        self.run_state.source_revision = replace(self.run_state.source_revision, revision=source)
        return ValidationResult(stage=ValidationStage.RUNTIME, status=ValidationStatus.PASS, summary="offline functional boundary passed")


def test_m1_representative_block_item_recipe_product_flow(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    planned = []
    original_plan = CapabilityPlanner.plan

    def capture_plan(planner, candidates):  # noqa: ANN001
        result = original_plan(planner, candidates)
        if result.success:
            planned.append(result)
        return result

    monkeypatch.setattr(CapabilityPlanner, "plan", capture_plan)
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE, workspace, ignore=shutil.ignore_patterns("bin", "build", ".gradle"))
    provider = _DeterministicProvider(
        """package dev.pdpunto.l11;

import net.fabricmc.api.ModInitializer;
import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.registry.RegistryKey;
import net.minecraft.registry.RegistryKeys;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.Identifier;
import net.minecraft.util.math.BlockPos;

public final class ExampleMod implements ModInitializer {
    public static final String MOD_ID = "pdagentl11";
    public static final Block SERVER_CORE = new Block(AbstractBlock.Settings.create()
        .registryKey(RegistryKey.of(RegistryKeys.BLOCK, Identifier.of(MOD_ID, "server_core"))));
    private static final BlockState PROBE_STATE = Blocks.DIAMOND_BLOCK.getDefaultState();

    @Override
    public void onInitialize() {}

    public static boolean applyProbeState(ServerWorld world, BlockPos pos) {
        return world.setBlockState(pos, PROBE_STATE, Block.NOTIFY_ALL);
    }

    public static BlockState expectedProbeState() { return PROBE_STATE; }
}
"""
    )
    config = replace(load_config(), provider="openai", model="offline-test", runs_dir=tmp_path / "runs")
    application = build_product_application(
        config,
        provider_factory=lambda _config: provider,
        build_runner=GradleBuildRunner(
            environment_overrides={
                "GRADLE_USER_HOME": str(Path.home() / ".gradle"),
                "GRADLE_OPTS": "-Dorg.gradle.offline=true",
            }
        ),
        product_data_root=tmp_path / "product-data",
        minecraft_runner_factory=lambda _root: object(),
    )
    offline_validator = _OfflineFunctionalValidator()
    monkeypatch.setattr(
        fabric_orchestration,
        "ProductiveMinecraftFunctionalValidator",
        lambda **_kwargs: offline_validator,
    )
    application.fabric_orchestrator.functional_validator = None
    try:
        project = application.project_service.register_project("M1 representative", workspace)
        task = application.project_service.create_task(project.project_id, REQUEST)
        started = application.execution_service.start(task.task_id)
        for _ in range(600):
            if application.execution_service.get(started.execution_id).terminal:
                break
            Event().wait(0.1)
        result = application.execution_service.get(started.execution_id)

        assert result.status is ProductExecutionStatus.SUCCEEDED
        assert result.execution_id == result.run_id
        assert provider.calls == 1
        persisted = application.runtime.storage.read_run_state(result.run_id)
        contract = persisted.task_contract
        assert contract is not None
        assert len(contract.requirements) == 6
        assert {item.kind for item in contract.validation_requirements} == {"build", "artifact", "minecraft"}
        assert planned
        plan = planned[-1]
        assert tuple(item.definition_id for item in plan.instances) == (
            "fabric.block",
            "fabric.block_item",
            "fabric.recipe",
        )
        assert len(plan.dependency_edges) == 2
        assert persisted.build_results[-1].success
        assert persisted.artifact_result is not None
        assert persisted.artifact_result.classification == "VALID"
        assert persisted.progress_ledger is not None
        assert not persisted.progress_ledger.pending_requirement_ids(
            tuple(item.requirement_id for item in contract.requirements)
        )
        assert application.runtime.storage.read_final_report(result.run_id).completion_status == "COMPLETE"
        assert ProjectInspector().inspect(workspace).status.value == "READY"
    finally:
        application.shutdown()
