from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pd_agent.artifacts import ArtifactValidator
from pd_agent.context import ContextManager
from pd_agent.core import (
    AgentResponse,
    ArtifactResult,
    BuildResult,
    ExecutionLimits,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    ToolCall,
    ToolResult,
    ToolResultStatus,
)
from pd_agent.fabric import FabricNormalOrchestrator, FabricOrchestrationStatus
from pd_agent.minecraft import (
    MinecraftEvidenceKind,
    MinecraftEvidenceReference,
    MinecraftObservationStatus,
    MinecraftObservationType,
    MinecraftTestStatus,
    ObservationResult,
)
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot


class _Inspector:
    def inspect(self, root: Path) -> ProjectSnapshot:
        return ProjectSnapshot(
            project_root=root,
            status=ProjectInspectionStatus.READY,
            source_roots=(root / "src" / "main" / "java",),
            resource_roots=(root / "src" / "main" / "resources",),
            detected_versions={},
        )


class _Provider:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, _request):
        self.calls += 1
        if self.calls == 1:
            return AgentResponse(
                assistant_message="edit",
                tool_calls=(ToolCall(call_id="write-1", tool_name="write_file", arguments={
                    "path": "src/main/java/example/ServerCore.java",
                    "content": "package example; public final class ServerCore {}\n",
                }),),
            )
        return AgentResponse(assistant_message="build")


class _Build:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, _snapshot, state, _limits):
        self.calls += 1
        result = BuildResult(
            attempt=self.calls,
            command_display="fake build",
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


class _Tools:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._tools = {"write_file": SimpleNamespace(name="write_file", description="write", input_schema={})}

    def execute(self, call, _context):
        path = self.root / call.arguments["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(call.arguments["content"], encoding="utf-8")
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolResultStatus.SUCCESS,
            output={"path": call.arguments["path"]},
            metadata={"changed": True, "path": call.arguments["path"]},
        )


class _Artifact:
    def validate(self, snapshot, _build, *, run_id):
        path = snapshot.project_root / "build" / "libs" / "server-core.jar"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"current artifact")
        return ArtifactResult(path=path, size=path.stat().st_size, timestamp=datetime.now(timezone.utc), classification="VALID")


class _Minecraft:
    def __init__(self, status: MinecraftObservationStatus) -> None:
        self.status = status
        self.calls = 0

    def run(self, _spec, **_kwargs):
        self.calls += 1
        return SimpleNamespace(
            status=MinecraftTestStatus.PASS,
            observations=(ObservationResult(
                observation_id="server-core",
                observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
                status=self.status,
                expected={"present": True},
                actual={"present": self.status is MinecraftObservationStatus.PASS},
                evidence_refs=(MinecraftEvidenceReference(kind=MinecraftEvidenceKind.OBSERVATION, ref="runtime/server-core.json"),),
            ),),
        )


def _contract() -> FabricTaskContract:
    return FabricTaskContract(
        task_id="server-core",
        revision="product-1",
        goal="add Server Core",
        requirements=(
            FabricRequirement(requirement_id="source-change", description="a source change is required"),
            FabricRequirement(requirement_id="validation-build", description="the project builds"),
            FabricRequirement(requirement_id="validation-artifact", description="the artifact is valid"),
            FabricRequirement(requirement_id="validation-minecraft", description="Minecraft runtime passes"),
        ),
        completion_criteria=("source change", "build", "artifact", "minecraft"),
        validation_requirements=(
            FabricValidationRequirement(validation_requirement_id="validate-build", requirement_ids=("validation-build",), kind="build"),
            FabricValidationRequirement(validation_requirement_id="validate-artifact", requirement_ids=("validation-artifact",), kind="artifact"),
            FabricValidationRequirement(
                validation_requirement_id="validate-minecraft",
                requirement_ids=("validation-minecraft",),
                kind="minecraft",
                spec={"target_mod_id": "examplemod", "observations": [{
                    "observation_id": "server-core",
                    "observation_type": "REGISTRY_ENTRY_PRESENT",
                    "profile": "registry_entry",
                    "selector": {"kind": "registry", "id": "examplemod:server_core"},
                    "expected": {"present": True},
                    "requirement_ids": ["validation-minecraft"],
                }]},
            ),
        ),
    )


def _run(tmp_path: Path, minecraft_runner=None, artifact_validator=None):
    root = tmp_path / "workspace"
    (root / "src" / "main" / "resources").mkdir(parents=True)
    (root / "src" / "main" / "resources" / "fabric.mod.json").write_text("{}", encoding="utf-8")
    return FabricNormalOrchestrator(
        provider=_Provider(),
        build_runner=_Build(),
        artifact_validator=artifact_validator or _Artifact(),
        context_manager=ContextManager(),
        project_inspector=_Inspector(),
        tool_executor=_Tools(root),
        limits=ExecutionLimits(max_agent_steps=5, max_tool_calls=5, max_build_attempts=2),
        minecraft_runner=minecraft_runner,
    ).run(_contract(), root, brain_enabled=False)


def test_productive_fabric_pipeline_reaches_completion_gate(tmp_path: Path) -> None:
    minecraft = _Minecraft(MinecraftObservationStatus.PASS)
    result = _run(tmp_path, minecraft_runner=minecraft)

    assert result.status is FabricOrchestrationStatus.COMPLETE
    assert result.completion.complete is True
    assert minecraft.calls == 1


def test_missing_minecraft_is_incomplete_without_delivery(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.status is FabricOrchestrationStatus.INCOMPLETE
    assert "validate-minecraft" in result.completion.missing_validation_requirement_ids


def test_minecraft_observation_failure_is_not_complete(tmp_path: Path) -> None:
    result = _run(tmp_path, minecraft_runner=_Minecraft(MinecraftObservationStatus.FAIL))

    assert result.status is FabricOrchestrationStatus.INCOMPLETE
    assert result.completion.active_failure_ids


def test_invalid_artifact_is_rejected_before_minecraft(tmp_path: Path) -> None:
    class InvalidArtifact:
        def validate(self, snapshot, _build, *, run_id):
            return ArtifactResult(path=None, size=0, timestamp=datetime.now(timezone.utc), classification="INVALID")

    minecraft = _Minecraft(MinecraftObservationStatus.PASS)
    result = _run(tmp_path, minecraft_runner=minecraft, artifact_validator=InvalidArtifact())

    assert result.status is FabricOrchestrationStatus.INCOMPLETE
    assert minecraft.calls == 0
    assert "validate-artifact" in result.completion.missing_validation_requirement_ids or result.completion.invalid_blocking_validation_refs
