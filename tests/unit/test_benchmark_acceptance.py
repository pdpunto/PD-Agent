from __future__ import annotations

import json
from pathlib import Path

from pd_agent.benchmark.acceptance import (
    build_required_minecraft_observation_spec,
    evaluate_required_minecraft_observations,
    evaluate_required_resources,
)
from pd_agent.minecraft import MinecraftObservationType, MinecraftTestSpec
from tests.fixtures.artifact_projects import write_manifest_jar


def _jar(root: Path, *, extra_files: dict[str, bytes | str] | None = None) -> Path:
    return write_manifest_jar(
        root / "build" / "libs" / "target.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "examplemod",
                "version": "1.0.0",
                "environment": "*",
                "entrypoints": {"main": ["com.example.examplemod.ExampleMod"]},
            }
        ),
        extra_files=extra_files,
    )


def _base_spec() -> MinecraftTestSpec:
    return MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="examplemod",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="f6",
        observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        observation_params={"registry_kind": "block", "identifier": "examplemod:marble_lantern"},
        timeout_seconds=30,
    )


def test_required_resources_evaluate_json_and_text_content(tmp_path: Path) -> None:
    jar = _jar(
        tmp_path,
        extra_files={
            "assets/examplemod/lang/en_us.json": json.dumps(
                {
                    "block.examplemod.marble_lantern": "Marble Lantern",
                    "item.examplemod.marble_lantern": "Marble Lantern",
                }
            ),
        },
    )
    evaluation = evaluate_required_resources(
        jar,
        {
            "required_resources": [
                {
                    "path": "assets/examplemod/lang/en_us.json",
                    "type": "json",
                    "assertions": [
                        {"kind": "json_pointer_equals", "path": "/block.examplemod.marble_lantern", "value": "Marble Lantern"},
                        {"kind": "json_pointer_equals", "path": "/item.examplemod.marble_lantern", "value": "Marble Lantern"},
                    ],
                }
            ]
        },
    )

    assert evaluation.passed is True
    assert evaluation.required_resources[0]["passed"] is True
    assert evaluation.required_resources[0]["assertions"][0]["passed"] is True
    assert evaluation.required_resources[0]["assertions"][1]["passed"] is True


def test_required_resources_fail_when_lang_value_is_wrong(tmp_path: Path) -> None:
    jar = _jar(
        tmp_path,
        extra_files={
            "assets/examplemod/lang/en_us.json": json.dumps(
                {
                    "block.examplemod.marble_lantern": "Lantern",
                    "item.examplemod.marble_lantern": "Lantern",
                }
            ),
        },
    )
    evaluation = evaluate_required_resources(
        jar,
        {
            "required_resources": [
                {
                    "path": "assets/examplemod/lang/en_us.json",
                    "type": "json",
                    "assertions": [
                        {"kind": "json_pointer_equals", "path": "/block.examplemod.marble_lantern", "value": "Marble Lantern"},
                        {"kind": "json_pointer_equals", "path": "/item.examplemod.marble_lantern", "value": "Marble Lantern"},
                    ],
                }
            ]
        },
    )

    assert evaluation.passed is False
    assert any("expected" in violation for violation in evaluation.violations)


def test_required_minecraft_observations_build_secondary_item_check() -> None:
    base_spec = _base_spec()
    evaluation = evaluate_required_minecraft_observations(
        base_spec,
        {
            "required_minecraft_observations": [
                {
                    "test_id": "f6-item",
                    "observation_type": "REGISTRY_ENTRY_PRESENT",
                    "observation_params": {"registry_kind": "item", "identifier": "examplemod:marble_lantern"},
                }
            ]
        },
    )

    assert evaluation.passed is True
    assert len(evaluation.required_observations) == 1
    extra = evaluation.required_observations[0]
    assert extra.test_id == "f6-item"
    assert extra.observation_type is MinecraftObservationType.REGISTRY_ENTRY_PRESENT
    assert extra.observation_params == {"registry_kind": "item", "identifier": "examplemod:marble_lantern"}


def test_build_required_minecraft_observation_spec_preserves_base_defaults() -> None:
    base_spec = _base_spec()
    derived = build_required_minecraft_observation_spec(
        base_spec,
        {
            "test_id": "f6-item",
            "observation_type": "REGISTRY_ENTRY_PRESENT",
            "observation_params": {"registry_kind": "item", "identifier": "examplemod:marble_lantern"},
        },
    )

    assert derived.target_jar == base_spec.target_jar
    assert derived.target_mod_id == base_spec.target_mod_id
    assert derived.minecraft_version == base_spec.minecraft_version
    assert derived.loader_version == base_spec.loader_version
    assert derived.timeout_seconds == base_spec.timeout_seconds
    assert derived.expect_neighbor_update is base_spec.expect_neighbor_update
