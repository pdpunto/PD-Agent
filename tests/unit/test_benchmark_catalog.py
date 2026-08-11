from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pd_agent.benchmark import (
    BenchmarkAcceptanceSpec,
    BenchmarkCatalog,
    BenchmarkCatalogError,
    BenchmarkDataset,
    BenchmarkEnvironmentRequirements,
    BenchmarkFixtureReference,
    BenchmarkTask,
    BenchmarkTaskReference,
    BenchmarkValidationRequirements,
    FIXTURE_IDENTITY_ALGORITHM,
    compute_fixture_identity,
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _fixture_root(root: Path) -> Path:
    fixture = root / "fixtures" / "fixture-a"
    (fixture / "src" / "main" / "java" / "dev" / "pdpunto").mkdir(parents=True, exist_ok=True)
    (fixture / "src" / "main" / "java" / "dev" / "pdpunto" / "Example.java").write_text(
        "package dev.pdpunto;\nclass Example {}\n",
        encoding="utf-8",
    )
    (fixture / "build" / "ignored.txt").parent.mkdir(parents=True, exist_ok=True)
    (fixture / "build" / "ignored.txt").write_text("ignored", encoding="utf-8")
    (fixture / ".gradle" / "cache.bin").parent.mkdir(parents=True, exist_ok=True)
    (fixture / ".gradle" / "cache.bin").write_text("ignored", encoding="utf-8")
    return fixture


def _task_manifest(root: Path, *, fixture_ref: str, fixture_identity: str | None = None) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="task-a",
        task_version="1",
        description="registry lookup",
        prompt="Do the registry lookup.",
        fixture=BenchmarkFixtureReference(
            fixture_ref=fixture_ref,
            fixture_identity=fixture_identity,
            identity_algorithm=FIXTURE_IDENTITY_ALGORITHM,
            metadata={"origin": "test"},
        ),
        validation=BenchmarkValidationRequirements(build=True, artifact=True, minecraft=True, source_change=True),
        acceptance=BenchmarkAcceptanceSpec(
            acceptance_type="minecraft_harness",
            spec={"kind": "registry"},
        ),
        environment=BenchmarkEnvironmentRequirements(
            minecraft_version="1.21.11",
            loader_version="0.19.3",
            loom_version="1.13.3",
            yarn_version="1.21.11+build.6",
            java_version="21",
        ),
    )


def _dataset_manifest() -> BenchmarkDataset:
    return BenchmarkDataset(
        dataset_id="dataset-a",
        dataset_version="1",
        tasks=(BenchmarkTaskReference(task_id="task-a", task_version="1"),),
        description="catalog test",
        tags=("fabric",),
    )


def test_load_catalog_valid_manifest_and_fixture_identity(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    fixture = _fixture_root(root)
    fixture_hash = compute_fixture_identity(fixture)

    dataset_path = _write_json(root / "datasets" / "dataset-a.json", _dataset_manifest().to_dict())
    task_path = _write_json(
        root / "tasks" / "task-a.json",
        _task_manifest(root, fixture_ref="fixtures/fixture-a", fixture_identity=fixture_hash).to_dict(),
    )

    catalog = BenchmarkCatalog.load(root)

    assert catalog.root == root.resolve()
    assert catalog.datasets == (BenchmarkDataset.from_dict(json.loads(dataset_path.read_text(encoding="utf-8"))),)
    assert catalog.tasks == (BenchmarkTask.from_dict(json.loads(task_path.read_text(encoding="utf-8"))),)
    assert catalog.dataset_for("dataset-a", "1").dataset_id == "dataset-a"
    assert catalog.task_for("task-a", "1").fixture.fixture_ref == "fixtures/fixture-a"
    assert catalog.fixture_paths[("task-a", "1")] == fixture.resolve()
    assert catalog.fixture_identities[("task-a", "1")] == fixture_hash


def test_invalid_schema_rejected(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    _fixture_root(root)
    _write_json(root / "datasets" / "dataset-a.json", {"schema_version": 2, "dataset_id": "dataset-a"})
    _write_json(
        root / "tasks" / "task-a.json",
        _task_manifest(root, fixture_ref="fixtures/fixture-a").to_dict(),
    )

    with pytest.raises(BenchmarkCatalogError, match="invalid dataset schema"):
        BenchmarkCatalog.load(root)


def test_dataset_references_missing_task(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    _fixture_root(root)
    _write_json(root / "datasets" / "dataset-a.json", _dataset_manifest().to_dict())
    task = _task_manifest(root, fixture_ref="fixtures/fixture-a")
    task = BenchmarkTask.from_dict({**task.to_dict(), "task_id": "task-b"})
    _write_json(root / "tasks" / "task-b.json", task.to_dict())

    with pytest.raises(BenchmarkCatalogError, match="references missing task"):
        BenchmarkCatalog.load(root)


def test_duplicate_dataset_ids_rejected(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    fixture = _fixture_root(root)
    fixture_hash = compute_fixture_identity(fixture)
    _write_json(root / "datasets" / "dataset-a.json", _dataset_manifest().to_dict())
    _write_json(root / "datasets" / "dup" / "dataset-a.json", _dataset_manifest().to_dict())
    _write_json(
        root / "tasks" / "task-a.json",
        _task_manifest(root, fixture_ref="fixtures/fixture-a", fixture_identity=fixture_hash).to_dict(),
    )
    _write_json(
        root / "tasks" / "dup" / "task-a.json",
        _task_manifest(root, fixture_ref="fixtures/fixture-a", fixture_identity=fixture_hash).to_dict(),
    )

    with pytest.raises(BenchmarkCatalogError, match="duplicate dataset manifest"):
        BenchmarkCatalog.load(root)


def test_duplicate_task_ids_rejected(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    fixture = _fixture_root(root)
    fixture_hash = compute_fixture_identity(fixture)
    _write_json(root / "datasets" / "dataset-a.json", _dataset_manifest().to_dict())
    _write_json(
        root / "tasks" / "task-a.json",
        _task_manifest(root, fixture_ref="fixtures/fixture-a", fixture_identity=fixture_hash).to_dict(),
    )
    _write_json(
        root / "tasks" / "dup" / "task-a.json",
        _task_manifest(root, fixture_ref="fixtures/fixture-a", fixture_identity=fixture_hash).to_dict(),
    )

    with pytest.raises(BenchmarkCatalogError, match="duplicate task manifest"):
        BenchmarkCatalog.load(root)


def test_fixture_missing_or_outside_root_rejected(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    _fixture_root(root)
    _write_json(root / "datasets" / "dataset-a.json", _dataset_manifest().to_dict())
    _write_json(
        root / "tasks" / "task-a.json",
        _task_manifest(root, fixture_ref="../outside-fixture").to_dict(),
    )

    with pytest.raises(BenchmarkCatalogError, match="invalid fixture reference"):
        BenchmarkCatalog.load(root)


def test_fixture_nonexistent_rejected(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    _fixture_root(root)
    _write_json(root / "datasets" / "dataset-a.json", _dataset_manifest().to_dict())
    _write_json(
        root / "tasks" / "task-a.json",
        _task_manifest(root, fixture_ref="fixtures/missing").to_dict(),
    )

    with pytest.raises(BenchmarkCatalogError, match="invalid fixture reference"):
        BenchmarkCatalog.load(root)


def test_invalid_json_rejected(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    _fixture_root(root)
    _write_json(root / "datasets" / "dataset-a.json", _dataset_manifest().to_dict())
    (root / "tasks" / "task-a.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "tasks" / "task-a.json").write_text("{ invalid json", encoding="utf-8")

    with pytest.raises(BenchmarkCatalogError, match="invalid JSON"):
        BenchmarkCatalog.load(root)
