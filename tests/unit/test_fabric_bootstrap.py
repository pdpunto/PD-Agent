from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_agent.bootstrap import FabricBootstrap, FabricBootstrapError
from pd_agent.core import portable_seed_identity
from pd_agent.project import ProjectInspectionStatus, ProjectInspector


def _create(root: Path, **kwargs):
    return FabricBootstrap().create(
        root,
        mod_id=kwargs.pop("mod_id", "examplemod"),
        package=kwargs.pop("package", "com.example.examplemod"),
        **kwargs,
    )


def test_empty_workspace_bootstraps_and_inspects_ready(tmp_path: Path) -> None:
    result = _create(tmp_path / "project")
    snapshot = ProjectInspector().inspect(result.workspace)

    assert result.status == "SUCCESS"
    assert result.inspection_status == "READY"
    assert snapshot.status == ProjectInspectionStatus.READY
    assert snapshot.fabric_manifests[0].mod_id == "examplemod"
    assert result.manifest_path.exists()


def test_pinned_versions_and_manifest_are_exact(tmp_path: Path) -> None:
    result = _create(tmp_path / "project")
    properties = (result.workspace / "gradle.properties").read_text(encoding="utf-8")
    build = (result.workspace / "build.gradle.kts").read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert "minecraft_version=1.21.11" in properties
    assert "loader_version=0.19.3" in properties
    assert "fabric_api_version=0.141.6+1.21.11" in properties
    assert "mappings_version=1.21.11+build.6" in properties
    assert 'id("fabric-loom") version "1.13.3"' in build
    assert "JavaLanguageVersion.of(21)" in build
    assert manifest["pinned_versions"]["minecraft"] == "1.21.11"
    assert manifest["pinned_versions"]["yarn"] == "1.21.11+build.6"
    assert manifest["timestamp"] is None


def test_same_inputs_have_same_fingerprint_without_timestamp(tmp_path: Path) -> None:
    first = _create(tmp_path / "one")
    second = _create(tmp_path / "two")

    assert first.project_fingerprint == second.project_fingerprint
    assert json.loads(first.manifest_path.read_text())["project_fingerprint"] == first.project_fingerprint


def test_material_input_changes_fingerprint(tmp_path: Path) -> None:
    first = _create(tmp_path / "one")
    second = _create(tmp_path / "two", mod_id="othermod", package="org.example.other")

    assert first.project_fingerprint != second.project_fingerprint


@pytest.mark.parametrize(
    "mod_id",
    ["", "ExampleMod", "has space", "../escape", "a\\b", "a:b", "a..b", "x" * 65],
)
def test_invalid_mod_id_rejected_without_partial_project(tmp_path: Path, mod_id: str) -> None:
    target = tmp_path / "project"
    with pytest.raises(FabricBootstrapError):
        _create(target, mod_id=mod_id)
    assert not target.exists()


@pytest.mark.parametrize("package", ["", "../escape", "a/b", "a\\b", "/absolute", "class.name", "a..b"])
def test_invalid_package_rejected_without_partial_project(tmp_path: Path, package: str) -> None:
    target = tmp_path / "project"
    with pytest.raises(FabricBootstrapError):
        _create(target, package=package)
    assert not target.exists()


def test_non_empty_workspace_and_second_bootstrap_are_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()
    (target / "user.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FabricBootstrapError, match="ALREADY_INITIALIZED"):
        _create(target)
    assert (target / "user.txt").read_text(encoding="utf-8") == "keep"

    empty = tmp_path / "empty"
    _create(empty)
    before = sorted(path.relative_to(empty).as_posix() for path in empty.rglob("*"))
    with pytest.raises(FabricBootstrapError, match="ALREADY_INITIALIZED"):
        _create(empty)
    assert before == sorted(path.relative_to(empty).as_posix() for path in empty.rglob("*"))


def test_seed_identity_is_recorded_and_mismatch_fails(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    (seed / "wrapper").mkdir(parents=True)
    (seed / "wrapper" / "cache.bin").write_bytes(b"seed")
    target = tmp_path / "project"
    result = _create(target, seed_root=seed)
    assert result.seed_identity
    assert json.loads(result.manifest_path.read_text())["seed_identity"] == result.seed_identity

    with pytest.raises(FabricBootstrapError, match="mismatch"):
        _create(tmp_path / "bad", seed_root=seed, expected_seed_identity="0" * 64)


def test_wrapper_source_copies_pinned_wrapper_files(tmp_path: Path) -> None:
    source = tmp_path / "wrapper-source"
    (source / "gradle" / "wrapper").mkdir(parents=True)
    (source / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    (source / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
    (source / "gradle" / "wrapper" / "gradle-wrapper.properties").write_text("distributionUrl=local\n", encoding="utf-8")
    (source / "gradle" / "wrapper" / "gradle-wrapper.jar").write_bytes(b"jar")

    result = _create(tmp_path / "project", wrapper_source_root=source)
    assert (result.workspace / "gradle/wrapper/gradle-wrapper.jar").read_bytes() == b"jar"
    assert (result.workspace / "gradlew.bat").read_text(encoding="utf-8") == "@echo off\n"


def test_product_bootstrap_has_no_benchmark_import() -> None:
    source = Path(__file__).parents[2] / "src" / "pd_agent" / "bootstrap.py"
    assert "pd_agent.benchmark" not in source.read_text(encoding="utf-8")


def test_generated_paths_are_confined_to_workspace(tmp_path: Path) -> None:
    result = _create(tmp_path / "project")
    root = result.workspace
    assert all(root in path.resolve().parents or path.resolve() == root for path in root.rglob("*"))


def test_bootstrap_accepts_canonical_portable_seed_identity(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    (seed / "caches").mkdir(parents=True)
    (seed / "caches" / "stable.bin").write_bytes(b"stable")
    (seed / "caches" / "gc.properties").write_text("volatile", encoding="utf-8")
    expected = portable_seed_identity(seed)
    result = _create(tmp_path / "project", seed_root=seed, expected_seed_identity=expected)
    assert result.seed_identity == expected


def test_old_raw_tree_identity_was_not_canonical(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    (seed / "caches").mkdir(parents=True)
    (seed / "caches" / "stable.bin").write_bytes(b"stable")
    (seed / "caches" / "gc.properties").write_text("volatile", encoding="utf-8")
    raw = __import__("hashlib").sha256()
    for path in sorted(seed.rglob("*"), key=lambda item: item.relative_to(seed).as_posix()):
        if path.is_file():
            raw.update(path.relative_to(seed).as_posix().encode("utf-8"))
            raw.update(b"\0" + path.read_bytes() + b"\0")
    assert raw.hexdigest() != portable_seed_identity(seed)


def test_seed_identity_ignores_only_declared_nonportable_files(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    stable = seed / "stable.bin"
    stable.write_bytes(b"stable")
    first = portable_seed_identity(seed)
    (seed / "gc.properties").write_text("one", encoding="utf-8")
    (seed / "sample.lock").write_text("lock", encoding="utf-8")
    assert portable_seed_identity(seed) == first
    stable.write_bytes(b"changed")
    assert portable_seed_identity(seed) != first


def test_seed_identity_ignores_mtime_and_absolute_location(tmp_path: Path) -> None:
    first_root = tmp_path / "one"
    first_root.mkdir()
    (first_root / "stable.bin").write_bytes(b"stable")
    first = portable_seed_identity(first_root)
    second_root = tmp_path / "nested" / "two"
    second_root.mkdir(parents=True)
    (second_root / "stable.bin").write_bytes(b"stable")
    (first_root / "stable.bin").touch()
    assert portable_seed_identity(first_root) == portable_seed_identity(second_root) == first


def test_generated_kotlin_dsl_uses_valid_property_interpolation(tmp_path: Path) -> None:
    result = _create(tmp_path / "project")
    build = (result.workspace / "build.gradle.kts").read_text(encoding="utf-8")
    assert r"$\{" not in build
    for name in ("minecraft_version", "mappings_version", "loader_version", "fabric_api_version"):
        assert f'${{property("{name}")}}' in build
