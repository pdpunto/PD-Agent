from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.core import ArtifactIdentity, FabricRequirement, FabricTaskContract, RunState
from pd_agent.minecraft import (
    FabricRuntimeOrchestrator,
    MinecraftObservationStatus,
    MinecraftObservationType,
    ObservationRequest,
    ObservationResult,
    RuntimeValidationSpec,
    runtime_spec_from_requirement,
)
from pd_agent.product import ProductFabricTaskContractResolver
from tests.unit.test_product_fabric_execution import _records, _vertical_b_payload, _vertical_b_task


def test_vertical_b_contract_has_one_runtime_requirement_and_one_probe_per_item(tmp_path: Path) -> None:
    project, _task, snapshot = _records(tmp_path)
    contract = ProductFabricTaskContractResolver().resolve(
        project, _vertical_b_task(project, _vertical_b_payload(two_items=True)), snapshot
    )

    runtime = [item for item in contract.validation_requirements if item.kind == "minecraft"]
    assert len(runtime) == 1
    observations = runtime[0].spec["observations"]
    item_observations = [item for item in observations if item["observation_type"] == "REGISTRY_ENTRY_PRESENT"]
    assert [item["selector"]["identifier"] for item in item_observations] == [
        "examplemod:ruby_core", "examplemod:ruby_shard"
    ]
    assert all(item["selector"]["registry_kind"] == "item" for item in item_observations)
    assert len([item for item in observations if item["observation_type"] == "RECIPE_LOADED"]) == 1
    assert all(
        item["requirement_ids"]
        and all(value.startswith("requirement:") for value in item["requirement_ids"])
        for item in item_observations
    )
    assert "RECIPE_MATCH" not in json.dumps(runtime[0].spec)


def test_vertical_b_runtime_observation_order_is_independent_of_input_order(tmp_path: Path) -> None:
    project, _task, snapshot = _records(tmp_path)
    payload = _vertical_b_payload(two_items=True)
    first = ProductFabricTaskContractResolver().resolve(project, _vertical_b_task(project, payload), snapshot)
    reversed_payload = {"items": list(reversed(payload["items"])), "recipes": list(reversed(payload["recipes"]))}
    second = ProductFabricTaskContractResolver().resolve(project, _vertical_b_task(project, reversed_payload), snapshot)
    first_obs = next(item for item in first.validation_requirements if item.kind == "minecraft").spec["observations"]
    second_obs = next(item for item in second.validation_requirements if item.kind == "minecraft").spec["observations"]
    assert [(item["observation_id"], item["selector"]) for item in first_obs] == [(item["observation_id"], item["selector"]) for item in second_obs]


def _runtime_plan() -> RuntimeValidationSpec:
    requests = tuple(
        ObservationRequest(
            observation_id=f"item-{item}",
            observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
            profile="registry_entry",
            selector={"kind": "registry", "registry_kind": "item", "identifier": f"demo:{item}"},
            expected={"present": True},
        )
        for item in ("a", "b")
    )
    return RuntimeValidationSpec(
        validation_requirement_id="validation:items",
        validation_revision="revision",
        observations=requests,
        observation_requirements={"item-a": ("requirement:item-a",), "item-b": ("requirement:item-b",)},
    )


def test_runtime_aggregation_requires_all_item_observations() -> None:
    plan = _runtime_plan()
    runner = FabricRuntimeOrchestrator(SimpleNamespace())
    passing = tuple(
        ObservationResult(
            observation_id=item.observation_id,
            observation_type=item.observation_type,
            status=MinecraftObservationStatus.PASS,
            expected=item.expected,
            actual={"present": True},
        )
        for item in plan.observations
    )
    one_failed = (passing[0], ObservationResult(
        observation_id="item-b",
        observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        status=MinecraftObservationStatus.FAIL,
        expected={"present": True},
        actual={"present": False},
    ))
    artifact = SimpleNamespace(artifact_identity="artifact")
    failed, failure = runner._validate_observations(plan, one_failed, SimpleNamespace(status="PASS"), artifact, "run-1")
    assert failed.status.value == "REPAIRABLE_FAIL"
    assert failure is not None and failure.requirement_ids == ("requirement:item-b",)
    passed, no_failure = runner._validate_observations(plan, passing, SimpleNamespace(status="PASS"), artifact, "run-2")
    assert passed.status.value == "PASS"
    assert no_failure is None


def test_runtime_plan_rejects_duplicate_observation_ids() -> None:
    request = ObservationRequest(
        observation_id="same",
        observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        profile="registry_entry",
        selector={"kind": "registry", "registry_kind": "item", "identifier": "demo:a"},
        expected={"present": True},
    )
    with pytest.raises(ValueError, match="observation IDs must be unique"):
        RuntimeValidationSpec(
            validation_requirement_id="validation:items",
            validation_revision="revision",
            observations=(request, request),
            observation_requirements={"same": ("requirement:item-a",)},
        )
