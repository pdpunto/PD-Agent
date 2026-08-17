from __future__ import annotations

from pathlib import Path

import pytest

from pd_agent.benchmark import (
    ResolvedRuntimeModDependency,
    RuntimeModDependencyResolutionError,
    resolve_runtime_mod_dependencies,
)
from pd_agent.minecraft import MinecraftTestSpec
from tests.fixtures.artifact_projects import write_jar, write_manifest_jar


ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _runtime_project(root: Path, *, duplicate_sidecar: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "gradlew", "#!/bin/sh\n")
    _write(root / "settings.gradle.kts", 'rootProject.name = "runtime-mods"\n')
    _write(
        root / "build.gradle.kts",
        """
plugins {
    id("fabric-loom") version "1.13.3"
}

repositories {
    mavenCentral()
    maven("https://maven.fabricmc.net/")
}

dependencies {
    minecraft("com.mojang:minecraft:${property("minecraft_version")}")
    mappings("net.fabricmc:yarn:${property("mappings_version")}:v2")
    modImplementation("net.fabricmc.fabric-api:fabric-api:${property("fabric_api_version")}")
    modImplementation("net.fabricmc:fabric-loader:${property("loader_version")}")
    modRuntimeOnly("com.example:sidecar:1.0.0")
    modRuntimeOnly("com.google.guava:guava:31.1-jre")
""".strip()
        + ("\n    modRuntimeOnly(\"com.example:sidecar:1.0.0\")\n" if duplicate_sidecar else "\n")
        + "}\n",
    )
    _write(
        root / "gradle.properties",
        "\n".join(
            [
                "minecraft_version=1.21.11",
                "mappings_version=1.21.11+build.6",
                "fabric_api_version=0.141.6+1.21.11",
                "loader_version=0.19.3",
            ]
        )
        + "\n",
    )
    _write(
        root / "src" / "main" / "resources" / "fabric.mod.json",
        """
{
  "schemaVersion": 1,
  "id": "runtime-mods",
  "version": "1.0.0",
  "environment": "*"
}
""".strip()
        + "\n",
    )
    return root


def _fake_mod_jar(base: Path, *, group: str, artifact: str, version: str, hash_dir: str, manifest_id: str) -> Path:
    jar = (
        base
        / "caches"
        / "modules-2"
        / "files-2.1"
        / Path(*group.split("."))
        / artifact
        / version
        / hash_dir
        / f"{artifact}-{version}.jar"
    )
    write_manifest_jar(
        jar,
        manifest=(
            "{"
            f'"schemaVersion": 1, "id": "{manifest_id}", "version": "{version}", "environment": "*"'
            "}"
        ),
    )
    return jar


def _fake_plain_jar(base: Path, *, group: str, artifact: str, version: str, hash_dir: str) -> Path:
    jar = (
        base
        / "caches"
        / "modules-2"
        / "files-2.1"
        / Path(*group.split("."))
        / artifact
        / version
        / hash_dir
        / f"{artifact}-{version}.jar"
    )
    write_jar(jar, files={"META-INF/MANIFEST.MF": "Manifest-Version: 1.0\n"})
    return jar


def test_spec_runtime_mod_jars_round_trip_and_default_empty(tmp_path: Path) -> None:
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="runtime-mods",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="runtime-mods",
        timeout_seconds=90,
    )

    assert spec.runtime_mod_jars == ()
    assert spec.to_dict()["runtime_mod_jars"] == []
    assert MinecraftTestSpec.from_dict(spec.to_dict()) == spec

    rich_spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="runtime-mods",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="runtime-mods",
        runtime_mod_jars=(Path("mods/b.jar"), Path("mods/a.jar")),
        timeout_seconds=90,
    )

    assert rich_spec.runtime_mod_jars == (Path("mods/a.jar"), Path("mods/b.jar"))
    assert rich_spec.to_dict()["runtime_mod_jars"] == ["mods/a.jar", "mods/b.jar"]
    assert MinecraftTestSpec.from_dict(rich_spec.to_dict()) == rich_spec


@pytest.mark.parametrize(
    "runtime_mod_jars",
    [
        (Path("mods/a.jar"), Path("mods/a.jar")),
        (Path("mods/a.jar"), Path("build/libs/target.jar")),
    ],
)
def test_spec_rejects_duplicate_or_target_runtime_mod_jars(
    runtime_mod_jars: tuple[Path, Path],
) -> None:
    with pytest.raises(ValueError):
        MinecraftTestSpec(
            target_jar=Path("build/libs/target.jar"),
            target_mod_id="runtime-mods",
            minecraft_version="1.21.11",
            loader_version="0.19.3",
            test_id="runtime-mods",
            runtime_mod_jars=runtime_mod_jars,
            timeout_seconds=90,
        )


def test_runtime_mod_dependency_resolver_finds_target_runtime_mods_and_skips_platform_and_non_mods(
    tmp_path: Path,
) -> None:
    project_root = _runtime_project(tmp_path / "project")
    gradle_home = tmp_path / "gradle-home"
    fabric_api_jar = _fake_mod_jar(
        gradle_home,
        group="net.fabricmc.fabric-api",
        artifact="fabric-api",
        version="0.141.6+1.21.11",
        hash_dir="fabric-api-hash",
        manifest_id="fabric-api",
    )
    _fake_mod_jar(
        gradle_home,
        group="net.fabricmc",
        artifact="fabric-loader",
        version="0.19.3",
        hash_dir="loader-hash",
        manifest_id="fabricloader",
    )
    sidecar_jar = _fake_mod_jar(
        gradle_home,
        group="com.example",
        artifact="sidecar",
        version="1.0.0",
        hash_dir="sidecar-hash",
        manifest_id="sidecar",
    )
    _fake_plain_jar(
        gradle_home,
        group="com.google.guava",
        artifact="guava",
        version="31.1-jre",
        hash_dir="guava-hash",
    )

    dependencies = resolve_runtime_mod_dependencies(project_root, gradle_user_home=gradle_home)

    assert [item.coordinate for item in dependencies] == [
        "com.example:sidecar:1.0.0",
        "net.fabricmc.fabric-api:fabric-api:0.141.6+1.21.11",
    ]
    assert [item.path for item in dependencies] == [sidecar_jar.resolve(), fabric_api_jar.resolve()]
    assert all(len(item.sha256) == 64 for item in dependencies)
    assert dependencies[0].source.startswith(str(project_root / "build.gradle.kts"))
    assert "modRuntimeOnly" in dependencies[0].source
    assert isinstance(dependencies[0], ResolvedRuntimeModDependency)
    assert dependencies[0].to_dict()["path"].endswith("sidecar-1.0.0.jar")
    assert dependencies[1].to_dict()["path"].endswith("fabric-api-0.141.6+1.21.11.jar")


def test_runtime_mod_dependency_resolver_returns_empty_tuple_when_no_runtime_mods_are_available(
    tmp_path: Path,
) -> None:
    project_root = _runtime_project(tmp_path / "project")
    (project_root / "build.gradle.kts").write_text(
        """
plugins {
    id("fabric-loom") version "1.13.3"
}

repositories {
    mavenCentral()
    maven("https://maven.fabricmc.net/")
}

dependencies {
    minecraft("com.mojang:minecraft:${property("minecraft_version")}")
    mappings("net.fabricmc:yarn:${property("mappings_version")}:v2")
    modImplementation("net.fabricmc:fabric-loader:${property("loader_version")}")
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    gradle_home = tmp_path / "gradle-home"
    _fake_mod_jar(
        gradle_home,
        group="net.fabricmc",
        artifact="fabric-loader",
        version="0.19.3",
        hash_dir="loader-hash",
        manifest_id="fabricloader",
    )

    dependencies = resolve_runtime_mod_dependencies(project_root, gradle_user_home=gradle_home)

    assert dependencies == ()


def test_runtime_mod_dependency_resolver_rejects_missing_dependency(tmp_path: Path) -> None:
    project_root = _runtime_project(tmp_path / "project")
    (project_root / "build.gradle.kts").write_text(
        """
plugins {
    id("fabric-loom") version "1.13.3"
}

dependencies {
    modRuntimeOnly("com.example:missing:1.0.0")
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeModDependencyResolutionError, match="missing runtime mod dependency"):
        resolve_runtime_mod_dependencies(project_root, gradle_user_home=tmp_path / "gradle-home")


def test_runtime_mod_dependency_resolver_rejects_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _runtime_project(tmp_path / "project")
    gradle_home = tmp_path / "gradle-home"
    escaped_jar = _fake_mod_jar(
        tmp_path / "outside",
        group="com.example",
        artifact="sidecar",
        version="1.0.0",
        hash_dir="escape-hash",
        manifest_id="sidecar",
    )

    def _escape(*_args, **_kwargs):  # noqa: ANN001, ANN002
        return escaped_jar

    monkeypatch.setattr("pd_agent.benchmark.dependencies._locate_runtime_mod_jar", _escape)

    with pytest.raises(RuntimeModDependencyResolutionError, match="escapes gradle_user_home"):
        resolve_runtime_mod_dependencies(project_root, gradle_user_home=gradle_home)


def test_runtime_mod_dependency_resolver_deduplicates_identical_coordinates(tmp_path: Path) -> None:
    project_root = _runtime_project(tmp_path / "project", duplicate_sidecar=True)
    gradle_home = tmp_path / "gradle-home"
    _fake_mod_jar(
        gradle_home,
        group="net.fabricmc.fabric-api",
        artifact="fabric-api",
        version="0.141.6+1.21.11",
        hash_dir="fabric-api-hash",
        manifest_id="fabric-api",
    )
    _fake_mod_jar(
        gradle_home,
        group="com.example",
        artifact="sidecar",
        version="1.0.0",
        hash_dir="sidecar-hash",
        manifest_id="sidecar",
    )
    _fake_plain_jar(
        gradle_home,
        group="com.google.guava",
        artifact="guava",
        version="31.1-jre",
        hash_dir="guava-hash",
    )

    dependencies = resolve_runtime_mod_dependencies(project_root, gradle_user_home=gradle_home)

    assert [item.coordinate for item in dependencies] == [
        "com.example:sidecar:1.0.0",
        "net.fabricmc.fabric-api:fabric-api:0.141.6+1.21.11",
    ]
