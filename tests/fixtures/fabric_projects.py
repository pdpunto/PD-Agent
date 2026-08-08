"""Offline Fabric project fixtures for tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "-c", "user.name=Codex", "-c", "user.email=codex@example.com", "add", "."], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "-c", "user.name=Codex", "-c", "user.email=codex@example.com", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)


def make_simple_fabric_project(root: Path, *, with_git: bool = True, dirty: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "gradlew", "#!/bin/sh\n")
    _write(root / "settings.gradle.kts", 'rootProject.name = "example"\n')
    _write(
        root / "build.gradle.kts",
        """
plugins {
    id("fabric-loom") version "1.8-SNAPSHOT"
}

dependencies {
    minecraft("com.mojang:minecraft:${minecraft_version}")
    mappings("net.fabricmc:yarn:${mappings}:v2")
    modImplementation("net.fabricmc.fabric-api:fabric-api:${fabric_version}")
}
""".strip()
        + "\n",
    )
    _write(
        root / "gradle.properties",
        "\n".join(
            [
                "minecraft_version=1.20.1",
                "mappings=1.20.1+build.10",
                "fabric_version=0.92.1+1.20.1",
                "loader_version=0.15.11",
                "loom_version=1.8-SNAPSHOT",
            ]
        )
        + "\n",
    )
    _write(
        root / "src" / "main" / "resources" / "fabric.mod.json",
        """
{
  "schemaVersion": 1,
  "id": "example",
  "version": "${version}",
  "environment": "*",
  "entrypoints": {
    "main": ["com.example.ExampleMod"]
  },
  "mixins": ["example.mixins.json"],
  "depends": {
    "fabricloader": ">=0.15.0",
    "minecraft": "~1.20.1",
    "fabric-api": "*"
  }
}
""".strip()
        + "\n",
    )
    _write(
        root / "src" / "main" / "resources" / "example.mixins.json",
        """
{
  "required": true,
  "package": "com.example.mixin",
  "compatibilityLevel": "JAVA_17",
  "mixins": ["ExampleMixin"],
  "client": [],
  "server": [],
  "injectors": {
    "defaultRequire": 1
  }
}
""".strip()
        + "\n",
    )
    _write(root / "src" / "main" / "java" / "com" / "example" / "ExampleMod.java", "package com.example; class ExampleMod {}\n")
    if with_git:
        _git_init(root)
        if dirty:
            _write(root / "src" / "main" / "java" / "com" / "example" / "ExampleMod.java", "package com.example; class ExampleMod { int x = 1; }\n")
    return root


def make_kotlin_dsl_project(root: Path) -> Path:
    return make_simple_fabric_project(root, with_git=False)


def make_no_git_project(root: Path) -> Path:
    return make_simple_fabric_project(root, with_git=False)


def make_dirty_git_project(root: Path) -> Path:
    return make_simple_fabric_project(root, with_git=True, dirty=True)


def make_invalid_metadata_project(root: Path) -> Path:
    make_simple_fabric_project(root, with_git=False)
    _write(
        root / "src" / "main" / "resources" / "fabric.mod.json",
        "{ invalid json",
    )
    return root


def make_wrapper_absent_project(root: Path) -> Path:
    make_simple_fabric_project(root, with_git=False)
    (root / "gradlew").unlink()
    return root


def make_multimodule_resolvable_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "gradlew", "#!/bin/sh\n")
    _write(root / "settings.gradle.kts", 'include(":mod-a", ":lib")\n')
    _write(root / "mod-a" / "build.gradle.kts", 'plugins { id("fabric-loom") }\n')
    _write(
        root / "mod-a" / "src" / "main" / "resources" / "fabric.mod.json",
        '{ "schemaVersion": 1, "id": "moda", "version": "1.0.0", "environment": "*" }\n',
    )
    _write(root / "lib" / "build.gradle.kts", 'plugins { java }\n')
    _git_init(root)
    return root


def make_multimodule_ambiguous_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "gradlew", "#!/bin/sh\n")
    _write(root / "settings.gradle.kts", 'include(":mod-a", ":mod-b")\n')
    for module in ("mod-a", "mod-b"):
        _write(
            root / module / "src" / "main" / "resources" / "fabric.mod.json",
            f'{{ "schemaVersion": 1, "id": "{module}", "version": "1.0.0", "environment": "*" }}\n',
        )
        _write(root / module / "build.gradle.kts", 'plugins { id("fabric-loom") }\n')
    _git_init(root)
    return root

