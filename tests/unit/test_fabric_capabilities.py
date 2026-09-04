from __future__ import annotations

import math
from pathlib import Path

import pytest

from pd_agent.fabric.capabilities import (
    CapabilityCandidate,
    CapabilityDefinition,
    CapabilityInstance,
    CapabilityModelError,
    CapabilityRecipeIngredient,
    DeclarativeCapabilityReference,
    PlanningFailure,
    VanillaRecipeIngredient,
    canonical_capability_json,
    derive_capability_output_id,
)
from pd_agent.fabric.registry import (
    FOUNDATION_DEFINITIONS,
    CapabilityRegistry,
    DuplicateCapabilityError,
    UnsupportedCapabilityError,
    foundation_capability_registry,
)


def _definition(**overrides: object) -> CapabilityDefinition:
    values: dict[str, object] = {
        "definition_id": "fabric.server-core",
        "parameter_schema": {"namespace": {"type": "string"}},
        "parameter_defaults": {"namespace": "examplemod"},
        "prerequisites": ({"id": "fabric.base"},),
        "requirements": ({"kind": "source", "id": "block"},),
        "validations": ({"kind": "artifact", "id": "jar"},),
        "mutation_expectations": ({"path": "src/main/java/Main.java"},),
    }
    values.update(overrides)
    return CapabilityDefinition(**values)


def test_valid_definition_and_instance_are_data_only() -> None:
    definition = _definition()
    instance = CapabilityInstance(definition_id=definition.definition_id, parameters={"namespace": "examplemod"})
    assert definition.identity
    assert instance.identity
    assert "provider" not in instance.to_dict()
    assert "runtime" not in instance.to_dict()


def test_mapping_and_nested_mapping_order_are_deterministic() -> None:
    first = CapabilityInstance(definition_id="fabric.demo", parameters={"z": {"b": 2, "a": 1}, "a": 1})
    second = CapabilityInstance(definition_id="fabric.demo", parameters={"a": 1, "z": {"a": 1, "b": 2}})
    assert first.parameters == second.parameters
    assert first.identity == second.identity
    assert canonical_capability_json(first.parameters) == canonical_capability_json(second.parameters)


def test_semantic_parameter_change_changes_identity() -> None:
    first = CapabilityInstance(definition_id="fabric.demo", parameters={"count": 1})
    changed = CapabilityInstance(definition_id="fabric.demo", parameters={"count": 2})
    assert first.identity != changed.identity


@pytest.mark.parametrize("value", [Path("not-data"), object(), lambda: None])
def test_unsupported_parameter_types_are_rejected(value: object) -> None:
    with pytest.raises(CapabilityModelError):
        CapabilityInstance(definition_id="fabric.demo", parameters={"value": value})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(CapabilityModelError):
        CapabilityInstance(definition_id="fabric.demo", parameters={"value": value})


def test_malformed_definition_and_schema_version_are_rejected() -> None:
    with pytest.raises(CapabilityModelError):
        CapabilityDefinition(definition_id="Not Valid")
    with pytest.raises(CapabilityModelError):
        _definition(schema_version=2)
    with pytest.raises(CapabilityModelError):
        CapabilityInstance(definition_id="fabric.demo", definition_schema_version=2)


@pytest.mark.parametrize(
    "value",
    ["x" * 4097, {"x": [None] * 65}, {"command": "should-not-be-data"}],
)
def test_bounded_data_and_unsafe_declarations_are_rejected(value: object) -> None:
    with pytest.raises(CapabilityModelError):
        CapabilityInstance(definition_id="fabric.demo", parameters={"value": value})


def test_candidate_and_planning_failure_are_serializable_data() -> None:
    candidate = CapabilityCandidate(definition_id="fabric.demo", parameters={"enabled": True})
    failure = PlanningFailure(code="INVALID_CANDIDATE", message="candidate rejected", details={"field": "x"})
    assert candidate.to_dict() == {"definition_id": "fabric.demo", "parameters": {"enabled": True}}
    assert failure.to_dict()["code"] == "INVALID_CANDIDATE"


def test_declaration_keys_and_references_are_bounded_and_serializable() -> None:
    reference = DeclarativeCapabilityReference(capability_id="fabric.item", declaration_key="item-a")
    candidate = CapabilityCandidate(definition_id="fabric.item", declaration_key="item-b", references=(reference,))
    assert candidate.to_dict()["declaration_key"] == "item-b"
    assert candidate.to_dict()["references"] == [reference.to_dict()]
    with pytest.raises(CapabilityModelError):
        CapabilityCandidate(definition_id="fabric.item", declaration_key="Not Safe")


def test_foundation_registry_contains_only_generic_capabilities() -> None:
    registry = foundation_capability_registry()
    assert registry.definition_ids == ("fabric.block", "fabric.block_assets", "fabric.block_item", "fabric.item", "fabric.item_assets", "fabric.recipe")
    assert all("server" not in item.definition_id for item in registry.definitions())
    assert all("provider" not in item.to_dict() for item in registry.definitions())


def test_registry_rejects_duplicates_unknown_ids_and_mutation_after_freeze() -> None:
    registry = CapabilityRegistry().register(FOUNDATION_DEFINITIONS[0])
    with pytest.raises(DuplicateCapabilityError):
        registry.register(FOUNDATION_DEFINITIONS[0])
    with pytest.raises(UnsupportedCapabilityError):
        registry.get("fabric.unknown")
    registry.freeze()
    with pytest.raises(CapabilityModelError):
        registry.register(FOUNDATION_DEFINITIONS[1])


def test_prerequisites_are_data_only_and_registry_does_not_resolve_them() -> None:
    registry = foundation_capability_registry()
    assert registry.get("fabric.block_item").prerequisites
    assert registry.get("fabric.recipe").prerequisites
    assert not hasattr(registry, "resolve")


def test_derived_output_ids_are_stable_and_local_key_sensitive() -> None:
    instance = CapabilityInstance(definition_id="fabric.block", parameters={"name": "core", "namespace": "example"})
    same = CapabilityInstance(definition_id="fabric.block", parameters={"namespace": "example", "name": "core"})
    assert derive_capability_output_id(instance, "source") == derive_capability_output_id(same, "source")
    assert derive_capability_output_id(instance, "source") != derive_capability_output_id(instance, "resource")


def test_b2_recipe_ingredient_helpers_are_bounded_and_serializable() -> None:
    vanilla = VanillaRecipeIngredient(item_id="minecraft:iron_ingot", quantity=2)
    own = CapabilityRecipeIngredient(capability_id="fabric.item", declaration_key="item-a", quantity=1)
    assert vanilla.to_dict() == {"kind": "vanilla", "item_id": "minecraft:iron_ingot", "quantity": 2}
    assert own.to_dict()["kind"] == "capability"
    with pytest.raises(CapabilityModelError):
        VanillaRecipeIngredient(item_id="minecraft:iron_ingot", quantity=0)
    with pytest.raises(CapabilityModelError):
        VanillaRecipeIngredient(item_id="minecraft:iron_ingot", quantity=65)
