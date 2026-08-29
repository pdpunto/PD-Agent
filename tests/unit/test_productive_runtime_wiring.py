from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.core import (
    ArtifactResult,
    BuildAttemptIdentity,
    FailureFactStatus,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    RunState,
    TaskProgressLedger,
    ValidationStatus,
    compute_source_revision,
)
from pd_agent.minecraft import MinecraftEvidenceKind, MinecraftEvidenceReference, MinecraftObservationStatus, MinecraftObservationType, ObservationResult, MinecraftTestStatus
from pd_agent.validation import CompletionGate
from pd_agent.validation import ProductiveMinecraftFunctionalValidator
from pd_agent.validation.runtime import _artifact_reference
from pd_agent.core import SecurityViolation


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
        self.specs = []

    def run(self, spec, **kwargs):  # noqa: ANN001
        self.calls += 1
        self.specs.append(spec)
        observation = ObservationResult(
            observation_id="obs-1",
            observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
            status=self.status,
            expected={"present": True},
            actual={"present": self.status is MinecraftObservationStatus.PASS},
            evidence_refs=(MinecraftEvidenceReference(kind=MinecraftEvidenceKind.OBSERVATION, ref="runtime/observation.json"),),
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
    assert runner.specs[0].target_jar == Path("mod.jar")
    assert state.artifact_identity is not None
    assert state.progress_ledger is not None
    assert state.progress_ledger.satisfied_requirement_ids == ("runtime",)


def test_productive_boundary_consumes_runner_metadata_observation(tmp_path: Path) -> None:
    contract = _contract()
    artifact = _artifact(tmp_path)
    observation = ObservationResult(
        observation_id="obs-1",
        observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        status=MinecraftObservationStatus.PASS,
        expected={"present": True},
        actual={"present": True},
        evidence_refs=(MinecraftEvidenceReference(kind=MinecraftEvidenceKind.OBSERVATION, ref="runtime/observation.json"),),
    )

    class MetadataRunner:
        def run(self, spec, **kwargs):  # noqa: ANN001
            del spec, kwargs
            return SimpleNamespace(
                status=MinecraftTestStatus.PASS,
                metadata={"observation_result": observation.to_dict()},
            )

    state = _state(contract, artifact)
    validator = ProductiveMinecraftFunctionalValidator(contract=contract, runner=MetadataRunner())
    validator.bind_run_state(state)

    result = validator.validate(artifact.path.parent, artifact, contract, state.run_id)

    assert result.status is ValidationStatus.PASS
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


def test_invalid_observation_mapping_has_structured_violation_message(tmp_path: Path) -> None:
    contract = _contract()
    artifact = _artifact(tmp_path)
    runner = _Runner(MinecraftObservationStatus.PASS)
    state = _state(contract, artifact)
    validator = ProductiveMinecraftFunctionalValidator(contract=contract, runner=runner)
    validator.bind_run_state(state)

    original = runner.run

    def mismatched_run(spec, **kwargs):  # noqa: ANN001
        result = original(spec, **kwargs)
        return SimpleNamespace(status=MinecraftTestStatus.PASS, observations=())

    runner.run = mismatched_run
    result = validator.validate(tmp_path, artifact, contract, state.run_id)

    assert result.status is ValidationStatus.INVALID
    assert result.violations[0].code == "RUNTIME_OBSERVATION_MAPPING_INVALID"
    assert result.violations[0].message


def test_repair_reconciles_new_validated_artifact_before_second_runtime(tmp_path: Path) -> None:
    contract = _contract()
    artifact_a = _artifact(tmp_path)
    runner = _Runner(MinecraftObservationStatus.FAIL)
    state = _state(contract, artifact_a)
    validator = ProductiveMinecraftFunctionalValidator(contract=contract, runner=runner)
    validator.bind_run_state(state)

    first = validator.validate(tmp_path, artifact_a, contract, state.run_id)
    assert first.status is ValidationStatus.REPAIRABLE_FAIL
    identity_a = state.artifact_identity

    source = tmp_path / "src" / "ExampleMod.java"
    source.parent.mkdir()
    source.write_text("fixed", encoding="utf-8")
    artifact_a.path.write_bytes(b"repaired-artifact")
    artifact_b = ArtifactResult(path=artifact_a.path, size=artifact_a.path.stat().st_size, timestamp=datetime.now(timezone.utc), classification="VALID")
    build_b = BuildAttemptIdentity(
        build_attempt_id="build-2",
        source_revision="b" * 64,
        contract_identity=contract.identity(),
        result_ref="builds/2",
        success=True,
    )
    state.build_results = (SimpleNamespace(attempt=1, success=True), SimpleNamespace(attempt=2, success=True))
    state.build_identities = (*state.build_identities, build_b)
    validator.runner = _Runner(MinecraftObservationStatus.PASS)

    # The validator computes the current source revision from the workspace;
    # bind the new build identity to that same revision.
    build_b = replace(build_b, source_revision=compute_source_revision(tmp_path).revision)
    state.build_identities = (state.build_identities[0], build_b)
    second = validator.validate(tmp_path, artifact_b, contract, state.run_id)

    assert second.status is ValidationStatus.PASS
    assert identity_a is not None and state.artifact_identity is not None
    assert state.artifact_identity.artifact_identity != identity_a.artifact_identity
    assert runner.calls == 1
    assert len(state.runtime_identities) == 2
    assert state.runtime_identities[0].artifact_identity == identity_a.artifact_identity
    assert state.runtime_identities[1].artifact_identity == state.artifact_identity.artifact_identity
    assert [item.status for item in state.progress_ledger.failures] == [FailureFactStatus.ACTIVE, FailureFactStatus.RESOLVED]
    assert CompletionGate().evaluate(contract, state.progress_ledger, state).complete is True


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


def test_internal_absolute_artifact_becomes_relative_runtime_reference(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)

    assert _artifact_reference(tmp_path, artifact.path) == Path("build/libs/mod.jar")


def test_external_absolute_artifact_is_rejected_before_runtime(tmp_path: Path) -> None:
    external = tmp_path.parent / "external.jar"
    external.write_bytes(b"external")

    with pytest.raises(SecurityViolation, match="artifact path escapes project_root"):
        _artifact_reference(tmp_path, external)


def test_artifact_traversal_is_rejected_before_runtime(tmp_path: Path) -> None:
    with pytest.raises(SecurityViolation, match="path escapes project_root"):
        _artifact_reference(tmp_path, Path("..") / "external.jar")
