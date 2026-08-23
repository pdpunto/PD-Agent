from __future__ import annotations

import zipfile
from pathlib import Path

from pd_agent.core import AgentResponse, ToolCall, ValidationResult, ValidationStage, ValidationStatus, ValidationViolation
from pd_agent.minecraft import MinecraftEvidencePaths, MinecraftTargetMetadata, MinecraftTestResult, MinecraftTestSpec, MinecraftTestStatus
from pd_agent.benchmark.functional import BenchmarkFunctionalValidator
from pd_agent.validation import PreBuildWorkspaceValidator
from tests.unit.test_l9_runtime import ScriptedProvider, _controller, _runtime_project


class ScriptedFunctionalValidator:
    def __init__(self) -> None:
        self.calls = 0
        self.last_results: tuple[ValidationResult, ...] = ()

    def validate(self, project_root, artifact, contract, run_id):  # noqa: ANN001
        del project_root, artifact, contract, run_id
        self.calls += 1
        post = ValidationResult(stage=ValidationStage.POST_ARTIFACT, status=ValidationStatus.PASS, summary="artifact ok")
        if self.calls == 1:
            runtime = ValidationResult(
                stage=ValidationStage.RUNTIME,
                status=ValidationStatus.REPAIRABLE_FAIL,
                summary="runtime failed",
                violations=(ValidationViolation(
                    code="REGISTRY_ENTRY_PRESENT",
                    requirement="item registry entry examplemod:signal_charm",
                    observed={"category": "missing"},
                    message="required item registry entry was not observed",
                ),),
            )
        else:
            runtime = ValidationResult(stage=ValidationStage.RUNTIME, status=ValidationStatus.PASS, summary="runtime ok")
        self.last_results = (post, runtime)
        return runtime


def _minecraft_result(status: MinecraftTestStatus, reason: str = "ok") -> MinecraftTestResult:
    spec = MinecraftTestSpec(
        target_jar=Path("target.jar"),
        target_mod_id="examplemod",
        minecraft_version="1.20.1",
        loader_version="0.15.11",
        test_id="functional",
        timeout_seconds=30,
        observation_type="REGISTRY_ENTRY_PRESENT",
        observation_params={"registry_kind": "item", "identifier": "examplemod:signal_charm"},
    )
    target = MinecraftTargetMetadata(
        path=Path("target.jar"),
        size_bytes=1,
        sha256="a" * 64,
        mod_id="examplemod",
        minecraft_version="1.20.1",
        loader_version="0.15.11",
        java_version="21",
    )
    return MinecraftTestResult(
        run_id="run",
        status=status,
        reason=reason,
        spec=spec,
        target=target,
        evidence_paths=MinecraftEvidencePaths(root=Path("evidence")),
    )


def test_functional_repair_rebuilds_before_runtime_pass(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "functional", build_state="pass")
    provider = ScriptedProvider([
        AgentResponse(
            assistant_message="source",
            tool_calls=(ToolCall(call_id="1", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"}),),
        ),
        AgentResponse(
            assistant_message="repair",
            tool_calls=(ToolCall(call_id="2", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod { int signal; }\n"}),),
        ),
    ])
    controller, storage = _controller(root, provider)
    functional = ScriptedFunctionalValidator()
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    controller.functional_validator = functional
    state, report = controller.run(root, "functional", validation_contract={"schema_version": 1, "required_resources": []})

    assert state.state.value == "COMPLETED"
    assert state.build_attempt_count == 2
    assert functional.calls == 2
    assert report.validation_results[-1].status is ValidationStatus.PASS
    events = storage.read_events(state.run_id)
    event_names = [event.event_type.value for event in events]
    assert "SEMANTIC_REPAIR_FEEDBACK" in event_names
    assert event_names.count("BUILD_STARTED") == 2
    assert event_names.index("VALIDATION_COMPLETED") < event_names.index("BUILD_STARTED", event_names.index("VALIDATION_COMPLETED") + 1)


def test_functional_validator_maps_post_artifact_json_failure(tmp_path: Path) -> None:
    jar = tmp_path / "artifact.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("assets/examplemod/lang/en_us.json", "{}")
    artifact = type("Artifact", (), {"path": jar})()
    validator = BenchmarkFunctionalValidator(
        acceptance_spec={
            "required_resources": [{
                "path": "assets/examplemod/lang/en_us.json",
                "type": "json",
                "assertions": [{"kind": "json_pointer_present", "path": "/item.examplemod.signal_charm"}],
            }],
        }
    )
    result = validator.validate(tmp_path, artifact, None, "run")
    assert result.stage is ValidationStage.POST_ARTIFACT
    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert result.violations[0].code == "JSON_POINTER_MISSING"


def test_functional_validator_maps_infrastructure_to_blocked(tmp_path: Path) -> None:
    jar = tmp_path / "artifact.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("fabric.mod.json", "{}")
    artifact = type("Artifact", (), {"path": jar})()
    validator = BenchmarkFunctionalValidator(
        acceptance_spec={"required_resources": []},
        runtime_check=lambda artifact, run_id: _minecraft_result(MinecraftTestStatus.INFRA_ERROR, "harness unavailable"),
    )
    result = validator.validate(tmp_path, artifact, None, "run")
    assert result.status is ValidationStatus.BLOCKED
    assert result.stage is ValidationStage.RUNTIME
