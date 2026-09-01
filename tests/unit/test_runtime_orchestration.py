from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pd_agent.core import ArtifactIdentity, BuildAttemptIdentity, FabricRequirement, FabricTaskContract, FabricValidationRequirement, RunState, TaskProgressLedger, ValidationResult, ValidationStage, ValidationStatus
from pd_agent.minecraft import (
    FabricRuntimeOrchestrator,
    MinecraftEvidenceKind,
    MinecraftEvidenceReference,
    MinecraftObservationStatus,
    MinecraftObservationType,
    MinecraftTestSpec,
    MinecraftTestStatus,
    ObservationResult,
    RuntimeOrchestrationStatus,
    runtime_spec_from_requirement,
)
from pd_agent.runtime import AgentRuntime


SHA = "a" * 64
ENV_ROOT = Path("C:/runtime")


def _requirement(kind: str = "runtime") -> FabricValidationRequirement:
    return FabricValidationRequirement(
        validation_requirement_id="v-runtime",
        requirement_ids=("r-runtime",),
        kind=kind,
        spec={
            "observations": [{
                "observation_id": "obs-1",
                "observation_type": MinecraftObservationType.REGISTRY_ENTRY_PRESENT.value,
                "profile": "registry_entry",
                "selector": {"kind": "registry", "id": "examplemod:item"},
                "expected": {"present": True},
                "requirement_ids": ["r-runtime"],
            }],
        },
    )


def _contract(*, requirement: FabricValidationRequirement | None = None) -> FabricTaskContract:
    return FabricTaskContract(
        task_id="runtime-task",
        revision="1",
        goal="run a runtime observation",
        requirements=(FabricRequirement(requirement_id="r-runtime", description="runtime behavior"),),
        validation_requirements=((requirement,) if requirement else ()),
    )


def _state(contract: FabricTaskContract) -> tuple[RunState, ArtifactIdentity]:
    build = BuildAttemptIdentity(build_attempt_id="build-1", source_revision=SHA, contract_identity=contract.identity(), success=True)
    artifact = ArtifactIdentity(artifact_identity=SHA, sha256=SHA, producing_build_attempt_id="build-1", source_revision=SHA, contract_identity=contract.identity())
    return RunState(task=contract.task_id, progress_ledger=TaskProgressLedger(contract_identity=contract.identity()), build_identities=(build,), artifact_identity=artifact), artifact


def _spec(tmp_path: Path) -> MinecraftTestSpec:
    target = tmp_path / "mod.jar"
    target.write_bytes(b"jar")
    return MinecraftTestSpec(target_jar=target, target_mod_id="examplemod", minecraft_version="1.21.11", loader_version="0.19.3", test_id="runtime", timeout_seconds=10)


def _observation(status: MinecraftObservationStatus = MinecraftObservationStatus.PASS) -> ObservationResult:
    return ObservationResult(observation_id="obs-1", observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT, status=status, expected={"present": True}, actual={"present": status is MinecraftObservationStatus.PASS}, evidence_refs=(MinecraftEvidenceReference(kind=MinecraftEvidenceKind.OBSERVATION, ref="observation/1.json"),))


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run(self, spec, **kwargs):
        self.calls += 1
        return self.result


def test_runtime_requirement_maps_explicit_observation_to_requirement() -> None:
    plan = runtime_spec_from_requirement(_requirement())
    assert plan.observation_requirements == {"obs-1": ("r-runtime",)}
    assert plan.observations[0].observation_id == "obs-1"


def test_no_runtime_requirement_does_not_launch(tmp_path: Path) -> None:
    contract = _contract()
    runner = FakeRunner((_observation(),))
    state, artifact = _state(contract)
    outcome = FabricRuntimeOrchestrator(runner).validate(contract=contract, run_state=state, artifact=artifact, source_revision=SHA, minecraft_spec=_spec(tmp_path))
    assert outcome.status is RuntimeOrchestrationStatus.NOT_REQUIRED
    assert runner.calls == 0


def test_missing_or_stale_artifact_blocks_without_launch(tmp_path: Path) -> None:
    contract = _contract(requirement=_requirement())
    runner = FakeRunner((_observation(),))
    state, artifact = _state(contract)
    state.artifact_identity = None
    outcome = FabricRuntimeOrchestrator(runner).validate(contract=contract, run_state=state, artifact=artifact, source_revision=SHA, minecraft_spec=_spec(tmp_path))
    assert outcome.status is RuntimeOrchestrationStatus.BLOCKED
    assert runner.calls == 0


def test_current_artifact_launches_and_pass_is_bound_and_reusable(tmp_path: Path) -> None:
    contract = _contract(requirement=_requirement())
    runner = FakeRunner((_observation(),))
    state, artifact = _state(contract)
    orchestrator = FabricRuntimeOrchestrator(runner)
    first = orchestrator.validate(contract=contract, run_state=state, artifact=artifact, source_revision=SHA, minecraft_spec=_spec(tmp_path))
    second = orchestrator.validate(contract=contract, run_state=state, artifact=artifact, source_revision=SHA, minecraft_spec=_spec(tmp_path))
    assert first.status is RuntimeOrchestrationStatus.VALIDATED
    assert first.validation_result is not None and first.validation_result.status.value == "PASS"
    assert second.status is RuntimeOrchestrationStatus.REUSED
    assert runner.calls == 1
    assert state.progress_ledger is not None and state.progress_ledger.satisfied_requirement_ids == ()
    assert state.validation_results == ()


def test_agent_runtime_owns_one_validation_result_per_logical_validation() -> None:
    class FunctionalValidator:
        last_results = ()

        def validate(self, project_root, artifact, contract, run_id):  # noqa: ANN001
            del project_root, artifact, contract, run_id
            return ValidationResult(
                stage=ValidationStage.RUNTIME,
                status=ValidationStatus.PASS,
                summary="runtime validation passed",
            )

    contract = _contract(requirement=_requirement())
    state, _artifact_identity = _state(contract)
    state.artifact_result = object()
    runtime = AgentRuntime(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
        context_manager=object(),
        functional_validator=FunctionalValidator(),
    )

    project_snapshot = SimpleNamespace(project_root=Path("."))
    assert runtime._run_functional_validation(state, project_snapshot, []) == "PASS"
    assert runtime._run_functional_validation(state, project_snapshot, []) == "PASS"
    assert len(state.validation_results) == 2


def test_failed_target_observation_is_repairable_and_failure_is_active(tmp_path: Path) -> None:
    contract = _contract(requirement=_requirement())
    runner = FakeRunner((_observation(MinecraftObservationStatus.FAIL),))
    state, artifact = _state(contract)
    outcome = FabricRuntimeOrchestrator(runner).validate(contract=contract, run_state=state, artifact=artifact, source_revision=SHA, minecraft_spec=_spec(tmp_path))
    assert outcome.validation_result is not None and outcome.validation_result.status.value == "REPAIRABLE_FAIL"
    assert outcome.failure_fact is not None
    assert outcome.failure_fact.requirement_ids == ("r-runtime",)
    assert state.progress_ledger is not None and state.progress_ledger.failures


def test_harness_crash_is_blocked_not_target_repair(tmp_path: Path) -> None:
    contract = _contract(requirement=_requirement())
    runner = FakeRunner(SimpleNamespace(status=MinecraftTestStatus.CRASH, observations=()))
    state, artifact = _state(contract)
    outcome = FabricRuntimeOrchestrator(runner).validate(contract=contract, run_state=state, artifact=artifact, source_revision=SHA, minecraft_spec=_spec(tmp_path))
    assert outcome.validation_result is not None and outcome.validation_result.status.value == "BLOCKED"
    assert outcome.validation_result.violations[0].code == "RUNTIME_HARNESS_BLOCKED"


def test_target_startup_crash_is_repairable_with_failure_evidence(tmp_path: Path) -> None:
    contract = _contract(requirement=_requirement())
    log_path = tmp_path / "latest.log"
    log_path.write_text("Block id not set", encoding="utf-8")
    runner = FakeRunner(SimpleNamespace(
        status=MinecraftTestStatus.CRASH,
        reason="target mod failed during Minecraft startup",
        target_failure_reason="Block id not set",
        metadata={"target_startup_failure": True},
        runtime_evidence=SimpleNamespace(
            latest_log_path=log_path,
            harness_result_path=tmp_path / "harness-result.json",
            metadata={},
        ),
        observations=(),
    ))
    state, artifact = _state(contract)
    outcome = FabricRuntimeOrchestrator(runner).validate(contract=contract, run_state=state, artifact=artifact, source_revision=SHA, minecraft_spec=_spec(tmp_path))
    assert outcome.validation_result is not None
    assert outcome.validation_result.status is ValidationStatus.REPAIRABLE_FAIL
    assert outcome.validation_result.violations[0].code == "RUNTIME_TARGET_STARTUP_FAILURE"
    assert outcome.validation_result.violations[0].actual == "Block id not set"
    assert str(log_path) in outcome.validation_result.evidence_refs
    assert outcome.failure_fact is not None
    assert outcome.failure_fact.code == "RUNTIME_TARGET_STARTUP_FAILURE"
