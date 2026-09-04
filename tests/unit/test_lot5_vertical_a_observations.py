from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.core import (
    ArtifactIdentity,
    BuildAttemptIdentity,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    RunState,
    TaskProgressLedger,
)
from pd_agent.minecraft import (
    FabricRuntimeOrchestrator,
    MinecraftEvidenceKind,
    MinecraftEvidenceReference,
    MinecraftObservationStatus,
    MinecraftObservationType,
    MinecraftTestSpec,
    MinecraftTestRunner,
    MinecraftTestStatus,
    ObservationRequest,
    ObservationResult,
    RuntimeOrchestrationStatus,
    runtime_spec_from_requirement,
)


SHA = "a" * 64


def _association_request(*, item_id: str = "examplemod:server_core", block_id: str = "examplemod:server_core") -> ObservationRequest:
    return ObservationRequest(
        observation_id="block-item-association",
        observation_type=MinecraftObservationType.BLOCK_ITEM_ASSOCIATION,
        profile="block_item_association",
        selector={"kind": "block_item_association", "item_id": item_id, "block_id": block_id},
        expected={"associated": True},
    )


def _vertical_requirement() -> FabricValidationRequirement:
    return FabricValidationRequirement(
        validation_requirement_id="validation:vertical-a-runtime",
        requirement_ids=("requirement:block", "requirement:item", "requirement:association"),
        kind="runtime",
        spec={
            "profile": "vertical_a_runtime_v1",
            "observations": [
                {
                    "observation_id": "block-registry",
                    "observation_type": "REGISTRY_ENTRY_PRESENT",
                    "profile": "registry",
                    "selector": {"kind": "registry", "registry_kind": "block", "identifier": "examplemod:server_core"},
                    "expected": {"present": True},
                    "requirement_ids": ["requirement:block"],
                },
                {
                    "observation_id": "item-registry",
                    "observation_type": "REGISTRY_ENTRY_PRESENT",
                    "profile": "registry",
                    "selector": {"kind": "registry", "registry_kind": "item", "identifier": "examplemod:server_core"},
                    "expected": {"present": True},
                    "requirement_ids": ["requirement:item"],
                },
                {
                    "observation_id": "block-item-association",
                    "observation_type": "BLOCK_ITEM_ASSOCIATION",
                    "profile": "block_item_association",
                    "selector": {"kind": "block_item_association", "item_id": "examplemod:server_core", "block_id": "examplemod:server_core"},
                    "expected": {"associated": True},
                    "requirement_ids": ["requirement:association"],
                },
            ],
        },
    )


def _contract() -> FabricTaskContract:
    return FabricTaskContract(
        task_id="vertical-a",
        revision="1",
        goal="runtime",
        requirements=tuple(FabricRequirement(requirement_id=item, description=item) for item in ("requirement:block", "requirement:item", "requirement:association")),
        validation_requirements=(_vertical_requirement(),),
    )


def _state(contract: FabricTaskContract) -> tuple[RunState, ArtifactIdentity]:
    build = BuildAttemptIdentity(
        build_attempt_id="build-1",
        source_revision=SHA,
        contract_identity=contract.identity(),
        success=True,
    )
    artifact = ArtifactIdentity(
        artifact_identity=SHA,
        sha256=SHA,
        producing_build_attempt_id="build-1",
        source_revision=SHA,
        contract_identity=contract.identity(),
    )
    return RunState(
        task=contract.task_id,
        progress_ledger=TaskProgressLedger(contract_identity=contract.identity()),
        build_identities=(build,),
        artifact_identity=artifact,
    ), artifact


def _observation(observation_id: str, observation_type: MinecraftObservationType, status: MinecraftObservationStatus, expected: dict, actual: dict) -> ObservationResult:
    return ObservationResult(
        observation_id=observation_id,
        observation_type=observation_type,
        status=status,
        expected=expected,
        actual=actual,
        evidence_refs=(MinecraftEvidenceReference(kind=MinecraftEvidenceKind.OBSERVATION, ref=f"observation/{observation_id}.json"),),
    )


def test_block_item_association_contract_round_trip() -> None:
    request = _association_request()
    restored = ObservationRequest.from_dict(request.to_dict())
    assert restored == request
    assert restored.selector == {"kind": "block_item_association", "item_id": "examplemod:server_core", "block_id": "examplemod:server_core"}


@pytest.mark.parametrize(
    "selector",
    [
        {"kind": "block_item_association", "block_id": "examplemod:block"},
        {"kind": "block_item_association", "item_id": "examplemod:item"},
        {"kind": "block_item_association", "item_id": "bad", "block_id": "examplemod:block"},
    ],
)
def test_block_item_association_rejects_missing_or_malformed_ids(selector: dict) -> None:
    with pytest.raises(ValueError):
        ObservationRequest(
            observation_id="association",
            observation_type=MinecraftObservationType.BLOCK_ITEM_ASSOCIATION,
            profile="block_item_association",
            selector=selector,
            expected={"associated": True},
        )


def test_vertical_a_accepts_one_heterogeneous_runtime_requirement() -> None:
    plan = runtime_spec_from_requirement(_vertical_requirement())
    assert len(plan.observations) == 3
    assert [item.observation_type for item in plan.observations] == [
        MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        MinecraftObservationType.BLOCK_ITEM_ASSOCIATION,
    ]
    assert plan.observation_requirements["block-item-association"] == ("requirement:association",)


@pytest.mark.parametrize(
    ("item_present", "is_block_item", "actual_block_id", "status"),
    [
        (True, True, "examplemod:server_core", MinecraftObservationStatus.PASS),
        (False, False, None, MinecraftObservationStatus.FAIL),
        (True, False, None, MinecraftObservationStatus.FAIL),
        (True, True, "examplemod:other", MinecraftObservationStatus.FAIL),
    ],
)
def test_block_item_association_result_represents_real_semantic_outcomes(
    item_present: bool,
    is_block_item: bool,
    actual_block_id: str | None,
    status: MinecraftObservationStatus,
) -> None:
    result = _observation(
        "block-item-association",
        MinecraftObservationType.BLOCK_ITEM_ASSOCIATION,
        status,
        {"associated": True},
        {
            "item_present": item_present,
            "is_block_item": is_block_item,
            "actual_block_id": actual_block_id,
            "associated": status is MinecraftObservationStatus.PASS,
        },
    )
    restored = ObservationResult.from_dict(result.to_dict())
    assert restored.status is status
    assert restored.actual["is_block_item"] is is_block_item


def test_runner_maps_block_item_association_harness_result(tmp_path: Path) -> None:
    runner = MinecraftTestRunner(project_root=tmp_path)
    status, _reason, metadata = runner._classify_runtime(
        process={"timed_out": False, "exit_code": 0},
        harness_result={
            "test_id": "block-item-association",
            "observation_type": "BLOCK_ITEM_ASSOCIATION",
            "target_loaded": True,
            "target_origin_resolved": True,
            "target_sha_match": True,
            "server_started": True,
            "functional_test_result": "PASS",
            "observation_expected": {"associated": True},
            "observation_actual": {
                "item_present": True,
                "is_block_item": True,
                "actual_block_id": "examplemod:server_core",
                "associated": True,
            },
            "shutdown_requested": True,
        },
        latest_log="",
        launch_mode="pass",
        target=SimpleNamespace(path=Path("target.jar"), sha256=SHA, mod_id="examplemod"),
        timeout_seconds=30,
        observation_id="block-item-association",
    )
    assert status is MinecraftTestStatus.PASS
    observation = ObservationResult.from_dict(metadata["observation_result"])
    assert observation.observation_type is MinecraftObservationType.BLOCK_ITEM_ASSOCIATION
    assert observation.actual["is_block_item"] is True


class FakeRunner:
    def __init__(self, observations: tuple[ObservationResult, ...]) -> None:
        self.observations = observations
        self.calls = 0

    def run(self, spec: MinecraftTestSpec, **kwargs: object) -> object:
        self.calls += 1
        assert len(spec.observation_requests) == 3
        return SimpleNamespace(status=MinecraftTestStatus.PASS, observations=self.observations)


def test_failed_observations_correlate_only_their_requirements() -> None:
    contract = _contract()
    state, artifact = _state(contract)
    plan = runtime_spec_from_requirement(_vertical_requirement())
    observations = (
        _observation("block-registry", MinecraftObservationType.REGISTRY_ENTRY_PRESENT, MinecraftObservationStatus.PASS, {"present": True}, {"present": True}),
        _observation("item-registry", MinecraftObservationType.REGISTRY_ENTRY_PRESENT, MinecraftObservationStatus.FAIL, {"present": True}, {"present": False}),
        _observation("block-item-association", MinecraftObservationType.BLOCK_ITEM_ASSOCIATION, MinecraftObservationStatus.FAIL, {"associated": True}, {"associated": False, "is_block_item": False}),
    )
    outcome = FabricRuntimeOrchestrator(FakeRunner(observations)).validate(
        contract=contract,
        run_state=state,
        artifact=artifact,
        source_revision=SHA,
        minecraft_spec=MinecraftTestSpec(target_jar=Path("mod.jar"), target_mod_id="examplemod", minecraft_version="1.21.11", loader_version="0.19.3", test_id="vertical-a", timeout_seconds=10, observation_requests=plan.observations),
    )
    assert outcome.status is RuntimeOrchestrationStatus.VALIDATED
    assert outcome.failure_fact is not None
    assert outcome.failure_fact.requirement_ids == ("requirement:item", "requirement:association")
    assert "validation:" not in " ".join(outcome.failure_fact.requirement_ids)
    assert all("block-registry" not in item for item in outcome.failure_fact.requirement_ids)
