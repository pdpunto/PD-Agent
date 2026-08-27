from __future__ import annotations

import json

import pytest

from pd_agent.core import (
    FabricEnvironmentConstraints,
    FabricKnowledgeSignal,
    FabricMutationExpectation,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    RunState,
)


def _contract(*, revision: str = "1", goal: str = "Implement the Fabric feature") -> FabricTaskContract:
    requirement = FabricRequirement(requirement_id="r1", description="The feature exists")
    return FabricTaskContract(
        task_id="fabric.demo",
        revision=revision,
        goal=goal,
        requirements=(requirement,),
        required_capabilities=("data_components",),
        completion_criteria=("required validations pass",),
        validation_requirements=(
            FabricValidationRequirement(
                validation_requirement_id="v1",
                requirement_ids=("r1",),
                kind="build",
                spec={"command_name": "compileJava"},
            ),
        ),
        knowledge_signals=(FabricKnowledgeSignal(signal_id="k1", query="Fabric component API"),),
        mutation_expectations=(FabricMutationExpectation(expectation_id="m1", role="source", path="src/main/java/Example.java"),),
        environment_constraints=FabricEnvironmentConstraints(
            minecraft_version="1.21.11",
            loader_version="0.19.3",
            fabric_api_version="0.141.6+1.21.11",
            yarn_version="1.21.11+build.6",
            java_version="21",
        ),
    )


def test_valid_contract_creation_and_fields() -> None:
    contract = _contract()
    assert contract.schema_version == 1
    assert contract.identity() == ("fabric.demo", "1", contract.fingerprint)
    assert contract.environment_constraints.minecraft_version == "1.21.11"


def test_serialization_and_fingerprint_are_deterministic() -> None:
    first = _contract()
    second = _contract()
    assert first.canonical_json() == second.canonical_json()
    assert first.fingerprint == second.fingerprint
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True)


def test_material_change_and_revision_change_identity() -> None:
    assert _contract().fingerprint != _contract(goal="Different goal").fingerprint
    assert _contract().fingerprint != _contract(revision="2").fingerprint


def test_roundtrip_preserves_identity() -> None:
    original = _contract()
    reopened = FabricTaskContract.from_dict(original.to_dict())
    assert reopened == original
    assert reopened.identity() == original.identity()


def test_contract_is_immutable() -> None:
    with pytest.raises((AttributeError, TypeError)):
        _contract().goal = "changed"  # type: ignore[misc]


def test_duplicate_requirement_validation_and_dangling_links_rejected() -> None:
    requirement = FabricRequirement(requirement_id="r1", description="one")
    with pytest.raises(ValueError, match="duplicate requirement"):
        FabricTaskContract(task_id="x", revision="1", goal="goal", requirements=(requirement, requirement))
    with pytest.raises(ValueError, match="unknown requirement"):
        FabricTaskContract(
            task_id="x",
            revision="1",
            goal="goal",
            requirements=(requirement,),
            validation_requirements=(
                FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=("missing",), kind="build"),
            ),
        )
    with pytest.raises(ValueError, match="duplicate IDs"):
        FabricTaskContract(
            task_id="x",
            revision="1",
            goal="goal",
            requirements=(requirement,),
            validation_requirements=(
                FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=("r1",), kind="build"),
                FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=("r1",), kind="artifact"),
            ),
        )


def test_unsafe_control_payloads_and_non_json_values_rejected() -> None:
    with pytest.raises(ValueError, match="control key"):
        FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=(), kind="build", spec={"shell": "gradle"})
    with pytest.raises(ValueError, match="JSON-compatible"):
        FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=(), kind="build", spec={"value": object()})
    with pytest.raises(ValueError, match="relative"):
        FabricMutationExpectation(expectation_id="m1", role="source", path="../outside.java")


def test_environment_and_optional_required_semantics() -> None:
    assert FabricRequirement(requirement_id="optional", description="optional", required=False).required is False
    assert FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=(), kind="runtime", required=False).required is False
    with pytest.raises(ValueError, match="platform"):
        FabricEnvironmentConstraints(platform="neoforge")


def test_benchmark_isolation_and_legacy_run_state_unchanged() -> None:
    import pd_agent.core.contracts as contracts

    assert not any(name.startswith("pd_agent.benchmark") for name in contracts.__dict__)
    state = RunState(task="legacy")
    payload = state.to_dict()
    assert RunState.from_dict(payload).task == "legacy"
