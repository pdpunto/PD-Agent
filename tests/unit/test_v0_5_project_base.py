from __future__ import annotations

from pathlib import Path

from pd_agent.project import ProjectInspectionStatus, ProjectInspector
from pd_agent.benchmark.workspace import compute_fixture_identity


ROOT = Path(__file__).resolve().parents[2]
PROJECT_BASE = ROOT / "benchmarks" / "projects" / "v0_5_fabric_base"


def test_v0_5_project_base_is_ready() -> None:
    snapshot = ProjectInspector().inspect(PROJECT_BASE)

    assert snapshot.status == ProjectInspectionStatus.READY
    assert snapshot.wrapper.present is True
    assert snapshot.target_subproject == PROJECT_BASE
    assert snapshot.detected_versions["minecraft"].value == "1.21.11"
    assert snapshot.detected_versions["loader"].value == "0.19.3"
    assert snapshot.detected_versions["loom"].value == "1.13.3"
    assert snapshot.fabric_manifests[0].mod_id == "examplemod"
    assert snapshot.fabric_manifests[0].entrypoints["main"] == ("com.example.examplemod.ExampleMod",)
    assert snapshot.fabric_manifests[0].entrypoints["client"] == ("com.example.examplemod.client.ExampleModClient",)
    assert any(path.name == "fabric.mod.json" for path in snapshot.relevant_files)
    assert any(path.as_posix().endswith("src/main/java") for path in snapshot.source_roots)
    assert any(path.as_posix().endswith("src/main/resources") for path in snapshot.resource_roots)


def test_v0_5_project_base_has_complete_wrapper() -> None:
    assert (PROJECT_BASE / "gradlew").exists()
    assert (PROJECT_BASE / "gradlew.bat").exists()
    assert (PROJECT_BASE / "gradle" / "wrapper" / "gradle-wrapper.jar").exists()
    assert (PROJECT_BASE / "gradle" / "wrapper" / "gradle-wrapper.properties").exists()


def test_v0_5_project_base_identity_is_stable() -> None:
    first = compute_fixture_identity(PROJECT_BASE)
    second = compute_fixture_identity(PROJECT_BASE)

    assert first == second
    assert len(first) == 64


def test_v0_5_project_base_has_no_benchmark_helpers() -> None:
    forbidden = [
        "B001",
        "B002",
        "B003",
        "HarnessRunner",
        "TargetBridge",
        "applyProbeState",
        "expectedProbeState",
        "probeIdentifier",
        "Registries.BLOCK",
    ]
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            PROJECT_BASE / "build.gradle.kts",
            PROJECT_BASE / "settings.gradle.kts",
            PROJECT_BASE / "gradle.properties",
            PROJECT_BASE / "PROVENANCE.md",
            PROJECT_BASE / "src" / "main" / "resources" / "fabric.mod.json",
            PROJECT_BASE / "src" / "main" / "java" / "com" / "example" / "examplemod" / "ExampleMod.java",
            PROJECT_BASE / "src" / "main" / "java" / "com" / "example" / "examplemod" / "client" / "ExampleModClient.java",
        ]
    )

    assert not any(token in text for token in forbidden)
