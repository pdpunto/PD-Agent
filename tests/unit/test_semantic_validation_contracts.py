from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pd_agent.benchmark import (
    BenchmarkAcceptanceSpec,
    PublicJsonPointerAssertion,
    PublicValidationContract,
    build_public_validation_contract,
)
from pd_agent.core import (
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    ValidationViolation,
)


TASK_ROOT = Path(__file__).parents[2] / "benchmarks" / "tasks"


def _public_contract(task_id: str) -> PublicValidationContract:
    payload = json.loads((TASK_ROOT / f"{task_id}-v5.json").read_text(encoding="utf-8"))
    acceptance = BenchmarkAcceptanceSpec.from_dict(payload["acceptance"])
    return build_public_validation_contract(acceptance)


def _assert_no_forbidden_keys(value: object) -> None:
    forbidden = {
        "knowledge_needs",
        "hints",
        "reference",
        "solution",
        "scoring",
        "notes",
        "test_id",
        "evidence_requirements",
        "project_base_ref",
        "resource_contract",
    }
    if isinstance(value, dict):
        assert not forbidden.intersection(value)
        for item in value.values():
            _assert_no_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_keys(item)


def test_validation_enums_are_stable() -> None:
    assert [item.value for item in ValidationStage] == ["PRE_BUILD", "POST_ARTIFACT", "RUNTIME"]
    assert [item.value for item in ValidationStatus] == ["PASS", "REPAIRABLE_FAIL", "BLOCKED"]


def test_validation_violation_and_result_round_trip() -> None:
    violation = ValidationViolation(
        code="RESOURCE_JSON_POINTER_MISSING",
        requirement="/item.examplemod.server_core",
        observed={"present": False, "path": "assets/examplemod/lang/en_us.json"},
        message="required value is missing",
        evidence_refs=("evidence/resource.json",),
    )
    result = ValidationResult(
        stage=ValidationStage.PRE_BUILD,
        status=ValidationStatus.REPAIRABLE_FAIL,
        summary="one public requirement failed",
        violations=(violation,),
        evidence_refs=("evidence/resource.json",),
    )

    assert ValidationViolation.from_dict(violation.to_dict()) == violation
    assert ValidationResult.from_dict(result.to_dict()) == result
    with pytest.raises(FrozenInstanceError):
        violation.code = "changed"  # type: ignore[misc]


def test_validation_payload_is_deterministic() -> None:
    result = ValidationResult(
        stage="RUNTIME",
        status="PASS",
        summary="all requirements passed",
        violations=(),
        evidence_refs=("evidence/runtime.json",),
    )
    first = json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":"))
    second = json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":"))
    assert first == second


def test_public_contract_t1() -> None:
    contract = _public_contract("F6-T1")
    assert contract.to_dict() == {
        "schema_version": 1,
        "registry_observations": [
            {"registry_kind": "item", "identifier": "examplemod:signal_charm"}
        ],
        "required_minecraft_observations": [],
        "required_resources": [],
        "preservation": {
            "mod_id": "examplemod",
            "preserve_entrypoints": True,
            "preserve_unrelated_sources": True,
        },
    }


def test_public_contract_t2() -> None:
    contract = _public_contract("F6-T2")
    assert contract.registry_observations[0].to_dict() == {
        "registry_kind": "block",
        "identifier": "examplemod:marble_lantern",
    }
    assert contract.required_minecraft_observations[0].to_dict() == {
        "registry_kind": "item",
        "identifier": "examplemod:marble_lantern",
    }
    assert contract.required_resources[0].to_dict() == {
        "path": "assets/examplemod/lang/en_us.json",
        "resource_type": "json",
        "assertions": [
            {
                "kind": "json_pointer_equals",
                "path": "/block.examplemod.marble_lantern",
                "value": "Marble Lantern",
            },
            {
                "kind": "json_pointer_equals",
                "path": "/item.examplemod.marble_lantern",
                "value": "Marble Lantern",
            },
        ],
    }


def test_public_contract_t3() -> None:
    contract = _public_contract("F6-T3")
    assert contract.registry_observations[0].identifier == "examplemod:server_core"
    assert contract.required_minecraft_observations[0].identifier == "examplemod:server_core"
    assert [resource.path for resource in contract.required_resources] == [
        "assets/examplemod/lang/en_us.json",
        "data/examplemod/recipe/server_core.json",
    ]
    assert contract.required_resources[1].assertions[0].to_dict() == {
        "kind": "json_pointer_equals",
        "path": "/result/id",
        "value": "examplemod:server_core",
    }
    assert contract.required_resources[1].assertions[1].to_dict() == {
        "kind": "json_pointer_equals",
        "path": "/result/count",
        "value": 1,
    }


def test_public_json_pointer_presence_and_equality_round_trip() -> None:
    present = PublicJsonPointerAssertion(kind="json_pointer_present", path="/item.examplemod.signal_charm")
    equal = PublicJsonPointerAssertion(
        kind="json_pointer_equals",
        path="/item.examplemod.signal_charm",
        value="Signal Charm",
    )
    assert present.to_dict() == {
        "kind": "json_pointer_present",
        "path": "/item.examplemod.signal_charm",
    }
    assert PublicJsonPointerAssertion.from_dict(equal.to_dict()) == equal


def test_public_contract_excludes_hidden_and_benchmark_only_fields() -> None:
    for task_id in ("F6-T1", "F6-T2", "F6-T3"):
        payload = _public_contract(task_id).to_dict()
        _assert_no_forbidden_keys(payload)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for forbidden in ("knowledge_needs", "hints", "reference", "solution", "scoring"):
            assert forbidden not in encoded


def test_public_contract_round_trip_is_stable() -> None:
    contract = _public_contract("F6-T3")
    restored = PublicValidationContract.from_dict(contract.to_dict())
    assert restored == contract
    assert restored.to_dict() == contract.to_dict()


def test_malformed_acceptance_fails_closed() -> None:
    acceptance = BenchmarkAcceptanceSpec(
        acceptance_type="fabric_feature",
        spec={
            "observation_type": "REGISTRY_ENTRY_PRESENT",
            "observation_params": {"registry_kind": "block", "identifier": "examplemod:x"},
            "required_resources": [{"path": "../outside.json", "type": "json", "assertions": []}],
        },
    )
    with pytest.raises(ValueError, match="relative repository path"):
        build_public_validation_contract(acceptance)


def test_adapter_has_no_provider_or_brain_dependency() -> None:
    source = (Path(__file__).parents[2] / "src" / "pd_agent" / "benchmark" / "public_validation.py").read_text(
        encoding="utf-8"
    )
    assert "pd_agent.providers" not in source
    assert "pd_agent.brain" not in source
