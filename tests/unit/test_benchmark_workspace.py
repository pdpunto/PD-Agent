from __future__ import annotations

import os
from pathlib import Path

import pytest

from pd_agent.benchmark import (
    BenchmarkWorkspace,
    BenchmarkWorkspaceError,
    compute_fixture_identity,
    prepare_workspace,
)


def _make_fixture(root: Path) -> Path:
    fixture = root / "fixture"
    (fixture / "src" / "main" / "java" / "dev" / "pdpunto").mkdir(parents=True, exist_ok=True)
    (fixture / "src" / "main" / "java" / "dev" / "pdpunto" / "Example.java").write_text(
        "package dev.pdpunto;\nclass Example { String value = \"ok\"; }\n",
        encoding="utf-8",
    )
    (fixture / "build" / "ignored.txt").parent.mkdir(parents=True, exist_ok=True)
    (fixture / "build" / "ignored.txt").write_text("ignored build output", encoding="utf-8")
    (fixture / ".gradle" / "ignored.bin").parent.mkdir(parents=True, exist_ok=True)
    (fixture / ".gradle" / "ignored.bin").write_text("ignored gradle output", encoding="utf-8")
    (fixture / "bin" / "main").mkdir(parents=True, exist_ok=True)
    (fixture / "bin" / "main" / "ignored.class").write_text("ignored class", encoding="utf-8")
    return fixture


def test_same_tree_same_hash_and_creation_order_independent(tmp_path: Path) -> None:
    first = _make_fixture(tmp_path / "first")
    second = tmp_path / "second" / "fixture"
    (second / "src" / "main" / "java" / "dev" / "pdpunto").mkdir(parents=True, exist_ok=True)
    (second / "src" / "main" / "java" / "dev" / "pdpunto" / "Example.java").write_text(
        "package dev.pdpunto;\nclass Example { String value = \"ok\"; }\n",
        encoding="utf-8",
    )
    (second / ".gradle" / "ignored.bin").parent.mkdir(parents=True, exist_ok=True)
    (second / ".gradle" / "ignored.bin").write_text("other ignored output", encoding="utf-8")
    (second / "build" / "ignored.txt").parent.mkdir(parents=True, exist_ok=True)
    (second / "build" / "ignored.txt").write_text("other ignored build output", encoding="utf-8")

    assert compute_fixture_identity(first) == compute_fixture_identity(second)


def test_source_edit_changes_hash(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    before = compute_fixture_identity(fixture)
    source = fixture / "src" / "main" / "java" / "dev" / "pdpunto" / "Example.java"
    source.write_text("package dev.pdpunto;\nclass Example { String value = \"changed\"; }\n", encoding="utf-8")

    after = compute_fixture_identity(fixture)

    assert before != after


def test_ignored_outputs_do_not_change_hash(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    before = compute_fixture_identity(fixture)
    (fixture / "build" / "nested").mkdir(parents=True, exist_ok=True)
    (fixture / "build" / "nested" / "another.txt").write_text("build noise", encoding="utf-8")
    (fixture / ".gradle" / "more.bin").write_text("gradle noise", encoding="utf-8")
    (fixture / "bin" / "main" / "another.class").write_text("bin noise", encoding="utf-8")

    after = compute_fixture_identity(fixture)

    assert before == after


def test_prepare_workspace_creates_isolated_copy_and_round_trip_metadata(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)

    workspace = prepare_workspace(fixture, benchmark_root, run_id="run-1", attempt_id="attempt-1")
    payload = workspace.to_dict()
    restored = BenchmarkWorkspace.from_dict(payload)

    assert restored == workspace
    assert workspace.canonical_hash_before == workspace.workspace_hash_initial
    assert workspace.workspace_root != fixture
    assert workspace.workspace_root.exists()
    assert (workspace.workspace_root / "src" / "main" / "java" / "dev" / "pdpunto" / "Example.java").exists()
    assert not (workspace.workspace_root / "build").exists()
    assert not (workspace.workspace_root / ".gradle").exists()
    assert not (workspace.workspace_root / "bin").exists()

    workspace.cleanup()
    assert not workspace.workspace_root.exists()
    assert compute_fixture_identity(fixture) == workspace.canonical_hash_before


def test_cleanup_revalidates_confinement_and_rejects_exterior_paths(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)
    workspace = prepare_workspace(fixture, benchmark_root, run_id="run-1", attempt_id="attempt-1")

    outside = tmp_path / "outside"
    outside.mkdir()
    object.__setattr__(workspace, "workspace_root", outside)

    with pytest.raises(BenchmarkWorkspaceError, match="escapes benchmark_root/workspaces"):
        workspace.cleanup()
    assert outside.exists()
    assert fixture.exists()


def test_cleanup_rejects_benchmark_root_and_workspaces_root(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)
    workspace = prepare_workspace(fixture, benchmark_root, run_id="run-1", attempt_id="attempt-1")

    with pytest.raises(BenchmarkWorkspaceError, match="cannot equal benchmark_root"):
        BenchmarkWorkspace.from_dict({**workspace.to_dict(), "workspace_root": str(benchmark_root)})
    with pytest.raises(BenchmarkWorkspaceError, match="cannot equal workspaces root"):
        BenchmarkWorkspace.from_dict({**workspace.to_dict(), "workspace_root": str(benchmark_root / "workspaces")})


def test_round_trip_metadata_keeps_valid_cleanup(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)
    workspace = prepare_workspace(fixture, benchmark_root, run_id="run-1", attempt_id="attempt-1")
    restored = BenchmarkWorkspace.from_dict(workspace.to_dict())

    restored.cleanup()
    assert not restored.workspace_root.exists()


def test_two_workspaces_are_isolated_and_source_remains_unchanged(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)

    workspace_a = prepare_workspace(fixture, benchmark_root, run_id="run_a", attempt_id="attempt_1")
    workspace_b = prepare_workspace(fixture, benchmark_root, run_id="run_b", attempt_id="attempt_2")

    assert workspace_a.workspace_root != workspace_b.workspace_root
    source_file_a = workspace_a.workspace_root / "src" / "main" / "java" / "dev" / "pdpunto" / "Example.java"
    source_file_b = workspace_b.workspace_root / "src" / "main" / "java" / "dev" / "pdpunto" / "Example.java"
    source_file_a.write_text("package dev.pdpunto;\nclass Example { String value = \"workspace-a\"; }\n", encoding="utf-8")

    assert source_file_b.read_text(encoding="utf-8") != source_file_a.read_text(encoding="utf-8")
    assert (fixture / "src" / "main" / "java" / "dev" / "pdpunto" / "Example.java").read_text(encoding="utf-8").count("ok") == 1
    assert compute_fixture_identity(fixture) == workspace_a.canonical_hash_before
    assert compute_fixture_identity(workspace_b.workspace_root) == workspace_b.workspace_hash_initial

    workspace_a.cleanup()
    workspace_b.cleanup()
    assert not workspace_a.workspace_root.exists()
    assert not workspace_b.workspace_root.exists()


@pytest.mark.parametrize("run_id", ["run/a", "../x", "run\\a", "run:a", ".", "..", ""])
def test_invalid_run_ids_rejected(tmp_path: Path, run_id: str) -> None:
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)

    with pytest.raises(BenchmarkWorkspaceError):
        prepare_workspace(fixture, benchmark_root, run_id=run_id, attempt_id="attempt_1")


@pytest.mark.parametrize("attempt_id", ["attempt/a", "../x", "attempt\\a", "attempt:a", ".", "..", ""])
def test_invalid_attempt_ids_rejected(tmp_path: Path, attempt_id: str) -> None:
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)

    with pytest.raises(BenchmarkWorkspaceError):
        prepare_workspace(fixture, benchmark_root, run_id="run_1", attempt_id=attempt_id)


def test_valid_ids_remain_distinct(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)

    first = prepare_workspace(fixture, benchmark_root, run_id="run_a", attempt_id="attempt_1")
    second = prepare_workspace(fixture, benchmark_root, run_id="run_b", attempt_id="attempt_1")

    assert first.workspace_root != second.workspace_root
    assert first.workspace_root.name == "fixture"
    assert second.workspace_root.name == "fixture"
    assert first.workspace_root.parent.parent.name == "run_a"
    assert second.workspace_root.parent.parent.name == "run_b"
    first.cleanup()
    second.cleanup()


def test_symlink_escape_rejected_when_supported(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks not supported")

    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    fixture = _make_fixture(benchmark_root)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = fixture / "src" / "main" / "java" / "dev" / "pdpunto" / "escape.txt"

    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable in this environment")

    with pytest.raises(BenchmarkWorkspaceError, match="symlink not allowed"):
        prepare_workspace(fixture, benchmark_root, run_id="run-link", attempt_id="attempt-1")
