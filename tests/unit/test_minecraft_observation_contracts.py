from __future__ import annotations

import json

import pytest

from pd_agent.minecraft import (
    MinecraftEvidenceKind,
    MinecraftEvidenceReference,
    MinecraftObservationStatus,
    MinecraftObservationType,
    ObservationRequest,
    ObservationResult,
    MinecraftTestSpec,
    validate_item_component_profile,
    validate_block_entity_profile,
    validate_inventory_profile,
    validate_tag_membership_profile,
    validate_recipe_match_profile,
    validate_loot_result_profile,
)


NEW_TYPES = {
    "ITEM_COMPONENT_STATE",
    "BLOCK_ENTITY_STATE",
    "INVENTORY_STATE",
    "TAG_MEMBERSHIP",
    "RECIPE_MATCH",
    "LOOT_RESULT",
}


def _request() -> ObservationRequest:
    return ObservationRequest(
        observation_id="obs-001",
        observation_type=MinecraftObservationType.ITEM_COMPONENT_STATE,
        profile="controlled_stack",
        selector={"kind": "harness_stack", "id": "target"},
        parameters={"operation": "read"},
        expected={"present": True, "value": {"charge": 3}},
        phase="PHASE_1",
        metadata={"source": "harness"},
    )


def test_observation_types_preserve_legacy_and_declare_v06_types() -> None:
    values = {item.value for item in MinecraftObservationType}
    assert {"LEGACY_BLOCK_STATE", "REGISTRY_ENTRY_PRESENT"} <= values
    assert NEW_TYPES <= values
    assert "COMMAND_EXECUTION" not in values
    assert "EVENT_FIRED" not in values
    assert "PERSISTENCE" not in values


def test_observation_request_round_trip_is_semantically_equal() -> None:
    original = _request()
    restored = ObservationRequest.from_dict(json.loads(original.to_json()))
    assert restored == original


def test_structured_semantic_data_allows_control_named_keys_and_nested_lists() -> None:
    semantic_data = {"path": "semantic-value", "entries": [{"path": "semantic-value"}]}
    request = ObservationRequest(
        observation_id="obs-data",
        observation_type=MinecraftObservationType.ITEM_COMPONENT_STATE,
        profile="controlled_stack",
        selector={"kind": "harness_stack"},
        expected=semantic_data,
    )
    result = ObservationResult(
        observation_id="obs-data",
        observation_type=MinecraftObservationType.ITEM_COMPONENT_STATE,
        status=MinecraftObservationStatus.PASS,
        expected=semantic_data,
        actual={"nbt": {"foo": "bar"}, "entries": [{"path": "semantic-value"}]},
        error={"path": "semantic-error", "code": "DATA_MISMATCH"},
    )

    assert ObservationRequest.from_dict(json.loads(request.to_json())).expected == semantic_data
    restored = ObservationResult.from_dict(json.loads(result.to_json()))
    assert restored.expected == semantic_data
    assert restored.actual == result.actual
    assert restored.error == result.error


def test_observation_request_rejects_unknown_fields_and_unsafe_payloads() -> None:
    payload = _request().to_dict()
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        ObservationRequest.from_dict(payload)

    with pytest.raises(ValueError, match="prohibited key"):
        ObservationRequest(
            observation_id="obs-002",
            observation_type=MinecraftObservationType.TAG_MEMBERSHIP,
            profile="registry",
            selector={"kind": "tag"},
            parameters={"command": "/op"},
            expected=True,
        )

    for field, value in (("selector", {"path": "outside"}), ("parameters", {"nbt": "raw"}), ("metadata", {"reflection": "x"})):
        kwargs = {
            "observation_id": "obs-control",
            "observation_type": MinecraftObservationType.TAG_MEMBERSHIP,
            "profile": "registry",
            "selector": {"kind": "tag"},
            "expected": True,
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match="prohibited key"):
            ObservationRequest(**kwargs)


def test_structured_semantic_data_rejects_non_json_objects() -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        ObservationRequest(
            observation_id="obs-non-json",
            observation_type=MinecraftObservationType.ITEM_COMPONENT_STATE,
            profile="controlled_stack",
            selector={"kind": "harness_stack"},
            expected={"value": object()},
        )


def test_item_component_profile_is_closed_and_supports_round_trip() -> None:
    validate_item_component_profile(
        {"kind": "harness_stack", "item_id": "minecraft:diamond"},
        {"component_id": "minecraft:damage", "round_trip": True},
    )

    spec = MinecraftTestSpec(
        target_jar="build/libs/target.jar",
        target_mod_id="examplemod",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="i2-item-component",
        timeout_seconds=60,
        observation_type=MinecraftObservationType.ITEM_COMPONENT_STATE,
        observation_params={
            "component_id": "minecraft:damage",
            "item_id": "minecraft:diamond",
            "round_trip": True,
        },
    )
    assert spec.from_dict(spec.to_dict()) == spec


def test_i3_hopper_profiles_are_closed_and_controlled() -> None:
    selector = {"kind": "harness_block_entity", "fixture": "hopper", "pos": [8, 64, 8]}
    validate_block_entity_profile(selector, {"block_entity_id": "minecraft:hopper", "mutation": True})
    validate_inventory_profile(
        {"kind": "harness_inventory", "fixture": "hopper", "pos": [8, 64, 8]},
        {"slot": 0, "item_id": "minecraft:diamond", "count": 5, "mutation": True},
    )


def test_i4_tag_membership_profile_is_closed() -> None:
    validate_tag_membership_profile(
        {
            "registry_kind": "item",
            "tag_id": "pdagentl11_harness:i4_controlled_members",
            "member_id": "minecraft:diamond",
        },
        {"expected_membership": True},
    )


@pytest.mark.parametrize(
    "selector, parameters",
    [
        ({"registry_kind": "block", "tag_id": "pdagentl11_harness:i4_controlled_members", "member_id": "minecraft:diamond"}, {"expected_membership": True}),
        ({"registry_kind": "item", "tag_id": "minecraft:logs", "member_id": "minecraft:oak_log"}, {"expected_membership": True}),
        ({"registry_kind": "item", "tag_id": "pdagentl11_harness:i4_controlled_members", "member_id": "minecraft:stone"}, {"expected_membership": "false"}),
        ({"registry_kind": "item", "tag_id": "pdagentl11_harness:i4_controlled_members", "member_id": "minecraft:diamond", "path": "x"}, {"expected_membership": True}),
        ({"registry_kind": "item", "tag_id": "pdagentl11_harness:i4_controlled_members", "member_id": "minecraft:diamond"}, {"expected_membership": True, "command": "x"}),
    ],
)
def test_i4_tag_membership_profile_rejects_unsafe_or_unsupported_input(selector, parameters) -> None:
    with pytest.raises(ValueError):
        validate_tag_membership_profile(selector, parameters)


@pytest.mark.parametrize(
    "validator, selector, parameters",
    [
        (validate_block_entity_profile, {"kind": "harness_block_entity", "fixture": "hopper", "pos": [9, 64, 8]}, {}),
        (validate_block_entity_profile, {"kind": "harness_block_entity", "fixture": "hopper", "pos": [8, 64, 8]}, {"path": "x"}),
        (validate_block_entity_profile, {"kind": "harness_block_entity", "fixture": "hopper", "pos": [8, 64, 8]}, {"block_entity_id": "minecraft:chest"}),
        (validate_inventory_profile, {"kind": "harness_inventory", "fixture": "hopper", "pos": [8, 64, 8]}, {"slot": -1}),
        (validate_inventory_profile, {"kind": "harness_inventory", "fixture": "hopper", "pos": [8, 64, 8]}, {"slot": 5}),
        (validate_inventory_profile, {"kind": "harness_inventory", "fixture": "hopper", "pos": [8, 64, 8]}, {"slot": 0, "nbt": "raw"}),
        (validate_inventory_profile, {"kind": "harness_inventory", "fixture": "hopper", "pos": [8, 64, 8]}, {"slot": 0, "item_id": "minecraft:stone"}),
    ],
)
def test_i3_profiles_reject_unsafe_or_out_of_fixture_controls(validator, selector, parameters) -> None:
    with pytest.raises(ValueError):
        validator(selector, parameters)


@pytest.mark.parametrize(
    "selector, parameters",
    [
        ({"kind": "harness_stack"}, {"component_id": "minecraft:damage"}),
        ({"kind": "other", "item_id": "minecraft:diamond"}, {"component_id": "minecraft:damage"}),
        ({"kind": "harness_stack", "item_id": "minecraft:diamond"}, {"component_id": "damage"}),
        ({"kind": "harness_stack", "item_id": "minecraft:diamond"}, {"component_id": "minecraft:damage", "path": "x"}),
        ({"kind": "harness_stack", "item_id": "minecraft:diamond"}, {"component_id": "minecraft:damage", "round_trip": "true"}),
    ],
)
def test_item_component_profile_rejects_malformed_control_input(selector, parameters) -> None:
    with pytest.raises(ValueError):
        validate_item_component_profile(selector, parameters)


def test_observation_request_rejects_invalid_identity_profile_and_selector() -> None:
    with pytest.raises(ValueError):
        ObservationRequest(
            observation_id="../outside",
            observation_type=MinecraftObservationType.RECIPE_MATCH,
            profile="crafting",
            selector={"kind": "recipe"},
            expected=True,
        )


def test_recipe_match_profile_accepts_only_controlled_inputs() -> None:
    validate_recipe_match_profile(
        {"kind": "crafting_recipe", "recipe_id": "pdagentl11_harness:i5_marble_lantern"},
        {
            "input_item_id": "minecraft:diamond",
            "input_count": 1,
            "expected_output_item_id": "minecraft:gold_ingot",
            "expected_output_count": 1,
        },
    )


@pytest.mark.parametrize(
    "selector, parameters",
    [
        ({"kind": "crafting_recipe", "recipe_id": "minecraft:missing"}, {}),
        ({"kind": "recipe", "recipe_id": "pdagentl11_harness:i5_marble_lantern"}, {}),
        ({"kind": "crafting_recipe", "recipe_id": "pdagentl11_harness:i5_marble_lantern"}, {"path": "x"}),
        ({"kind": "crafting_recipe", "recipe_id": "pdagentl11_harness:i5_marble_lantern"}, {"input_item_id": "minecraft:stone", "input_count": 1, "expected_output_item_id": "minecraft:gold_ingot", "expected_output_count": 1}),
        ({"kind": "crafting_recipe", "recipe_id": "pdagentl11_harness:i5_marble_lantern"}, {"input_item_id": "minecraft:diamond", "input_count": 2, "expected_output_item_id": "minecraft:gold_ingot", "expected_output_count": 1}),
    ],
)
def test_recipe_match_profile_rejects_uncontrolled_or_malformed_inputs(selector, parameters) -> None:
    with pytest.raises(ValueError):
        validate_recipe_match_profile(selector, parameters)


def test_recipe_match_request_and_result_round_trip() -> None:
    request = ObservationRequest(
        observation_id="recipe-001",
        observation_type=MinecraftObservationType.RECIPE_MATCH,
        profile="crafting",
        selector={"kind": "crafting_recipe", "recipe_id": "pdagentl11_harness:i5_marble_lantern"},
        parameters={"input_item_id": "minecraft:diamond", "input_count": 1, "expected_output_item_id": "minecraft:gold_ingot", "expected_output_count": 1},
        expected={"matched": True, "output_item_id": "minecraft:gold_ingot", "output_count": 1},
    )
    assert ObservationRequest.from_dict(json.loads(request.to_json())) == request
    result = ObservationResult(
        observation_id="recipe-001",
        observation_type=MinecraftObservationType.RECIPE_MATCH,
        status=MinecraftObservationStatus.PASS,
        expected={"path": "semantic data", "output_count": 1},
        actual={"path": "semantic data", "output_count": 1},
    )
    assert ObservationResult.from_dict(json.loads(result.to_json())) == result


def test_loot_result_profile_accepts_bounded_generic_context() -> None:
    validate_loot_result_profile(
        {"kind": "loot_table", "loot_table_id": "pdagentl11_harness:i6_fixed_drop"},
        {"context_profile": "generic", "seed": 0, "expected_item_id": "minecraft:gold_ingot", "expected_count": 1},
    )


@pytest.mark.parametrize(
    "selector, parameters",
    [
        ({"kind": "loot_table", "loot_table_id": "minecraft:missing"}, {"context_profile": "generic", "seed": 0, "expected_item_id": "minecraft:gold_ingot", "expected_count": 1}),
        ({"kind": "loot_table", "loot_table_id": "pdagentl11_harness:i6_fixed_drop"}, {"context_profile": "arbitrary", "seed": 0, "expected_item_id": "minecraft:gold_ingot", "expected_count": 1}),
        ({"kind": "loot_table", "loot_table_id": "pdagentl11_harness:i6_fixed_drop"}, {"context_profile": "generic", "seed": True, "expected_item_id": "minecraft:gold_ingot", "expected_count": 1}),
        ({"kind": "loot_table", "loot_table_id": "pdagentl11_harness:i6_fixed_drop"}, {"context_profile": "generic", "seed": 0, "expected_item_id": "../secret", "expected_count": 1}),
        ({"kind": "loot_table", "loot_table_id": "pdagentl11_harness:i6_fixed_drop"}, {"context_profile": "generic", "seed": 0, "expected_item_id": "minecraft:gold_ingot", "expected_count": 65}),
        ({"kind": "loot_table", "loot_table_id": "pdagentl11_harness:i6_fixed_drop"}, {"context_profile": "generic", "seed": 0, "expected_item_id": "minecraft:gold_ingot", "expected_count": 1, "path": "x"}),
    ],
)
def test_loot_result_profile_rejects_uncontrolled_inputs(selector, parameters) -> None:
    with pytest.raises(ValueError):
        validate_loot_result_profile(selector, parameters)
    with pytest.raises(ValueError):
        ObservationRequest(
            observation_id="obs-003",
            observation_type=MinecraftObservationType.RECIPE_MATCH,
            profile="not a profile",
            selector={"kind": "recipe"},
            expected=True,
        )
    with pytest.raises(ValueError):
        ObservationRequest(
            observation_id="obs-004",
            observation_type=MinecraftObservationType.RECIPE_MATCH,
            profile="crafting",
            selector={},
            expected=True,
        )


def test_observation_result_round_trip_preserves_status_and_evidence() -> None:
    reference = MinecraftEvidenceReference(
        kind=MinecraftEvidenceKind.OBSERVATION,
        ref="runtime/phase-1/observation.json",
        phase="PHASE_1",
        process_id="process-001",
    )
    original = ObservationResult(
        observation_id="obs-001",
        observation_type=MinecraftObservationType.ITEM_COMPONENT_STATE,
        status=MinecraftObservationStatus.PASS,
        expected={"value": 3},
        actual={"value": 3},
        phase="PHASE_1",
        evidence_refs=(reference,),
    )
    restored = ObservationResult.from_dict(json.loads(original.to_json()))
    assert restored == original


@pytest.mark.parametrize("status", list(MinecraftObservationStatus))
def test_observation_result_supports_closed_statuses(status: MinecraftObservationStatus) -> None:
    result = ObservationResult(
        observation_id="obs-status",
        observation_type=MinecraftObservationType.LOOT_RESULT,
        status=status,
        expected={"items": []},
        error={"code": "NOT_AVAILABLE"} if status is MinecraftObservationStatus.BLOCKED else None,
    )
    assert result.status is status


def test_observation_result_rejects_unknown_status_and_evidence_traversal() -> None:
    payload = {
        "observation_id": "obs-005",
        "observation_type": "TAG_MEMBERSHIP",
        "status": "UNKNOWN",
        "expected": True,
    }
    with pytest.raises(ValueError):
        ObservationResult.from_dict(payload)

    with pytest.raises(ValueError, match="confined"):
        MinecraftEvidenceReference(kind="observation", ref="../secret.json")


def test_legacy_types_remain_usable_without_v06_fields() -> None:
    assert MinecraftObservationType("LEGACY_BLOCK_STATE") is MinecraftObservationType.LEGACY_BLOCK_STATE
    assert MinecraftObservationType("REGISTRY_ENTRY_PRESENT") is MinecraftObservationType.REGISTRY_ENTRY_PRESENT
