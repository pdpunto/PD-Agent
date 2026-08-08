"""Offline artifact fixtures for PD Agent v0.1."""

from __future__ import annotations

import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .build_projects import (
    make_build_runner_multimodule_project,
    make_build_runner_simple_project,
)


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def make_simple_artifact_project(root: Path) -> Path:
    return make_build_runner_simple_project(root, mode="success")


def make_multimodule_artifact_project(root: Path) -> Path:
    return make_build_runner_multimodule_project(root)


def write_jar(
    path: Path,
    *,
    files: Mapping[str, bytes | str],
    mtime: datetime | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as jar:
        for name, data in files.items():
            jar.writestr(name, data)
    if mtime is not None:
        stamp = mtime.timestamp()
        os.utime(path, (stamp, stamp))
    return path


def write_empty_jar(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def write_corrupt_jar(path: Path) -> Path:
    return _write(path, b"not-a-jar")


def write_manifest_jar(
    path: Path,
    *,
    manifest: str,
    extra_files: Mapping[str, bytes | str] | None = None,
    mtime: datetime | None = None,
) -> Path:
    files: dict[str, bytes | str] = {"fabric.mod.json": manifest}
    if extra_files:
        files.update(extra_files)
    return write_jar(path, files=files, mtime=mtime)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def set_mtime(path: Path, moment: datetime) -> None:
    stamp = moment.timestamp()
    os.utime(path, (stamp, stamp))
