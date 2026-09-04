from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pd_agent import ArtifactClassification, ArtifactValidator
from pd_agent.core import BuildResult, ValidationStatus
from pd_agent.project import ProjectInspector
from pd_agent.validation import PreBuildWorkspaceValidator
from tests.fixtures.artifact_projects import write_manifest_jar


def _spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "profile": "vertical_a_resources_v1",
        "namespace": "demo",
        "block_id": "core",
        "item_id": "core_item",
        "recipe_id": "core",
        "recipe_type": "minecraft:crafting_shaped",
        "ingredients": {"I": {"item": "minecraft:iron_ingot"}},
        "result_count": 1,
        "lang_key": "block.demo.core",
        "lang_value": "Core",
        "texture_strategy": "REUSE",
        "texture_reference": "minecraft:block/stone",
        "resource_paths": {
            "blockstate": "src/main/resources/assets/demo/blockstates/core.json",
            "block_model": "src/main/resources/assets/demo/models/block/core.json",
            "item_model": "src/main/resources/assets/demo/models/item/core_item.json",
            "lang": "src/main/resources/assets/demo/lang/en_us.json",
            "recipe": "src/main/resources/data/demo/recipes/core.json",
        },
    }
    spec.update(overrides)
    return spec


def _contract(spec: dict[str, object]) -> dict[str, object]:
    return {"validation_requirements": [{"kind": "artifact", "spec": spec}]}


def _write_resources(root: Path, *, valid: bool = True) -> None:
    paths = _spec()["resource_paths"]
    assert isinstance(paths, dict)
    contents = {
        "blockstate": {"variants": {"": {"model": "demo:block/core"}}},
        "block_model": {"parent": "minecraft:block/cube_all", "textures": {"all": "minecraft:block/stone"}},
        "item_model": {"parent": "demo:block/core"},
        "lang": {"block.demo.core": "Core"},
        "recipe": {
            "type": "minecraft:crafting_shaped",
            "pattern": ["I"],
            "key": {"I": {"item": "minecraft:iron_ingot"}},
            "result": {"id": "demo:core_item", "count": 1},
        },
    }
    for key, path in paths.items():
        target = root / Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(contents[key] if valid else {"broken": True}), encoding="utf-8")


def test_vertical_a_resource_profile_passes_valid_parameterized_set(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _write_resources(root)
    result = PreBuildWorkspaceValidator().validate(root, _contract(_spec()))
    assert result.status is ValidationStatus.PASS


def test_vertical_a_profile_rejects_missing_and_malformed_resources(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _write_resources(root, valid=False)
    result = PreBuildWorkspaceValidator().validate(root, _contract(_spec()))
    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert "VERTICAL_A_BLOCKSTATE_INVALID" in {item.code for item in result.violations}
    missing = _spec()
    missing_paths = dict(missing["resource_paths"])
    missing_paths.pop("item_model")
    missing["resource_paths"] = missing_paths
    missing_result = PreBuildWorkspaceValidator().validate(root, _contract(missing))
    assert any(item.code == "RESOURCE_MISSING" for item in missing_result.violations)


def test_reuse_texture_does_not_require_owned_file(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _write_resources(root)
    result = PreBuildWorkspaceValidator().validate(root, _contract(_spec()))
    assert result.status is ValidationStatus.PASS
    assert not any("texture" in item.requirement for item in result.violations)


def test_owned_texture_is_required_when_declared(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _write_resources(root)
    spec = _spec(texture_strategy="DERIVE", texture_path="src/main/resources/assets/demo/textures/block/core.png")
    result = PreBuildWorkspaceValidator().validate(root, _contract(spec))
    assert any(item.code == "RESOURCE_MISSING" for item in result.violations)


def test_artifact_required_entries_are_checked_and_reported(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    manifest = root / "src/main/resources/fabric.mod.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"id": "buildsimple", "version": "1.0.0"}), encoding="utf-8")
    jar = write_manifest_jar(
        root / "build/libs/buildsimple-1.0.0.jar",
        manifest=json.dumps({"id": "buildsimple", "version": "1.0.0"}),
        extra_files={"assets/demo/models/block/core.json": "{}"},
    )
    snapshot = ProjectInspector().inspect(root)
    started = datetime.now(timezone.utc)
    build = BuildResult(attempt=1, command_display="build", cwd=root, started_at=started, duration_seconds=0, exit_code=0, stdout_log="", stderr_log="")
    result = ArtifactValidator().validate(snapshot, build, required_entries=("assets\\demo\\models\\block\\core.json",))
    assert result.classification == ArtifactClassification.VALID.value
    assert result.metadata["required_entries_checked"] == ["assets/demo/models/block/core.json"]
    assert result.path == jar


def test_missing_or_unsafe_required_entry_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    manifest = root / "src/main/resources/fabric.mod.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"id": "buildsimple", "version": "1.0.0"}), encoding="utf-8")
    write_manifest_jar(root / "build/libs/buildsimple-1.0.0.jar", manifest=manifest.read_text(encoding="utf-8"))
    snapshot = ProjectInspector().inspect(root)
    started = datetime.now(timezone.utc)
    build = BuildResult(attempt=1, command_display="build", cwd=root, started_at=started, duration_seconds=0, exit_code=0, stdout_log="", stderr_log="")
    missing = ArtifactValidator().validate(snapshot, build, required_entries=("assets/demo/missing.json",))
    assert missing.classification == ArtifactClassification.INVALID_METADATA.value
    assert missing.metadata["missing_required_entries"] == ["assets/demo/missing.json"]
    unsafe = ArtifactValidator().validate(snapshot, build, required_entries=("../outside",))
    assert unsafe.classification == ArtifactClassification.INVALID_METADATA.value
