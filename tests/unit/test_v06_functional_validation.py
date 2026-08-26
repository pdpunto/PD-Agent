from __future__ import annotations

import pytest

from pd_agent.benchmark.functional import validate_command_result, validate_observation_result
from pd_agent.core import ValidationStatus
from pd_agent.minecraft import (
    CommandResult,
    MinecraftEvidenceKind,
    MinecraftEvidenceReference,
    MinecraftObservationStatus,
    MinecraftObservationType,
    ObservationResult,
)


def _observation(kind: MinecraftObservationType, *, error_code: str | None = None, actual: object = None) -> ObservationResult:
    return ObservationResult(
        observation_id="obs-001",
        observation_type=kind,
        status=MinecraftObservationStatus.FAIL,
        expected={"value": 1},
        actual=actual if actual is not None else {"value": 2},
        phase="PHASE_2",
        evidence_refs=(MinecraftEvidenceReference(kind=MinecraftEvidenceKind.OBSERVATION, ref="phase-2/obs.json"),),
        error={"code": error_code} if error_code else None,
    )


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        (MinecraftObservationType.ITEM_COMPONENT_STATE, "ITEM_COMPONENT_VALUE_MISMATCH"),
        (MinecraftObservationType.BLOCK_ENTITY_STATE, "BLOCK_ENTITY_STATE_MISMATCH"),
        (MinecraftObservationType.INVENTORY_STATE, "INVENTORY_SLOT_MISMATCH"),
        (MinecraftObservationType.TAG_MEMBERSHIP, "TAG_MEMBERSHIP_MISMATCH"),
        (MinecraftObservationType.RECIPE_MATCH, "RECIPE_MATCH_MISMATCH"),
        (MinecraftObservationType.LOOT_RESULT, "LOOT_RESULT_MISMATCH"),
    ],
)
def test_observation_mismatch_codes_are_closed(kind: MinecraftObservationType, expected_code: str) -> None:
    result = validate_observation_result(_observation(kind))
    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert result.violations[0].code == expected_code


def test_observation_special_codes_and_structured_feedback() -> None:
    result = validate_observation_result(_observation(MinecraftObservationType.INVENTORY_STATE, error_code="PERSISTED_STATE_MISMATCH"))
    violation = result.violations[0]
    assert violation.code == "PERSISTED_STATE_MISMATCH"
    assert violation.expected == {"value": 1}
    assert violation.actual == {"value": 2}
    assert violation.phase == "PHASE_2"
    assert violation.evidence_refs == ("phase-2/obs.json",)

    event = validate_observation_result(_observation(MinecraftObservationType.INVENTORY_STATE, error_code="EVENT_SIDE_EFFECT_MISSING"))
    assert event.violations[0].code == "EVENT_SIDE_EFFECT_MISSING"


def test_observation_pass_blocked_invalid_and_contradiction_mapping() -> None:
    passed = ObservationResult(
        observation_id="obs-pass",
        observation_type=MinecraftObservationType.ITEM_COMPONENT_STATE,
        status=MinecraftObservationStatus.PASS,
        expected={"value": 1},
        actual={"value": 1},
    )
    assert validate_observation_result(passed).status is ValidationStatus.PASS
    blocked = _observation(MinecraftObservationType.ITEM_COMPONENT_STATE)
    blocked = ObservationResult.from_dict({**blocked.to_dict(), "status": "BLOCKED"})
    assert validate_observation_result(blocked).status is ValidationStatus.BLOCKED
    invalid = ObservationResult.from_dict({**blocked.to_dict(), "status": "INVALID"})
    assert validate_observation_result(invalid).status is ValidationStatus.INVALID
    contradictory = ObservationResult.from_dict({**passed.to_dict(), "error": {"code": "FAILED"}})
    assert validate_observation_result(contradictory).status is ValidationStatus.INVALID


@pytest.mark.parametrize(
    ("kind", "expected", "actual"),
    [
        (
            MinecraftObservationType.ITEM_COMPONENT_STATE,
            {"component_id": "example:charge", "present": True, "value": 3},
            {"component_id": "example:charge", "present_before": False, "present_after": True, "value_after_mutation": 3, "value_after": 3, "value_restored": True, "round_trip": True},
        ),
        (
            MinecraftObservationType.BLOCK_ENTITY_STATE,
            {"present": True, "type": "minecraft:hopper"},
            {"present": True, "type": "minecraft:hopper", "position": [8, 64, 8], "state": {"facing": "north"}},
        ),
        (
            MinecraftObservationType.INVENTORY_STATE,
            {"size": 5, "slot": 0, "item_id": "minecraft:diamond", "count": 3},
            {"size": 5, "slot": 0, "item_id": "minecraft:diamond", "count": 3, "components": {}, "observed_at": "after-mutation"},
        ),
        (MinecraftObservationType.TAG_MEMBERSHIP, {"member": "minecraft:diamond", "present": True}, {"member": "minecraft:diamond", "present": True, "resolved": True}),
        (MinecraftObservationType.RECIPE_MATCH, {"matched": True, "output_count": 1}, {"matched": True, "output_count": 1, "recipe_type": "minecraft:crafting"}),
        (MinecraftObservationType.LOOT_RESULT, {"item_id": "minecraft:gold_ingot", "count": 1}, {"item_id": "minecraft:gold_ingot", "count": 1, "seed": 424242, "context": "generic"}),
    ],
)
def test_runtime_pass_trusts_primitive_semantics_for_enriched_actual(
    kind: MinecraftObservationType, expected: object, actual: object,
) -> None:
    result = ObservationResult(
        observation_id="obs-pass-enriched",
        observation_type=kind,
        status=MinecraftObservationStatus.PASS,
        expected=expected,
        actual=actual,
    )
    assert validate_observation_result(result).status is ValidationStatus.PASS


def test_inventory_size_mismatch_is_more_specific() -> None:
    result = validate_observation_result(ObservationResult(
        observation_id="inventory-size",
        observation_type=MinecraftObservationType.INVENTORY_STATE,
        status=MinecraftObservationStatus.FAIL,
        expected={"size": 5},
        actual={"size": 2},
    ))
    assert result.violations[0].code == "INVENTORY_SIZE_MISMATCH"


def test_command_status_mapping_distinguishes_functional_invalid_and_blocked() -> None:
    failed = validate_command_result(CommandResult(
        invocation_id="cmd-fail", registered=True, parsed=True, executed=False, return_code=1, success=False,
    ))
    assert failed.status is ValidationStatus.REPAIRABLE_FAIL
    assert failed.violations[0].code == "COMMAND_EXECUTION_FAILED"
    side_effect = validate_command_result(CommandResult(
        invocation_id="cmd-side", registered=True, parsed=True, executed=True, return_code=0, success=True,
    ), side_effect_matches=False)
    assert side_effect.violations[0].code == "COMMAND_SIDE_EFFECT_MISMATCH"
    malformed = validate_command_result(CommandResult(
        invocation_id="cmd-invalid", registered=False, parsed=False, executed=False, return_code=None, success=False,
    ))
    assert malformed.status is ValidationStatus.INVALID
    infrastructure = validate_command_result(CommandResult(
        invocation_id="cmd-blocked", registered=True, parsed=True, executed=False, return_code=None, success=False,
        error={"category": "infrastructure"},
    ))
    assert infrastructure.status is ValidationStatus.BLOCKED
