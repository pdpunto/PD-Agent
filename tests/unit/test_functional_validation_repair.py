from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from pd_agent.core import AgentResponse, ExecutionLimits, RunStatus, ToolCall, ValidationResult, ValidationStage, ValidationStatus, ValidationViolation
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


def test_runtime_repair_gate_violation_without_mutation_does_not_rebuild(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "runtime-noop-gate", build_state="pass")
    provider = ScriptedProvider([
        AgentResponse(
            assistant_message="source",
            tool_calls=(ToolCall(
                call_id="1",
                tool_name="write_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"},
            ),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(
                call_id="2",
                tool_name="read_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java"},
            ),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(
                call_id="3",
                tool_name="list_directory",
                arguments={"path": "src/main"},
            ),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(
                call_id="4",
                tool_name="read_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java"},
            ),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(
                call_id="5",
                tool_name="list_directory",
                arguments={"path": "src/main"},
            ),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(
                call_id="6",
                tool_name="list_directory",
                arguments={"path": "src/main"},
            ),),
        ),
        AgentResponse(assistant_message="no mutation"),
    ])
    controller, storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    controller.functional_validator = SequenceFunctionalValidator([ValidationStatus.REPAIRABLE_FAIL])

    state, _report = controller.run(root, "runtime no-op gate", validation_contract={"schema_version": 1, "required_resources": []})

    assert state.state.value == "FAILED"
    assert state.termination_reason == "semantic repair produced no mutation"
    assert state.build_attempt_count == 1
    assert len([event for event in storage.read_events(state.run_id) if event.event_type.value == "BUILD_STARTED"]) == 1


def test_each_runtime_repair_cycle_requires_its_own_mutation(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "runtime-second-noop", build_state="pass")
    provider = ScriptedProvider([
        AgentResponse(
            assistant_message="source",
            tool_calls=(ToolCall(
                call_id="1",
                tool_name="write_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"},
            ),),
        ),
        AgentResponse(
            assistant_message="repair one",
            tool_calls=(ToolCall(
                call_id="2",
                tool_name="write_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod { int one; }\n"},
            ),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(call_id="3", tool_name="read_file", arguments={"path": "src/main/java/com/example/ExampleMod.java"}),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(call_id="4", tool_name="list_directory", arguments={"path": "src/main"}),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(call_id="5", tool_name="read_file", arguments={"path": "src/main/java/com/example/ExampleMod.java"}),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(call_id="6", tool_name="list_directory", arguments={"path": "src/main"}),),
        ),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(call_id="7", tool_name="list_directory", arguments={"path": "src/main"}),),
        ),
        AgentResponse(assistant_message="no second mutation"),
    ])
    controller, _storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    controller.functional_validator = SequenceFunctionalValidator([
        ValidationStatus.REPAIRABLE_FAIL,
        ValidationStatus.REPAIRABLE_FAIL,
    ])

    state, _report = controller.run(root, "runtime second repair", validation_contract={"schema_version": 1, "required_resources": []})

    assert state.state.value == "FAILED"
    assert state.termination_reason == "semantic repair produced no mutation"
    assert state.build_attempt_count == 2


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


class SequenceFunctionalValidator:
    def __init__(self, runtime_statuses: list[ValidationStatus], *, post_failures: int = 0) -> None:
        self.runtime_statuses = list(runtime_statuses)
        self.post_failures = post_failures
        self.calls = 0
        self.last_results: tuple[ValidationResult, ...] = ()
        self.artifacts: list[object] = []

    def validate(self, project_root, artifact, contract, run_id):  # noqa: ANN001
        del project_root, contract, run_id
        self.calls += 1
        self.artifacts.append(artifact)
        if self.post_failures >= self.calls:
            post = ValidationResult(
                stage=ValidationStage.POST_ARTIFACT,
                status=ValidationStatus.REPAIRABLE_FAIL,
                summary="post artifact failed",
                violations=(ValidationViolation(
                    code="JSON_POINTER_MISMATCH",
                    requirement="assets/examplemod/lang/en_us.json:/item.examplemod.server_core",
                    observed={"category": "mismatch"},
                    message="required artifact value was not delivered",
                ),),
            )
            self.last_results = (post,)
            return post
        post = ValidationResult(stage=ValidationStage.POST_ARTIFACT, status=ValidationStatus.PASS, summary="artifact ok")
        status = self.runtime_statuses[min(self.calls - self.post_failures - 1, len(self.runtime_statuses) - 1)]
        if status is ValidationStatus.PASS:
            runtime = ValidationResult(stage=ValidationStage.RUNTIME, status=status, summary="runtime ok")
        else:
            runtime = ValidationResult(
                stage=ValidationStage.RUNTIME,
                status=status,
                summary="runtime failed",
                violations=(ValidationViolation(
                    code="REGISTRY_ENTRY_PRESENT",
                    requirement="item registry entry examplemod:signal_charm",
                    observed={"category": "missing"},
                    message="required item registry entry was not observed",
                ),),
            )
        self.last_results = (post, runtime)
        return runtime


def _repair_provider() -> ScriptedProvider:
    return ScriptedProvider([
        AgentResponse(
            assistant_message="source",
            tool_calls=(ToolCall(call_id="1", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"}),),
        ),
        AgentResponse(
            assistant_message="repair resources",
            tool_calls=(ToolCall(call_id="2", tool_name="create_file", arguments={"path": "assets/examplemod/lang/en_us.json", "content": '{"item.examplemod.server_core":"Server Core"}\n'}),),
        ),
        AgentResponse(
            assistant_message="repair runtime",
            tool_calls=(ToolCall(call_id="3", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod { int registered; }\n"}),),
        ),
    ])


def test_t2_like_end_to_end_prebuild_then_runtime_repair(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "t2", build_state="pass")
    controller, storage = _controller(root, _repair_provider())
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    functional = SequenceFunctionalValidator([ValidationStatus.REPAIRABLE_FAIL, ValidationStatus.PASS], post_failures=0)
    controller.functional_validator = functional
    contract = {
        "schema_version": 1,
        "required_resources": [{
            "path": "assets/examplemod/lang/en_us.json",
            "resource_type": "json",
            "assertions": [{"kind": "json_pointer_present", "path": "/item.examplemod.server_core"}],
        }],
    }
    state, report = controller.run(root, "Marble Lantern", validation_contract=contract, pending_mutation_targets=("role:source",))

    assert state.state.value == "COMPLETED"
    assert state.build_attempt_count >= 2
    assert functional.calls == 2
    assert len(functional.artifacts) == state.build_attempt_count
    assert any(item.stage is ValidationStage.PRE_BUILD and item.status is ValidationStatus.REPAIRABLE_FAIL for item in state.validation_results)
    assert any(item.stage is ValidationStage.RUNTIME and item.status is ValidationStatus.REPAIRABLE_FAIL for item in state.validation_results)
    assert report.validation_results[-1].status is ValidationStatus.PASS
    assert state.pending_mutation_targets == ()
    feedback = [event.payload["feedback"] for event in storage.read_events(state.run_id) if event.event_type.value == "SEMANTIC_REPAIR_FEEDBACK"]
    assert len(feedback) == 2
    assert all("reference" not in item.casefold() and "api" not in item.casefold() for item in feedback)


def test_t3_like_post_artifact_then_runtime_repair(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "t3", build_state="pass")
    controller, _storage = _controller(root, _repair_provider())
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    functional = SequenceFunctionalValidator([ValidationStatus.REPAIRABLE_FAIL, ValidationStatus.PASS], post_failures=1)
    controller.functional_validator = functional
    state, _report = controller.run(root, "Server Core", validation_contract={"schema_version": 1, "required_resources": []})

    assert state.state.value == "COMPLETED"
    assert state.build_attempt_count >= 2
    assert [item.stage for item in state.validation_results].count(ValidationStage.POST_ARTIFACT) >= 2
    assert any(item.stage is ValidationStage.RUNTIME and item.status is ValidationStatus.REPAIRABLE_FAIL for item in state.validation_results)


@pytest.mark.parametrize("cause", ["Item id not set", "Block id not set", "target initialization exception"])
def test_target_startup_causes_are_repairable_feedback(tmp_path: Path, cause: str) -> None:
    jar = tmp_path / "artifact.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("fabric.mod.json", "{}")
    artifact = type("Artifact", (), {"path": jar})()
    validator = BenchmarkFunctionalValidator(
        acceptance_spec={"required_resources": []},
        runtime_check=lambda artifact, run_id: _minecraft_result(MinecraftTestStatus.CRASH, cause),
    )
    result = validator.validate(tmp_path, artifact, None, "run")
    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert result.violations[0].message == cause


@pytest.mark.parametrize("status", [MinecraftTestStatus.CRASH, MinecraftTestStatus.INFRA_ERROR, MinecraftTestStatus.TIMEOUT])
def test_unknown_or_non_target_runtime_failures_are_blocked(tmp_path: Path, status: MinecraftTestStatus) -> None:
    jar = tmp_path / "artifact.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("fabric.mod.json", "{}")
    artifact = type("Artifact", (), {"path": jar})()
    reason = "unknown startup failure" if status is MinecraftTestStatus.CRASH else "runtime unavailable"
    validator = BenchmarkFunctionalValidator(
        acceptance_spec={"required_resources": []},
        runtime_check=lambda artifact, run_id: _minecraft_result(status, reason),
    )
    result = validator.validate(tmp_path, artifact, None, "run")
    assert result.status is ValidationStatus.BLOCKED


@pytest.mark.parametrize("stage", [ValidationStage.POST_ARTIFACT, ValidationStage.RUNTIME])
def test_repeated_functional_violation_is_terminal(tmp_path: Path, stage: ValidationStage) -> None:
    root = _runtime_project(tmp_path / stage.value, build_state="pass")
    provider = ScriptedProvider([
        AgentResponse(assistant_message="source", tool_calls=(ToolCall(call_id="1", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"}),)),
        AgentResponse(
            assistant_message="inspect",
            tool_calls=(ToolCall(
                call_id="2",
                tool_name="read_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java"},
            ),),
        ),
        AgentResponse(
            assistant_message="inspect again",
            tool_calls=(ToolCall(
                call_id="3",
                tool_name="read_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java"},
            ),),
        ),
    ])
    controller, _storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    functional = SequenceFunctionalValidator([ValidationStatus.REPAIRABLE_FAIL, ValidationStatus.REPAIRABLE_FAIL], post_failures=2 if stage is ValidationStage.POST_ARTIFACT else 0)
    controller.functional_validator = functional
    state, _report = controller.run(root, "stall", validation_contract={"schema_version": 1, "required_resources": []})
    assert state.state.value == "FAILED"
    assert state.termination_reason == "semantic repair produced no mutation"


def test_noop_repair_does_not_trigger_stale_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "noop-repair", build_state="pass")
    provider = ScriptedProvider([
        AgentResponse(
            assistant_message="source",
            tool_calls=(ToolCall(
                call_id="1",
                tool_name="write_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod { int signal; }\n"},
            ),),
        ),
        AgentResponse(
            assistant_message="inspect only",
            tool_calls=(ToolCall(
                call_id="2",
                tool_name="read_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java"},
            ),),
        ),
        AgentResponse(
            assistant_message="repair after inspection",
            tool_calls=(ToolCall(
                call_id="3",
                tool_name="write_file",
                arguments={
                    "path": "src/main/java/com/example/ExampleMod.java",
                    "content": "class ExampleMod { int repaired; }\n",
                },
            ),),
        ),
    ])
    controller, _storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    controller.functional_validator = SequenceFunctionalValidator([
        ValidationStatus.REPAIRABLE_FAIL,
        ValidationStatus.PASS,
    ])

    state, _report = controller.run(root, "noop repair", validation_contract={"schema_version": 1, "required_resources": []})

    assert state.state.value == "COMPLETED"
    assert state.build_attempt_count == 2


def test_multiple_mutations_pair_latest_artifact_with_latest_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "latest-artifact", build_state="pass")
    controller, _storage = _controller(root, _repair_provider())
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    functional = SequenceFunctionalValidator([
        ValidationStatus.REPAIRABLE_FAIL,
        ValidationStatus.REPAIRABLE_FAIL,
        ValidationStatus.PASS,
    ])
    controller.functional_validator = functional

    state, report = controller.run(root, "latest artifact", validation_contract={"schema_version": 1, "required_resources": []})

    assert state.state.value == "COMPLETED"
    assert state.build_attempt_count == 3
    assert report.final_build is not None
    assert report.final_build.attempt == 3
    assert report.artifact is state.artifact_result
    assert len(functional.artifacts) == 3
    timestamps = [artifact.timestamp for artifact in functional.artifacts]
    assert timestamps == sorted(timestamps)
    assert report.artifact.timestamp == timestamps[-1]


def test_blocked_runtime_does_not_repair_or_build_again(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "blocked", build_state="pass")
    provider = ScriptedProvider([AgentResponse(assistant_message="source", tool_calls=(ToolCall(call_id="1", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"}),))])
    controller, _storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    functional = SequenceFunctionalValidator([ValidationStatus.BLOCKED])
    controller.functional_validator = functional
    state, _report = controller.run(root, "blocked", validation_contract={"schema_version": 1, "required_resources": []})
    assert state.state.value == "BLOCKED"
    assert state.build_attempt_count == 1
    assert len(provider.requests) == 1


def test_real_edit_progress_resets_functional_stall(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "progress", build_state="pass")
    controller, _storage = _controller(root, _repair_provider())
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    controller.functional_validator = SequenceFunctionalValidator([
        ValidationStatus.REPAIRABLE_FAIL,
        ValidationStatus.REPAIRABLE_FAIL,
        ValidationStatus.PASS,
    ])
    state, _report = controller.run(root, "progress", validation_contract={"schema_version": 1, "required_resources": []})
    assert state.state.value == "COMPLETED"
    assert state.build_attempt_count == 3


@pytest.mark.parametrize("status", [MinecraftTestStatus.TIMEOUT])
def test_runtime_timeout_and_missing_result_are_blocked(tmp_path: Path, status: MinecraftTestStatus) -> None:
    jar = tmp_path / "artifact.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("fabric.mod.json", "{}")
    artifact = type("Artifact", (), {"path": jar})()
    for runtime_result in (lambda artifact, run_id: _minecraft_result(status, "timeout"), lambda artifact, run_id: None):
        validator = BenchmarkFunctionalValidator(acceptance_spec={"required_resources": []}, runtime_check=runtime_result)
        result = validator.validate(tmp_path, artifact, None, "run")
        assert result.status is ValidationStatus.BLOCKED


def test_functional_repair_respects_build_limit(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "limit", build_state="pass")
    controller, _storage = _controller(
        root,
        ScriptedProvider([AgentResponse(assistant_message="source", tool_calls=(ToolCall(call_id="1", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"}),))]),
        limits=ExecutionLimits(max_build_attempts=1),
    )
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    controller.functional_validator = SequenceFunctionalValidator([ValidationStatus.REPAIRABLE_FAIL])
    state, _report = controller.run(root, "limit", validation_contract={"schema_version": 1, "required_resources": []})
    assert state.state.value == "LIMIT_REACHED"
    assert state.build_attempt_count == 1


def test_validation_evidence_round_trip(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "roundtrip", build_state="pass")
    controller, storage = _controller(root, _repair_provider())
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    controller.functional_validator = SequenceFunctionalValidator([ValidationStatus.REPAIRABLE_FAIL, ValidationStatus.PASS])
    state, report = controller.run(root, "roundtrip", validation_contract={"schema_version": 1, "required_resources": []})
    restored_state = type(state).from_dict(state.to_dict())
    restored_report = type(report).from_dict(report.to_dict())
    events = storage.read_events(state.run_id)
    assert restored_state.validation_results == state.validation_results
    assert restored_report.validation_results == report.validation_results
    assert any(event.event_type.value == "VALIDATION_COMPLETED" for event in events)
    assert any(event.event_type.value == "SEMANTIC_REPAIR_FEEDBACK" for event in events)


def test_executor_does_not_double_run_minecraft_after_controller_evidence(monkeypatch, tmp_path: Path) -> None:
    from dataclasses import replace

    from pd_agent.benchmark.executor import BenchmarkExecutor
    from tests.unit.test_benchmark_executor import _artifact_jar, _config, _fixture_root, _final_report, _run_state, _task

    class ControllerWithFunctionalEvidence:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.storage = kwargs["storage"]

        def run(self, project_root, task, *, external_context=(), model_config=None, pending_mutation_targets=(), validation_contract=None):  # noqa: ANN001
            del external_context, model_config, pending_mutation_targets, validation_contract
            state = _run_state(project_root, task, status=RunStatus.COMPLETED)
            state.artifact_result = _artifact_jar(project_root)
            state.validation_results = (
                ValidationResult(stage=ValidationStage.POST_ARTIFACT, status=ValidationStatus.PASS, summary="artifact ok"),
                ValidationResult(stage=ValidationStage.RUNTIME, status=ValidationStatus.PASS, summary="runtime ok"),
            )
            report = replace(_final_report(state), validation_results=state.validation_results)
            return state, report

    class CountingRunner:
        project_root = tmp_path / "runner-root"
        calls = []

        def run(self, *args, **kwargs):  # noqa: ANN002, ANN003
            self.calls.append((args, kwargs))
            raise AssertionError("Minecraft was executed twice after controller functional evidence")

    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", ControllerWithFunctionalEvidence)
    executor = BenchmarkExecutor(provider=object(), build_runner=object(), artifact_validator=object())
    task = _task(
        minecraft=True,
        observation_type="REGISTRY_ENTRY_PRESENT",
        observation_params={"registry_kind": "item", "identifier": "examplemod:signal_charm"},
    )
    attempt = type("Attempt", (), {"scheduled_attempt_id": "no-double", "attempt_index": 1, "repetition_index": 0})()
    result = executor.execute(task, _config(brain_enabled=False), attempt, fixture_root=_fixture_root(), execution_root=tmp_path / "exec", minecraft_runner=CountingRunner())
    assert result.run_state.validation_results[-1].stage is ValidationStage.RUNTIME
