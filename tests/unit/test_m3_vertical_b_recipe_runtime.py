from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.minecraft import (
    FabricRuntimeOrchestrator,
    MinecraftObservationStatus,
    MinecraftObservationType,
    MinecraftTestRunner,
    ObservationRequest,
    ObservationResult,
    RuntimeValidationSpec,
    effective_observation_config,
    runtime_spec_from_requirement,
)
from pd_agent.product import ProductFabricTaskContractResolver
from tests.unit.test_product_fabric_execution import _records, _vertical_b_task


def _two_recipe_payload() -> dict[str, object]:
    return {
        "items": [
            {"declaration_key": "item-a", "item_id": "ruby_shard", "assets": {"texture_strategy": "REUSE"}},
            {"declaration_key": "item-b", "item_id": "ruby_core", "assets": {"texture_strategy": "DERIVE"}},
        ],
        "recipes": [
            {
                "declaration_key": "recipe-cross-item",
                "recipe_id": "ruby_core",
                "output": "item-b",
                "ingredients": [{"kind": "capability", "declaration_key": "item-a"}],
            },
            {
                "declaration_key": "recipe-vanilla",
                "recipe_id": "ruby_shard",
                "output": "item-a",
                "ingredients": [{"kind": "vanilla", "item_id": "minecraft:iron_ingot"}],
            },
        ],
    }


def _contract(tmp_path: Path, payload: dict[str, object]):
    tmp_path.mkdir(parents=True, exist_ok=True)
    project, task, snapshot = _records(tmp_path)
    return ProductFabricTaskContractResolver().resolve(
        project, _vertical_b_task(project, payload), snapshot
    )


def test_b8_adds_recipe_load_to_b7_runtime_requirement_without_recipe_matching(tmp_path: Path) -> None:
    contract = _contract(tmp_path, _two_recipe_payload())
    runtime = [item for item in contract.validation_requirements if item.kind == "minecraft"]
    assert len(runtime) == 1
    observations = runtime[0].spec["observations"]
    recipes = [item for item in observations if item["observation_type"] == "RECIPE_LOADED"]
    assert [(item["observation_id"], item["selector"]) for item in recipes] == [
        ("vertical-b-recipe-loaded-ruby_core", {"kind": "recipe", "recipe_id": "examplemod:ruby_core"}),
        ("vertical-b-recipe-loaded-ruby_shard", {"kind": "recipe", "recipe_id": "examplemod:ruby_shard"}),
    ]
    assert all(item["expected"] == {"loaded": True} for item in recipes)
    assert all(item["requirement_ids"] and all(value.startswith("requirement:") for value in item["requirement_ids"]) for item in recipes)
    assert "RECIPE_MATCH" not in str(runtime[0].spec)


def test_b8_recipe_observation_order_is_deterministic_and_cross_item_is_load_only(tmp_path: Path) -> None:
    payload = _two_recipe_payload()
    first = _contract(tmp_path / "first", payload)
    reversed_payload = {"items": list(reversed(payload["items"])), "recipes": list(reversed(payload["recipes"]))}
    second = _contract(tmp_path / "second", reversed_payload)
    first_runtime = next(item for item in first.validation_requirements if item.kind == "minecraft")
    second_runtime = next(item for item in second.validation_requirements if item.kind == "minecraft")
    assert first_runtime.spec["observations"] == second_runtime.spec["observations"]
    cross = next(item for item in first_runtime.spec["observations"] if item["selector"].get("recipe_id") == "examplemod:ruby_core")
    assert set(cross["selector"]) == {"kind", "recipe_id"}
    assert "ingredient" not in cross and "output" not in cross


def _recipe_plan() -> RuntimeValidationSpec:
    requests = (
        ObservationRequest(
            observation_id="item-a",
            observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
            profile="registry_entry",
            selector={"kind": "registry", "registry_kind": "item", "identifier": "demo:item_a"},
            expected={"present": True},
        ),
        ObservationRequest(
            observation_id="recipe-r",
            observation_type=MinecraftObservationType.RECIPE_LOADED,
            profile="recipe_load",
            selector={"kind": "recipe", "recipe_id": "demo:recipe_r"},
            expected={"loaded": True},
        ),
    )
    return RuntimeValidationSpec(
        validation_requirement_id="validation:vertical-b",
        validation_revision="revision",
        observations=requests,
        observation_requirements={
            "item-a": ("requirement:item-a",),
            "recipe-r": ("requirement:recipe-r",),
        },
    )


def _result(request: ObservationRequest, status: MinecraftObservationStatus) -> ObservationResult:
    actual_key = "loaded" if request.observation_type is MinecraftObservationType.RECIPE_LOADED else "present"
    return ObservationResult(
        observation_id=request.observation_id,
        observation_type=request.observation_type,
        status=status,
        expected=request.expected,
        actual={actual_key: status is MinecraftObservationStatus.PASS},
    )


def test_b8_recipe_failure_prevents_runtime_pass_and_reconciles_to_pass() -> None:
    plan = _recipe_plan()
    runner = FabricRuntimeOrchestrator(SimpleNamespace())
    artifact = SimpleNamespace(artifact_identity="artifact")
    item, recipe = plan.observations
    failed, failure = runner._validate_observations(
        plan,
        (_result(item, MinecraftObservationStatus.PASS), _result(recipe, MinecraftObservationStatus.FAIL)),
        SimpleNamespace(status="PASS"), artifact, "run-fail",
    )
    assert failed.status.value == "REPAIRABLE_FAIL"
    assert failure is not None and failure.requirement_ids == ("requirement:recipe-r",)
    passed, no_failure = runner._validate_observations(
        plan,
        (_result(item, MinecraftObservationStatus.PASS), _result(recipe, MinecraftObservationStatus.PASS)),
        SimpleNamespace(status="PASS"), artifact, "run-pass",
    )
    assert passed.status.value == "PASS"
    assert no_failure is None


def test_b8_recipe_load_is_fail_closed_for_malformed_or_missing_evidence() -> None:
    with pytest.raises(ValueError, match="namespaced identifier"):
        ObservationRequest(
            observation_id="recipe",
            observation_type=MinecraftObservationType.RECIPE_LOADED,
            profile="recipe_load",
            selector={"kind": "recipe", "recipe_id": "not-namespaced"},
            expected={"loaded": True},
        )
    with pytest.raises(ValueError, match="explicit requirement_ids"):
        runtime_spec_from_requirement({
            "validation_requirement_id": "validation:recipe",
            "spec": {
                "observations": [{
                    "observation_id": "recipe",
                    "observation_type": "RECIPE_LOADED",
                    "profile": "recipe_load",
                    "selector": {"kind": "recipe", "recipe_id": "demo:recipe"},
                    "expected": {"loaded": True},
                }],
            },
        })


def test_b8_recipe_loaded_transport_and_result_normalization_are_explicit(tmp_path: Path) -> None:
    request = _recipe_plan().observations[1]
    observation_type, params = effective_observation_config(request)
    assert observation_type is MinecraftObservationType.RECIPE_LOADED
    assert params == {"recipe_id": "demo:recipe_r"}
    runner = MinecraftTestRunner(project_root=tmp_path)
    target = SimpleNamespace(path=tmp_path / "target.jar", sha256="a" * 64, mod_id="demo")
    status, _reason, metadata = runner._classify_runtime(
        process={"timed_out": False, "exit_code": 0},
        harness_result={
            "target_loaded": True,
            "target_origin_resolved": True,
            "target_sha_match": True,
            "server_started": True,
            "shutdown_requested": True,
            "functional_test_result": "PASS",
            "observation_type": "RECIPE_LOADED",
            "observation_expected": {"loaded": True},
            "observation_actual": {"recipe_id": "demo:recipe_r", "loaded": True},
            "reason": "recipe was loaded by RecipeManager",
        },
        latest_log=None,
        launch_mode="pass",
        target=target,
        timeout_seconds=30,
        observation_id=request.observation_id,
    )
    assert status.value == "PASS"
    assert metadata["observation_result"]["observation_type"] == "RECIPE_LOADED"


def test_b8_l11_harness_keeps_recipe_loaded_fields_separate_from_recipe_match() -> None:
    config = Path(__file__).resolve().parents[1] / "fixtures" / "l11_minecraft_harness" / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessConfig.java"
    source = config.read_text(encoding="utf-8")

    assert "observationRecipeId = normalizeRecipeLoadedField(observationType, observationRecipeId);" in source
    assert "private static String normalizeRecipeLoadedField" in source
    assert "if (!OBSERVATION_RECIPE_MATCH.equals(observationType))" in source
