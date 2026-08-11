"""Canonical benchmark fixture identity and disposable workspace handling."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


IGNORED_FIXTURE_DIRS = {
    ".git",
    ".gradle",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vs",
    "__pycache__",
    "bin",
    "build",
    "dist",
    "evidence",
    "out",
    "runs",
    "target",
}

IGNORED_FIXTURE_FILES = {
    ".ds_store",
    "thumbs.db",
}

FIXTURE_IDENTITY_ALGORITHM = "sha256-tree-v1"


class BenchmarkWorkspaceError(ValueError):
    """Raised when benchmark workspace preparation fails."""


def _safe_segment(value: object) -> str:
    text = str(value).strip().casefold()
    cleaned = [char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text]
    segment = "".join(cleaned).strip("._-")
    return segment or "unknown"


def _is_ignored_dir(name: str) -> bool:
    return name.casefold() in {item.casefold() for item in IGNORED_FIXTURE_DIRS}


def _is_ignored_file(name: str) -> bool:
    return name.casefold() in IGNORED_FIXTURE_FILES


def _iter_canonical_files(root: Path) -> Iterator[tuple[Path, Path]]:
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(dirnames, key=str.casefold)
        for dirname in dirnames:
            candidate = current_path / dirname
            if candidate.is_symlink():
                raise BenchmarkWorkspaceError(f"symlink not allowed in benchmark fixture: {candidate}")
        dirnames[:] = [dirname for dirname in dirnames if not _is_ignored_dir(dirname)]

        for filename in sorted(filenames, key=str.casefold):
            if _is_ignored_file(filename):
                continue
            candidate = current_path / filename
            if candidate.is_symlink():
                raise BenchmarkWorkspaceError(f"symlink not allowed in benchmark fixture: {candidate}")
            if not candidate.is_file():
                continue
            yield candidate.relative_to(root), candidate


def compute_fixture_identity(fixture_root: Path) -> str:
    """Compute canonical SHA-256 over source files in a fixture tree."""

    root = Path(fixture_root).resolve(strict=True)
    if not root.is_dir():
        raise BenchmarkWorkspaceError("fixture root must be an existing directory")

    hasher = hashlib.sha256()
    for relative_path, file_path in _iter_canonical_files(root):
        hasher.update(relative_path.as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(file_path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _copy_canonical_tree(source_root: Path, destination_root: Path) -> None:
    destination_root.mkdir(parents=True, exist_ok=True)
    for relative_path, file_path in _iter_canonical_files(source_root):
        target = destination_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target)


@dataclass(frozen=True, slots=True)
class BenchmarkWorkspace:
    """Disposable benchmark workspace plus identity metadata."""

    benchmark_root: Path
    source_fixture: Path
    canonical_hash_before: str
    workspace_root: Path
    workspace_hash_initial: str
    run_id: str
    attempt_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    preserve_on_cleanup: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_root", Path(self.benchmark_root).resolve(strict=True))
        object.__setattr__(self, "source_fixture", Path(self.source_fixture).resolve(strict=True))
        object.__setattr__(self, "workspace_root", Path(self.workspace_root).resolve(strict=False))
        object.__setattr__(self, "canonical_hash_before", str(self.canonical_hash_before))
        object.__setattr__(self, "workspace_hash_initial", str(self.workspace_hash_initial))
        object.__setattr__(self, "run_id", str(self.run_id).strip())
        object.__setattr__(self, "attempt_id", str(self.attempt_id).strip())
        if not self.run_id:
            raise BenchmarkWorkspaceError("run_id must not be empty")
        if not self.attempt_id:
            raise BenchmarkWorkspaceError("attempt_id must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_root": str(self.benchmark_root),
            "source_fixture": str(self.source_fixture),
            "canonical_hash_before": self.canonical_hash_before,
            "workspace_root": str(self.workspace_root),
            "workspace_hash_initial": self.workspace_hash_initial,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "created_at": self.created_at.isoformat(),
            "preserve_on_cleanup": self.preserve_on_cleanup,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkWorkspace":
        return cls(
            benchmark_root=Path(data["benchmark_root"]),
            source_fixture=Path(data["source_fixture"]),
            canonical_hash_before=str(data["canonical_hash_before"]),
            workspace_root=Path(data["workspace_root"]),
            workspace_hash_initial=str(data["workspace_hash_initial"]),
            run_id=str(data["run_id"]),
            attempt_id=str(data["attempt_id"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            preserve_on_cleanup=bool(data.get("preserve_on_cleanup", False)),
        )

    def cleanup(self) -> None:
        if self.preserve_on_cleanup:
            return
        shutil.rmtree(self.workspace_root, ignore_errors=True)


def prepare_workspace(
    source_fixture: Path,
    benchmark_root: Path,
    *,
    run_id: str,
    attempt_id: str,
    preserve_on_cleanup: bool = False,
) -> BenchmarkWorkspace:
    """Copy canonical fixture into isolated workspace and record hashes."""

    canonical_root = Path(source_fixture).resolve(strict=True)
    if not canonical_root.is_dir():
        raise BenchmarkWorkspaceError("source fixture must be an existing directory")

    benchmark_root = Path(benchmark_root).resolve(strict=True)
    if not benchmark_root.is_dir():
        raise BenchmarkWorkspaceError("benchmark_root must be an existing directory")

    canonical_hash = compute_fixture_identity(canonical_root)
    workspace_root = (
        benchmark_root
        / "workspaces"
        / _safe_segment(run_id)
        / f"{_safe_segment(attempt_id)}-{_safe_segment(canonical_root.name)}"
    )
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    workspace_root.parent.mkdir(parents=True, exist_ok=True)
    _copy_canonical_tree(canonical_root, workspace_root)
    workspace_hash = compute_fixture_identity(workspace_root)
    if workspace_hash != canonical_hash:
        raise BenchmarkWorkspaceError("workspace copy does not match canonical fixture")

    return BenchmarkWorkspace(
        benchmark_root=benchmark_root,
        source_fixture=canonical_root,
        canonical_hash_before=canonical_hash,
        workspace_root=workspace_root,
        workspace_hash_initial=workspace_hash,
        run_id=run_id,
        attempt_id=attempt_id,
        preserve_on_cleanup=preserve_on_cleanup,
    )
