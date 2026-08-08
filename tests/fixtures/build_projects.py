"""Offline build runner fixtures."""

from __future__ import annotations

import sys
from pathlib import Path


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _fake_wrapper_script(root: Path) -> Path:
    script = root / "fake_wrapper.py"
    _write(
        script,
        r"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import time

mode = sys.argv[1]
task = sys.argv[2] if len(sys.argv) > 2 else ""
sentinel = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None

if mode == "success":
    print(f"stdout:{task}")
    print("stderr:warn", file=sys.stderr)
    raise SystemExit(0)

if mode == "fail":
    print(f"stdout:{task}")
    print("stderr:boom", file=sys.stderr)
    raise SystemExit(2)

if mode == "timeout":
    if sentinel is not None:
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib, sys, time; "
                    "time.sleep(5); "
                    "pathlib.Path(sys.argv[1]).write_text('child survived', encoding='utf-8')"
                ),
                str(sentinel),
            ]
        )
        time.sleep(5)
        child.wait()
    else:
        time.sleep(5)
    raise SystemExit(0)

raise SystemExit(3)
""".strip()
        + "\n",
    )
    return script


def _write_windows_wrapper(root: Path, mode: str) -> Path:
    wrapper = root / "gradlew.bat"
    script = _fake_wrapper_script(root)
    python_exe = sys.executable
    sentinel_path = root / "child-survived.txt"
    sentinel_arg = f'"{sentinel_path}"' if mode == "timeout" else ""
    extra = f" {sentinel_arg}" if sentinel_arg else ""
    _write(
        wrapper,
        "\n".join(
            [
                "@echo off",
                f"\"{python_exe}\" \"{script}\" {mode} %*{extra}",
                "exit /b %ERRORLEVEL%",
            ]
        )
        + "\n",
    )
    _write(root / "gradlew", "#!/bin/sh\n")
    return wrapper


def make_build_runner_simple_project(root: Path, *, mode: str = "success") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write_windows_wrapper(root, mode)
    _write(root / "settings.gradle.kts", 'rootProject.name = "build-simple"\n')
    _write(root / "build.gradle.kts", 'plugins { id("fabric-loom") version "1.8-SNAPSHOT" }\n')
    _write(
        root / "gradle.properties",
        "\n".join(
            [
                "minecraft_version=1.20.1",
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
  "id": "buildsimple",
  "version": "1.0.0",
  "environment": "*"
}
""".strip()
        + "\n",
    )
    return root


def make_build_runner_multimodule_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write_windows_wrapper(root, "success")
    _write(root / "settings.gradle.kts", 'include(":mod-a", ":lib")\n')
    _write(root / "mod-a" / "build.gradle.kts", 'plugins { id("fabric-loom") }\n')
    _write(
        root / "mod-a" / "src" / "main" / "resources" / "fabric.mod.json",
        '{ "schemaVersion": 1, "id": "moda", "version": "1.0.0", "environment": "*" }\n',
    )
    _write(root / "lib" / "build.gradle.kts", 'plugins { java }\n')
    return root
