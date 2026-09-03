from __future__ import annotations

from pd_agent.fabric.capabilities import CapabilityCandidate, CapabilityDefinition, CapabilityInstance
from pd_agent.core.contracts import FabricEnvironmentConstraints
from pd_agent.fabric.planning import CapabilityPlanner, FabricContractContext, expand_plan_to_contract
from pd_agent.fabric.registry import CapabilityRegistry, FOUNDATION_DEFINITIONS, foundation_capability_registry


def _foundation_candidates() -> tuple[CapabilityCandidate, ...]:
    block = CapabilityInstance(definition_id="fabric.block", parameters={"namespace": "examplemod", "name": "core"})
    item = CapabilityInstance(definition_id="fabric.block_item", parameters={"block_instance_id": block.identity, "namespace": "examplemod"})
    return (
        CapabilityCandidate(definition_id="fabric.block", parameters={"name": "core", "namespace": "examplemod"}),
        CapabilityCandidate(definition_id="fabric.block_item", parameters={"namespace": "examplemod", "block_instance_id": block.identity}),
        CapabilityCandidate(definition_id="fabric.recipe", parameters={"ingredients": [{"item": "minecraft:iron"}], "output_instance_id": item.identity}),
    )


def test_empty_and_unsupported_inputs_fail_structurally() -> None:
    planner = CapabilityPlanner(foundation_capability_registry())
    assert planner.plan([]).success
    assert planner.plan(["not-a-candidate"]).failure.code == "INVALID_PARAMETERS"
    assert planner.plan([CapabilityCandidate(definition_id="fabric.unknown")]).failure.code == "UNSUPPORTED_CAPABILITY"


def test_block_alone_and_defaults_plan() -> None:
    definition = CapabilityDefinition(
        definition_id="test.default",
        parameter_schema={"name": {"type": "string"}},
        parameter_defaults={"name": "default"},
    )
    result = CapabilityPlanner(CapabilityRegistry([definition]).freeze()).plan([CapabilityCandidate(definition_id="test.default")])
    assert result.success
    assert result.instances[0].parameters["name"] == "default"


def test_block_item_dependency_and_full_foundation_composition() -> None:
    result = CapabilityPlanner(foundation_capability_registry()).plan(_foundation_candidates())
    assert result.success
    assert tuple(item.definition_id for item in result.instances) == ("fabric.block", "fabric.block_item", "fabric.recipe")
    assert len(result.instances) == 3
    assert len(result.dependency_edges) == 2


def test_equivalent_candidates_deduplicate_and_permutation_is_stable() -> None:
    candidates = _foundation_candidates()
    first = CapabilityPlanner(foundation_capability_registry()).plan(candidates + (candidates[0],))
    second = CapabilityPlanner(foundation_capability_registry()).plan(tuple(reversed(candidates)))
    assert first.success and second.success
    assert len(first.instances) == 3
    assert first.plan_fingerprint == second.plan_fingerprint
    assert first.dependency_edges == second.dependency_edges


def test_semantic_change_and_missing_reference_fail() -> None:
    planner = CapabilityPlanner(foundation_capability_registry())
    changed = CapabilityCandidate(definition_id="fabric.block", parameters={"namespace": "examplemod", "name": "changed"})
    assert planner.plan([changed]).instances[0].identity != planner.plan(_foundation_candidates()).instances[0].identity
    missing = CapabilityCandidate(definition_id="fabric.block_item", parameters={"namespace": "examplemod", "block_instance_id": "missing"})
    assert planner.plan([missing]).failure.code == "UNRESOLVED_PREREQUISITE"


def test_cycle_detection_uses_unique_capability_references() -> None:
    a = CapabilityDefinition(definition_id="test.a", prerequisites=({"capability": "test.b"},))
    b = CapabilityDefinition(definition_id="test.b", prerequisites=({"capability": "test.a"},))
    result = CapabilityPlanner(CapabilityRegistry([a, b]).freeze()).plan(
        [CapabilityCandidate(definition_id="test.a"), CapabilityCandidate(definition_id="test.b")]
    )
    assert result.failure is not None
    assert result.failure.code == "DEPENDENCY_CYCLE"


def test_planning_result_is_data_only_and_has_no_execution_authority() -> None:
    result = CapabilityPlanner(foundation_capability_registry()).plan([])
    assert result.to_dict()["success"] is True
    assert not hasattr(result, "execute")
    assert not hasattr(result, "provider")


def test_composed_plan_expands_to_correlated_fabric_contract() -> None:
    planner = CapabilityPlanner(foundation_capability_registry())
    plan = planner.plan(_foundation_candidates())
    expansion = expand_plan_to_contract(
        plan,
        foundation_capability_registry(),
        FabricContractContext(task_id="task-1", revision="m1", goal="compose a block capability"),
    )
    assert expansion.success
    assert expansion.contract is not None
    assert len(expansion.contract.requirements) == 6
    assert len(expansion.contract.validation_requirements) == 2
    requirement_ids = {item.requirement_id for item in expansion.contract.requirements}
    assert all(set(item.requirement_ids).issubset(requirement_ids) for item in expansion.contract.validation_requirements)
    assert all(expansion.requirements_for(instance.identity) for instance in plan.instances)
    assert expansion.validations_for(plan.instances[0].identity)
    assert expansion.validations_for(plan.instances[1].identity)
    assert not expansion.validations_for(plan.instances[2].identity)
    assert expansion.contract.fingerprint == expansion.contract.from_dict(expansion.contract.to_dict()).fingerprint


def test_contract_expansion_is_stable_under_candidate_permutation() -> None:
    candidates = _foundation_candidates()
    registry = foundation_capability_registry()
    context = FabricContractContext(task_id="task-1", revision="m1", goal="compose a block capability")
    first = expand_plan_to_contract(CapabilityPlanner(registry).plan(candidates), registry, context)
    second = expand_plan_to_contract(CapabilityPlanner(registry).plan(tuple(reversed(candidates))), registry, context)
    assert first.success and second.success
    assert first.contract is not None and second.contract is not None
    assert first.contract.fingerprint == second.contract.fingerprint
    assert first.capability_requirement_ids == second.capability_requirement_ids


def test_unsupported_validation_fails_before_contract_generation() -> None:
    definition = CapabilityDefinition(
        definition_id="test.unsupported",
        parameter_schema={"name": {"type": "string"}},
        requirements=({"key": "source", "description": "source exists"},),
        validations=({"key": "visual", "kind": "screenshot", "requirement_keys": ("source",)},),
    )
    registry = CapabilityRegistry([definition]).freeze()
    plan = CapabilityPlanner(registry).plan([CapabilityCandidate(definition_id="test.unsupported", parameters={"name": "x"})])
    expansion = expand_plan_to_contract(plan, registry, FabricContractContext(task_id="t", revision="1", goal="test"))
    assert expansion.failure is not None
    assert expansion.failure.code == "UNSUPPORTED_VALIDATION"


def test_invalid_generated_contract_is_structured() -> None:
    registry = foundation_capability_registry()
    failure = expand_plan_to_contract(
        CapabilityPlanner(registry).plan(_foundation_candidates()),
        registry,
        FabricContractContext(task_id="", revision="1", goal="test", environment_constraints=FabricEnvironmentConstraints()),
    )
    assert failure.failure is not None
    assert failure.failure.code == "INVALID_GENERATED_CONTRACT"
