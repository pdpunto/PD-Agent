"""Canonical benchmark fixture identity and disposable workspace handling."""

from __future__ import annotations

import hashlib
import os
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

LEGACY_FIXTURE_IDENTITY_ALGORITHM = "sha256-tree-v1"
FIXTURE_IDENTITY_ALGORITHM = "sha256-tree-v2"
SUPPORTED_FIXTURE_IDENTITY_ALGORITHMS = frozenset(
    {LEGACY_FIXTURE_IDENTITY_ALGORITHM, FIXTURE_IDENTITY_ALGORITHM}
)
_TEXT_FIXTURE_SUFFIXES = frozenset(
    {
        ".bat", ".cmd", ".gradle", ".java", ".json", ".kts", ".md",
        ".properties", ".sh", ".txt", ".xml", ".yaml", ".yml",
    }
)
_TEXT_FIXTURE_FILENAMES = frozenset({"gradlew"})
VALID_BENCHMARK_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


class BenchmarkWorkspaceError(ValueError):
    """Raised when benchmark workspace preparation fails."""


def _validate_benchmark_id(value: object, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise BenchmarkWorkspaceError(f"{field_name} must not be empty")
    if text in {".", ".."}:
        raise BenchmarkWorkspaceError(f"{field_name} must not be a path segment")
    separators = {"/", "\\", os.sep}
    if os.altsep:
        separators.add(os.altsep)
    if any(sep in text for sep in separators):
        raise BenchmarkWorkspaceError(f"{field_name} must not contain path separators")
    if text.startswith(".") or text.endswith("."):
        raise BenchmarkWorkspaceError(f"{field_name} must not start or end with dot")
    if any(char not in VALID_BENCHMARK_ID_CHARS for char in text):
        raise BenchmarkWorkspaceError(f"{field_name} contains unsafe characters")
    return text


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


def _validate_identity_algorithm(algorithm: str | None) -> str:
    selected = (algorithm or FIXTURE_IDENTITY_ALGORITHM).casefold()
    if selected not in SUPPORTED_FIXTURE_IDENTITY_ALGORITHMS:
        raise BenchmarkWorkspaceError(f"unsupported fixture identity algorithm: {algorithm}")
    return selected


def _canonical_file_bytes(relative_path: Path, file_path: Path, *, algorithm: str) -> bytes:
    content = file_path.read_bytes()
    if algorithm == LEGACY_FIXTURE_IDENTITY_ALGORITHM:
        return content
    if relative_path.name.casefold() in _TEXT_FIXTURE_FILENAMES or relative_path.suffix.casefold() in _TEXT_FIXTURE_SUFFIXES:
        return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return content


def compute_fixture_identity(fixture_root: Path, *, algorithm: str | None = None) -> str:
    """Compute SHA-256 over a fixture tree using an explicit identity policy."""

    root = Path(fixture_root).resolve(strict=True)
    if not root.is_dir():
        raise BenchmarkWorkspaceError("fixture root must be an existing directory")

    selected_algorithm = _validate_identity_algorithm(algorithm)
    hasher = hashlib.sha256()
    for relative_path, file_path in _iter_canonical_files(root):
        hasher.update(relative_path.as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(_canonical_file_bytes(relative_path, file_path, algorithm=selected_algorithm))
        hasher.update(b"\0")
    return hasher.hexdigest()


def _workspace_root_for(benchmark_root: Path, run_id: str, attempt_id: str) -> Path:
    benchmark_root = Path(benchmark_root).resolve(strict=True)
    return benchmark_root / "workspaces" / _validate_benchmark_id(run_id, field_name="run_id") / _validate_benchmark_id(
        attempt_id, field_name="attempt_id"
    )


def _validate_workspace_confinement(benchmark_root: Path, workspace_root: Path) -> Path:
    benchmark_root = Path(benchmark_root).resolve(strict=True)
    allowed_root = (benchmark_root / "workspaces").resolve(strict=False)
    candidate = Path(workspace_root).resolve(strict=False)
    if candidate == benchmark_root:
        raise BenchmarkWorkspaceError("workspace_root cannot equal benchmark_root")
    if candidate == allowed_root:
        raise BenchmarkWorkspaceError("workspace_root cannot equal workspaces root")
    try:
        candidate.relative_to(allowed_root)
    except ValueError as exc:
        raise BenchmarkWorkspaceError("workspace_root escapes benchmark_root/workspaces") from exc
    return candidate


def _expected_workspace_root(benchmark_root: Path, run_id: str, attempt_id: str, fixture_name: str) -> Path:
    return _workspace_root_for(benchmark_root, run_id, attempt_id) / _validate_benchmark_id(
        fixture_name, field_name="fixture_name"
    )


def _validate_workspace_identity(
    *,
    benchmark_root: Path,
    workspace_root: Path,
    run_id: str,
    attempt_id: str,
    fixture_name: str,
) -> Path:
    expected = _expected_workspace_root(benchmark_root, run_id, attempt_id, fixture_name).resolve(strict=False)
    candidate = _validate_workspace_confinement(benchmark_root, workspace_root)
    if candidate != expected:
        raise BenchmarkWorkspaceError(
            f"workspace_root does not match expected identity path: expected {expected}, got {candidate}"
        )
    return candidate


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
    identity_algorithm: str = FIXTURE_IDENTITY_ALGORITHM
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    preserve_on_cleanup: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_root", Path(self.benchmark_root).resolve(strict=True))
        object.__setattr__(self, "source_fixture", Path(self.source_fixture).resolve(strict=True))
        object.__setattr__(self, "canonical_hash_before", str(self.canonical_hash_before))
        object.__setattr__(self, "workspace_hash_initial", str(self.workspace_hash_initial))
        object.__setattr__(self, "run_id", str(self.run_id).strip())
        object.__setattr__(self, "attempt_id", str(self.attempt_id).strip())
        object.__setattr__(self, "identity_algorithm", _validate_identity_algorithm(self.identity_algorithm))
        _validate_benchmark_id(self.run_id, field_name="run_id")
        _validate_benchmark_id(self.attempt_id, field_name="attempt_id")
        object.__setattr__(
            self,
            "workspace_root",
            _validate_workspace_identity(
                benchmark_root=self.benchmark_root,
                workspace_root=Path(self.workspace_root),
                run_id=self.run_id,
                attempt_id=self.attempt_id,
                fixture_name=self.source_fixture.name,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_root": str(self.benchmark_root),
            "source_fixture": str(self.source_fixture),
            "canonical_hash_before": self.canonical_hash_before,
            "workspace_root": str(self.workspace_root),
            "workspace_hash_initial": self.workspace_hash_initial,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "identity_algorithm": self.identity_algorithm,
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
            identity_algorithm=str(data.get("identity_algorithm", LEGACY_FIXTURE_IDENTITY_ALGORITHM)),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            preserve_on_cleanup=bool(data.get("preserve_on_cleanup", False)),
        )

    def cleanup(self) -> None:
        if self.preserve_on_cleanup:
            return
        workspace_root = _validate_workspace_identity(
            benchmark_root=self.benchmark_root,
            workspace_root=self.workspace_root,
            run_id=self.run_id,
            attempt_id=self.attempt_id,
            fixture_name=self.source_fixture.name,
        )
        if not workspace_root.exists():
            return
        shutil.rmtree(workspace_root, ignore_errors=False)


def prepare_workspace(
    source_fixture: Path,
    benchmark_root: Path,
    *,
    run_id: str,
    attempt_id: str,
    preserve_on_cleanup: bool = False,
    identity_algorithm: str = FIXTURE_IDENTITY_ALGORITHM,
) -> BenchmarkWorkspace:
    """Copy canonical fixture into isolated workspace and record hashes."""

    canonical_root = Path(source_fixture).resolve(strict=True)
    if not canonical_root.is_dir():
        raise BenchmarkWorkspaceError("source fixture must be an existing directory")

    benchmark_root = Path(benchmark_root).resolve(strict=True)
    if not benchmark_root.is_dir():
        raise BenchmarkWorkspaceError("benchmark_root must be an existing directory")

    selected_algorithm = _validate_identity_algorithm(identity_algorithm)
    canonical_hash = compute_fixture_identity(canonical_root, algorithm=selected_algorithm)
    validated_run_id = _validate_benchmark_id(run_id, field_name="run_id")
    validated_attempt_id = _validate_benchmark_id(attempt_id, field_name="attempt_id")
    workspace_root = _expected_workspace_root(
        benchmark_root,
        validated_run_id,
        validated_attempt_id,
        canonical_root.name,
    ).resolve(strict=False)
    if workspace_root.exists():
        raise BenchmarkWorkspaceError(f"workspace already exists for run_id={validated_run_id!r} attempt_id={validated_attempt_id!r}")
    workspace_root.parent.mkdir(parents=True, exist_ok=True)
    _copy_canonical_tree(canonical_root, workspace_root)
    workspace_hash = compute_fixture_identity(workspace_root, algorithm=selected_algorithm)
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
        identity_algorithm=selected_algorithm,
        preserve_on_cleanup=preserve_on_cleanup,
    )
