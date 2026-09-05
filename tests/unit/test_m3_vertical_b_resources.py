from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.core import ValidationStatus
from pd_agent.validation import PreBuildWorkspaceValidator
from pd_agent.artifacts import ArtifactClassification, ArtifactValidator
from pd_agent.build import FabricBuildOrchestrator
from pd_agent.core import BuildResult
from pd_agent.project import ProjectInspector
from tests.fixtures.artifact_projects import make_simple_artifact_project, write_manifest_jar


def _spec(*, item_id: str = "ruby", display_name: str = "Ruby", source_path: str = "src/main/java/demo/RubyItem.java", **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "profile": "vertical_b_resources_v1",
        "namespace": "demo",
        "item_id": item_id,
        "display_name": display_name,
        "settings": {"max_count": 16},
        "source_path": source_path,
        "texture_strategy": "REUSE",
        "texture_reference": "minecraft:item/iron_ingot",
        "resource_paths": {
            "item_model": f"src/main/resources/assets/demo/models/item/{item_id}.json",
            "lang": "src/main/resources/assets/demo/lang/en_us.json",
        },
    }
    value.update(overrides)
    return value


def _contract(*specs: dict[str, object]) -> dict[str, object]:
    return {"validation_requirements": [{"kind": "build", "spec": spec} for spec in specs]}


def _write_item(root: Path, spec: dict[str, object], *, registration_id: str | None = None) -> None:
    source = root / str(spec["source_path"])
    source.parent.mkdir(parents=True, exist_ok=True)
    item_id = registration_id or str(spec["item_id"])
    source.write_text(
        f'Registry.register(Registries.ITEM, Identifier.of("demo", "{item_id}"), new Item(new Item.Settings().maxCount(16)));',
        encoding="utf-8",
    )
    paths = spec["resource_paths"]
    assert isinstance(paths, dict)
    model = root / str(paths["item_model"])
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_text(json.dumps({"parent": "minecraft:item/generated"}), encoding="utf-8")
    lang = root / str(paths["lang"])
    lang.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(lang.read_text(encoding="utf-8")) if lang.exists() else {}
    existing[f"item.demo.{spec['item_id']}"] = spec["display_name"]
    lang.write_text(json.dumps(existing), encoding="utf-8")


def _write_recipe(root: Path, spec: dict[str, object], ingredients: list[str] | None = None, *, output: str | None = None) -> None:
    path = root / str(spec["resource_paths"]["recipe"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "minecraft:crafting_shapeless",
        "ingredients": [{"item": item} for item in (ingredients or ["minecraft:iron_ingot"])],
        "result": {"id": output or "demo:ruby", "count": 1},
    }), encoding="utf-8")


def test_vertical_b_profile_validates_item_model_lang_and_vanilla_recipe(tmp_path: Path) -> None:
    spec = _spec(resource_paths={
        "item_model": "src/main/resources/assets/demo/models/item/ruby.json",
        "lang": "src/main/resources/assets/demo/lang/en_us.json",
        "recipe": "src/main/resources/data/demo/recipes/ruby.json",
    }, expected_output_id="demo:ruby", expected_ingredients=({"item_id": "minecraft:iron_ingot", "quantity": 1},))
    _write_item(tmp_path, spec)
    _write_recipe(tmp_path, spec)
    result = PreBuildWorkspaceValidator().validate(tmp_path, _contract(spec))
    assert result.status is ValidationStatus.PASS


def test_vertical_b_validates_two_items_and_cross_item_recipe(tmp_path: Path) -> None:
    first = _spec(item_id="shard", display_name="Shard", source_path="src/main/java/demo/ShardItem.java")
    second = _spec(item_id="core", display_name="Core", source_path="src/main/java/demo/CoreItem.java", resource_paths={
        "item_model": "src/main/resources/assets/demo/models/item/core.json",
        "lang": "src/main/resources/assets/demo/lang/en_us.json",
        "recipe": "src/main/resources/data/demo/recipes/core.json",
    }, expected_output_id="demo:core", expected_ingredients=({"item_id": "demo:shard", "quantity": 1},))
    _write_item(tmp_path, first)
    _write_item(tmp_path, second)
    _write_recipe(tmp_path, second, ["demo:shard"], output="demo:core")
    assert PreBuildWorkspaceValidator().validate(tmp_path, _contract(first, second)).status is ValidationStatus.PASS


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("missing_source", "VERTICAL_B_ITEM_SOURCE_MISSING"),
        ("wrong_id", "VERTICAL_B_ITEM_REGISTRATION_MISSING"),
        ("missing_model", "VERTICAL_B_RESOURCE_MISSING"),
        ("wrong_lang", "VERTICAL_B_LANG_ENTRY_MISMATCH"),
        ("wrong_ingredient", "VERTICAL_B_RECIPE_INGREDIENT_MISMATCH"),
        ("wrong_output", "VERTICAL_B_RECIPE_OUTPUT_MISMATCH"),
    ],
)
def test_vertical_b_reports_actionable_failures(tmp_path: Path, change: str, code: str) -> None:
    spec = _spec(resource_paths={
        "item_model": "src/main/resources/assets/demo/models/item/ruby.json",
        "lang": "src/main/resources/assets/demo/lang/en_us.json",
        "recipe": "src/main/resources/data/demo/recipes/ruby.json",
    }, expected_output_id="demo:ruby", expected_ingredients=({"item_id": "demo:shard", "quantity": 1},))
    _write_item(tmp_path, spec, registration_id="other" if change == "wrong_id" else None)
    if change == "missing_source":
        (tmp_path / str(spec["source_path"])).unlink()
    if change == "missing_model":
        (tmp_path / str(spec["resource_paths"]["item_model"])).unlink()
    if change == "wrong_lang":
        (tmp_path / str(spec["resource_paths"]["lang"])).write_text("{}", encoding="utf-8")
    _write_recipe(tmp_path, spec, ["minecraft:iron_ingot"] if change == "wrong_ingredient" else ["demo:shard"], output="demo:other" if change == "wrong_output" else "demo:ruby")
    result = PreBuildWorkspaceValidator().validate(tmp_path, _contract(spec))
    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert code in {item.code for item in result.violations}
    assert all(item.phase == "PRE_BUILD" for item in result.violations)


def test_vertical_b_rejects_unsafe_source_path(tmp_path: Path) -> None:
    spec = _spec(source_path="../outside/Item.java")
    result = PreBuildWorkspaceValidator().validate(tmp_path, _contract(spec))
    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert any(item.code == "VERTICAL_B_PATH_INVALID" for item in result.violations)


def test_vertical_b_rejects_incompatible_duplicate_model_owner(tmp_path: Path) -> None:
    first = _spec(item_id="one", source_path="src/main/java/demo/OneItem.java")
    second = _spec(item_id="two", source_path="src/main/java/demo/TwoItem.java", resource_paths={
        "item_model": first["resource_paths"]["item_model"],
        "lang": "src/main/resources/assets/demo/lang/en_us.json",
    })
    _write_item(tmp_path, first)
    _write_item(tmp_path, second)
    result = PreBuildWorkspaceValidator().validate(tmp_path, _contract(first, second))
    assert any(item.code == "VERTICAL_B_RESOURCE_PATH_CONFLICT" for item in result.violations)


def test_vertical_b_26_2_contract_does_not_require_yarn() -> None:
    spec = _spec()
    spec["platform"] = "26.2"
    spec["mappings_namespace"] = None
    assert spec["profile"] == "vertical_b_resources_v1"


def test_vertical_b_artifact_entries_are_derived_and_shared_lang_is_deduplicated() -> None:
    validations = (
        SimpleNamespace(kind="artifact", spec={
            "profile": "vertical_b_resources_v1",
            "resource_paths": {
                "item_model": "src/main/resources/assets/demo/models/one.json",
                "lang": "src/main/resources/assets/demo/lang/en_us.json",
            },
            "texture_strategy": "REUSE",
            "texture_reference": "minecraft:item/iron_ingot",
        }),
        SimpleNamespace(kind="artifact", spec={
            "profile": "vertical_b_resources_v1",
            "resource_paths": {
                "item_model": "src/main/resources/assets/demo/models/two.json",
                "lang": "src/main/resources/assets/demo/lang/en_us.json",
                "recipe": "src/main/resources/data/demo/recipes/core.json",
            },
            "texture_strategy": "DERIVE",
            "texture_path": {},
        }),
    )
    contract = SimpleNamespace(validation_requirements=validations)
    entries = FabricBuildOrchestrator()._required_artifact_entries(contract)
    assert entries == (
        "assets/demo/models/one.json",
        "assets/demo/lang/en_us.json",
        "assets/demo/models/two.json",
        "data/demo/recipes/core.json",
    )


def test_vertical_b_artifact_validator_checks_required_entries_and_allows_extra_files(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "artifact")
    snapshot = ProjectInspector().inspect(root)
    started = datetime.now(timezone.utc)
    jar = write_manifest_jar(
        root / "build/libs/buildsimple-1.0.0.jar",
        manifest=json.dumps({"schemaVersion": 1, "id": "buildsimple", "version": "1.0.0", "environment": "*"}),
        extra_files={
            "assets/demo/models/item/one.json": "{}",
            "assets/demo/lang/en_us.json": "{}",
            "data/demo/recipes/core.json": "{}",
            "assets/demo/extra.txt": "allowed",
        },
        mtime=started,
    )
    build = BuildResult(attempt=1, command_display="build", cwd=root, started_at=started, duration_seconds=0, exit_code=0, stdout_log="", stderr_log="")
    required = ("assets/demo/models/item/one.json", "assets/demo/lang/en_us.json", "data/demo/recipes/core.json")
    result = ArtifactValidator().validate(snapshot, build, required_entries=required)
    assert result.classification == ArtifactClassification.VALID.value
    assert result.path == jar
    assert result.metadata["required_entries_checked"] == list(required)
    missing = ArtifactValidator().validate(snapshot, build, required_entries=required + ("assets/demo/models/item/missing.json",))
    assert missing.classification == ArtifactClassification.INVALID_METADATA.value
    assert missing.metadata["missing_required_entries"] == ["assets/demo/models/item/missing.json"]
