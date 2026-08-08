from __future__ import annotations

import subprocess
from pathlib import Path

from pd_agent.project import ProjectInspectionStatus, ProjectInspector

from tests.fixtures.fabric_projects import (
    make_dirty_git_project,
    make_invalid_metadata_project,
    make_kotlin_dsl_project,
    make_multimodule_ambiguous_project,
    make_multimodule_resolvable_project,
    make_no_git_project,
    make_simple_fabric_project,
    make_wrapper_absent_project,
)


def _inspect(root: Path):
    return ProjectInspector().inspect(root)


def test_simple_fabric_project(tmp_path: Path) -> None:
    root = make_simple_fabric_project(tmp_path / "simple")
    snapshot = _inspect(root)

    assert snapshot.status == ProjectInspectionStatus.READY
    assert snapshot.git.present is True
    assert snapshot.git.head
    assert snapshot.git.branch in {"main", "master"}
    assert snapshot.wrapper.present is True
    assert snapshot.fabric_manifests[0].mod_id == "example"
    assert snapshot.fabric_manifests[0].entrypoints["main"] == ("com.example.ExampleMod",)
    assert "fabric-api" in snapshot.fabric_manifests[0].dependencies.depends
    assert snapshot.mixin_configs[0].package == "com.example.mixin"
    assert snapshot.detected_versions["minecraft"].value == "1.20.1"
    assert snapshot.target_subproject is not None
    assert snapshot.target_subproject.name == "simple"
    assert snapshot.modules


def test_kotlin_dsl_project(tmp_path: Path) -> None:
    root = make_kotlin_dsl_project(tmp_path / "kotlin")
    (root / "build.gradle.kts").write_text(
        """
plugins { id("fabric-loom") version "1.8-SNAPSHOT" }
sourceSets {
    val main by getting {
        java.srcDir("src/main/java")
        resources.srcDir("src/generated/resources")
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "src" / "generated" / "resources").mkdir(parents=True, exist_ok=True)
    snapshot = _inspect(root)

    assert snapshot.status == ProjectInspectionStatus.READY
    assert any(path.as_posix().endswith("src/main/java") for path in snapshot.source_roots)
    assert any(path.as_posix().endswith("src/generated/resources") for path in snapshot.resource_roots)


def test_no_git_project(tmp_path: Path) -> None:
    root = make_no_git_project(tmp_path / "nogit")
    snapshot = _inspect(root)

    assert snapshot.git.present is False
    assert snapshot.status == ProjectInspectionStatus.READY


def test_dirty_git_project(tmp_path: Path) -> None:
    root = make_dirty_git_project(tmp_path / "dirty")
    snapshot = _inspect(root)

    assert snapshot.git.present is True
    assert snapshot.git.working_tree_clean is False
    assert snapshot.git.status_porcelain


def test_invalid_metadata_project(tmp_path: Path) -> None:
    root = make_invalid_metadata_project(tmp_path / "invalid")
    snapshot = _inspect(root)

    assert snapshot.status == ProjectInspectionStatus.INCOMPATIBLE
    assert snapshot.fabric_manifests[0].errors


def test_wrapper_absent_project(tmp_path: Path) -> None:
    root = make_wrapper_absent_project(tmp_path / "nowrap")
    snapshot = _inspect(root)

    assert snapshot.status == ProjectInspectionStatus.INCOMPATIBLE
    assert snapshot.wrapper.present is False


def test_multimodule_resolvable_project(tmp_path: Path) -> None:
    root = make_multimodule_resolvable_project(tmp_path / "multi-ok")
    snapshot = _inspect(root)

    assert snapshot.status == ProjectInspectionStatus.READY
    assert snapshot.target_subproject is not None
    assert snapshot.target_subproject.name == "mod-a"


def test_multimodule_ambiguous_project(tmp_path: Path) -> None:
    root = make_multimodule_ambiguous_project(tmp_path / "multi-amb")
    snapshot = _inspect(root)

    assert snapshot.status == ProjectInspectionStatus.BLOCKED
    assert snapshot.target_subproject is None


def test_parser_does_not_execute_gradle_or_project_code(tmp_path: Path, monkeypatch) -> None:
    root = make_simple_fabric_project(tmp_path / "safe")
    commands: list[list[str]] = []

    real_run = subprocess.run

    def spy_run(*args, **kwargs):
        cmd = args[0]
        if isinstance(cmd, list):
            commands.append(cmd)
        return real_run(*args, **kwargs)

    monkeypatch.setattr("pd_agent.project.git.subprocess.run", spy_run)
    snapshot = _inspect(root)

    assert snapshot.status == ProjectInspectionStatus.READY
    assert commands
    assert all(cmd[0] == "git" for cmd in commands)
    assert not any("gradle" in " ".join(cmd).lower() for cmd in commands)

