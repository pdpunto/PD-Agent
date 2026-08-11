"""Benchmark dataset and task catalog loading."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from pd_agent.core import SecurityViolation, ToolExecutionError, ToolValidationError
from pd_agent.tools import SecurePathResolver

from .models import BenchmarkDataset, BenchmarkSchemaError, BenchmarkTask, BenchmarkTaskReference
from .workspace import FIXTURE_IDENTITY_ALGORITHM, BenchmarkWorkspaceError, compute_fixture_identity


class BenchmarkCatalogError(ValueError):
    """Raised when benchmark catalog loading or validation fails."""


def _is_ignored_dir(name: str) -> bool:
    from .workspace import IGNORED_FIXTURE_DIRS

    return name.casefold() in {item.casefold() for item in IGNORED_FIXTURE_DIRS}


def _manifest_files(root: Path, subdir: str) -> tuple[Path, ...]:
    base = root / subdir
    if not base.exists():
        return ()
    if not base.is_dir():
        raise BenchmarkCatalogError(f"catalog path is not a directory: {base}")

    files: list[Path] = []
    for current, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(dirnames, key=str.casefold)
        for dirname in dirnames:
            candidate = current_path / dirname
            if candidate.is_symlink():
                raise BenchmarkCatalogError(f"symlink not allowed in catalog tree: {candidate}")
        dirnames[:] = [dirname for dirname in dirnames if not _is_ignored_dir(dirname)]
        for filename in sorted(filenames, key=str.casefold):
            candidate = current_path / filename
            if candidate.is_symlink():
                raise BenchmarkCatalogError(f"symlink not allowed in catalog tree: {candidate}")
            if candidate.suffix.casefold() != ".json":
                continue
            if not candidate.is_file():
                continue
            files.append(candidate)
    return tuple(sorted(files, key=lambda path: str(path).casefold()))


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BenchmarkCatalogError(f"invalid JSON in {path}: {exc.msg}") from exc
    if not isinstance(data, Mapping):
        raise BenchmarkCatalogError(f"manifest must be an object: {path}")
    return data


def _load_dataset(path: Path) -> BenchmarkDataset:
    try:
        return BenchmarkDataset.from_dict(_load_json(path))
    except BenchmarkSchemaError as exc:
        raise BenchmarkCatalogError(f"invalid dataset schema in {path}: {exc}") from exc


def _load_task(path: Path) -> BenchmarkTask:
    try:
        return BenchmarkTask.from_dict(_load_json(path))
    except BenchmarkSchemaError as exc:
        raise BenchmarkCatalogError(f"invalid task schema in {path}: {exc}") from exc


def _key(item_id: str, version: str) -> tuple[str, str]:
    return item_id, version


@dataclass(frozen=True, slots=True)
class BenchmarkCatalog:
    """Loaded benchmark catalog with resolved references."""

    root: Path
    datasets: tuple[BenchmarkDataset, ...]
    tasks: tuple[BenchmarkTask, ...]
    dataset_paths: Mapping[tuple[str, str], Path] = field(default_factory=dict)
    task_paths: Mapping[tuple[str, str], Path] = field(default_factory=dict)
    fixture_paths: Mapping[tuple[str, str], Path] = field(default_factory=dict)
    fixture_identities: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).resolve(strict=True))
        object.__setattr__(self, "datasets", tuple(self.datasets))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "dataset_paths", dict(self.dataset_paths))
        object.__setattr__(self, "task_paths", dict(self.task_paths))
        object.__setattr__(self, "fixture_paths", dict(self.fixture_paths))
        object.__setattr__(self, "fixture_identities", dict(self.fixture_identities))

    @classmethod
    def load(cls, root: Path) -> "BenchmarkCatalog":
        benchmark_root = Path(root).resolve(strict=True)
        if not benchmark_root.is_dir():
            raise BenchmarkCatalogError("benchmark root must be an existing directory")

        resolver = SecurePathResolver(benchmark_root)
        dataset_paths = _manifest_files(benchmark_root, "datasets")
        task_paths = _manifest_files(benchmark_root, "tasks")
        if not dataset_paths:
            raise BenchmarkCatalogError("no dataset manifests found")
        if not task_paths:
            raise BenchmarkCatalogError("no task manifests found")

        datasets: list[BenchmarkDataset] = []
        tasks: list[BenchmarkTask] = []
        dataset_index: dict[tuple[str, str], BenchmarkDataset] = {}
        dataset_path_index: dict[tuple[str, str], Path] = {}
        task_index: dict[tuple[str, str], BenchmarkTask] = {}
        task_path_index: dict[tuple[str, str], Path] = {}
        task_refs_by_dataset: dict[tuple[str, str], tuple[BenchmarkTaskReference, ...]] = {}
        fixture_paths: dict[tuple[str, str], Path] = {}
        fixture_identities: dict[tuple[str, str], str] = {}

        for path in dataset_paths:
            dataset = _load_dataset(path)
            key = _key(dataset.dataset_id, dataset.dataset_version)
            if key in dataset_index:
                raise BenchmarkCatalogError(f"duplicate dataset manifest: {dataset.dataset_id}@{dataset.dataset_version}")
            dataset_index[key] = dataset
            dataset_path_index[key] = path
            task_refs_by_dataset[key] = dataset.tasks
            datasets.append(dataset)

        for path in task_paths:
            task = _load_task(path)
            key = _key(task.task_id, task.task_version)
            if key in task_index:
                raise BenchmarkCatalogError(f"duplicate task manifest: {task.task_id}@{task.task_version}")
            task_index[key] = task
            task_path_index[key] = path
            tasks.append(task)

            try:
                fixture_path = resolver.resolve_existing_directory(task.fixture.fixture_ref)
                fixture_hash = compute_fixture_identity(fixture_path)
            except (BenchmarkWorkspaceError, SecurityViolation, ToolExecutionError, ToolValidationError) as exc:
                raise BenchmarkCatalogError(f"invalid fixture reference for {path}: {exc}") from exc
            if task.fixture.identity_algorithm is not None and task.fixture.identity_algorithm.casefold() != FIXTURE_IDENTITY_ALGORITHM:
                raise BenchmarkCatalogError(
                    f"unsupported fixture identity algorithm for {path}: {task.fixture.identity_algorithm}"
                )
            if task.fixture.fixture_identity is not None and task.fixture.fixture_identity != fixture_hash:
                raise BenchmarkCatalogError(
                    f"fixture identity mismatch for {path}: expected {task.fixture.fixture_identity}, got {fixture_hash}"
                )
            fixture_paths[key] = fixture_path
            fixture_identities[key] = fixture_hash

        for dataset_key, references in task_refs_by_dataset.items():
            for reference in references:
                if _key(reference.task_id, reference.task_version) not in task_index:
                    raise BenchmarkCatalogError(
                        f"dataset {dataset_key[0]}@{dataset_key[1]} references missing task {reference.task_id}@{reference.task_version}"
                    )

        return cls(
            root=benchmark_root,
            datasets=tuple(sorted(datasets, key=lambda item: _key(item.dataset_id, item.dataset_version))),
            tasks=tuple(sorted(tasks, key=lambda item: _key(item.task_id, item.task_version))),
            dataset_paths=dataset_path_index,
            task_paths=task_path_index,
            fixture_paths=fixture_paths,
            fixture_identities=fixture_identities,
        )

    def dataset_for(self, dataset_id: str, dataset_version: str) -> BenchmarkDataset:
        return self._dataset_index()[_key(dataset_id, dataset_version)]

    def task_for(self, task_id: str, task_version: str) -> BenchmarkTask:
        return self._task_index()[_key(task_id, task_version)]

    def _dataset_index(self) -> dict[tuple[str, str], BenchmarkDataset]:
        return {_key(item.dataset_id, item.dataset_version): item for item in self.datasets}

    def _task_index(self) -> dict[tuple[str, str], BenchmarkTask]:
        return {_key(item.task_id, item.task_version): item for item in self.tasks}
