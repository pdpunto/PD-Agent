from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pd_agent.core import (
    ArtifactResult,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    RunState,
    TaskProgressLedger,
    ValidationStatus,
)
from pd_agent.minecraft import MinecraftObservationStatus, MinecraftObservationType, ObservationResult, MinecraftTestStatus
from pd_agent.validation import ProductiveMinecraftFunctionalValidator


def _contract(runtime: bool = True) -> FabricTaskContract:
    requirement = FabricValidationRequirement(
        validation_requirement_id="runtime-validation",
        requirement_ids=("runtime",),
        kind="runtime",
        required=runtime,
        spec={
            "target_mod_id": "examplemod",
            "minecraft_version": "1.21.11",
            "loader_version": "0.19.3",
            "test_id": "registry",
            "observations": [{
                "observation_id": "obs-1",
                "observation_type": "REGISTRY_ENTRY_PRESENT",
                "profile": "registry_entry",
                "selector": {"kind": "registry", "id": "examplemod:item"},
                "expected": {"present": True},
                "requirement_ids": ["runtime"],
            }],
        },
    )
    return FabricTaskContract(
        task_id="normal-runtime",
        revision="1",
        goal="validate runtime",
        requirements=(FabricRequirement(requirement_id="runtime", description="runtime"),),
        validation_requirements=(requirement,),
    )


def _artifact(tmp_path: Path) -> ArtifactResult:
    path = tmp_path / "build" / "libs" / "mod.jar"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"current-artifact")
    return ArtifactResult(path=path, size=path.stat().st_size, timestamp=datetime.now(timezone.utc), classification="VALID")


class _Runner:
    def __init__(self, status: MinecraftObservationStatus) -> None:
        self.status = status
        self.calls = 0

    def run(self, spec, **kwargs):  # noqa: ANN001
        self.calls += 1
        observation = ObservationResult(
            observation_id="obs-1",
            observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
            status=self.status,
            expected={"present": True},
            actual={"present": self.status is MinecraftObservationStatus.PASS},
        )
        return SimpleNamespace(status=MinecraftTestStatus.PASS, observations=(observation,))


def _state(contract: FabricTaskContract, artifact: ArtifactResult) -> RunState:
    return RunState(project_root=artifact.path.parent.parent.parent, task_contract=contract, task=contract.task_id, progress_ledger=TaskProgressLedger(contract_identity=contract.identity()), build_results=(SimpleNamespace(attempt=1, success=True),))


def test_productive_boundary_validates_without_benchmark_imports(tmp_path: Path) -> None:
    contract = _contract()
    artifact = _artifact(tmp_path)
    runner = _Runner(MinecraftObservationStatus.PASS)
    state = _state(contract, artifact)
    validator = ProductiveMinecraftFunctionalValidator(contract=contract, runner=runner)
    validator.bind_run_state(state)

    result = validator.validate(artifact.path.parent, artifact, contract, state.run_id)

    assert result.status is ValidationStatus.PASS
    assert runner.calls == 1
    assert state.artifact_identity is not None
    assert state.progress_ledger is not None
    assert state.progress_ledger.satisfied_requirement_ids == ("runtime",)


def test_productive_boundary_records_runtime_failure(tmp_path: Path) -> None:
    contract = _contract()
    artifact = _artifact(tmp_path)
    runner = _Runner(MinecraftObservationStatus.FAIL)
    state = _state(contract, artifact)
    validator = ProductiveMinecraftFunctionalValidator(contract=contract, runner=runner)
    validator.bind_run_state(state)

    result = validator.validate(artifact.path.parent, artifact, contract, state.run_id)

    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert runner.calls == 1
    assert state.progress_ledger is not None and state.progress_ledger.failures


def test_invalid_artifact_never_reaches_runner(tmp_path: Path) -> None:
    contract = _contract()
    artifact = _artifact(tmp_path)
    invalid = ArtifactResult(path=artifact.path, size=artifact.size, timestamp=artifact.timestamp, classification="INVALID")
    runner = _Runner(MinecraftObservationStatus.PASS)
    state = _state(contract, artifact)
    validator = ProductiveMinecraftFunctionalValidator(contract=contract, runner=runner)
    validator.bind_run_state(state)

    result = validator.validate(artifact.path.parent, invalid, contract, state.run_id)

    assert result.status is ValidationStatus.BLOCKED
    assert runner.calls == 0


def test_runtime_not_required_never_reaches_runner(tmp_path: Path) -> None:
    contract = _contract(runtime=False)
    artifact = _artifact(tmp_path)
    runner = _Runner(MinecraftObservationStatus.PASS)
    state = _state(contract, artifact)
    validator = ProductiveMinecraftFunctionalValidator(contract=contract, runner=runner)
    validator.bind_run_state(state)

    result = validator.validate(artifact.path.parent, artifact, contract, state.run_id)

    assert result.status is ValidationStatus.PASS
    assert runner.calls == 0
