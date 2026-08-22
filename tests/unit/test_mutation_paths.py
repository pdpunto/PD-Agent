from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_agent.benchmark.executor import _task_mutation_targets
from pd_agent.benchmark.models import BenchmarkTask
from pd_agent.core import RunState
from pd_agent.project import (
    MutationPathResolutionError,
    ProjectInspectionStatus,
    ProjectSnapshot,
    resolve_logical_resource_path,
)


def _snapshot(root: Path, *resource_roots: Path) -> ProjectSnapshot:
    return ProjectSnapshot(
        project_root=root,
        status=ProjectInspectionStatus.READY,
        resource_roots=tuple(resource_roots),
        target_subproject=root,
    )


def test_logical_assets_and_data_paths_resolve_to_physical_project_paths(tmp_path: Path) -> None:
    root = tmp_path / "project"
    snapshot = _snapshot(root, root / "src/main/resources")

    assert resolve_logical_resource_path(snapshot, "assets/examplemod/lang/en_us.json") == (
        "src/main/resources/assets/examplemod/lang/en_us.json"
    )
    assert resolve_logical_resource_path(snapshot, "data/examplemod/recipe/server_core.json") == (
        "src/main/resources/data/examplemod/recipe/server_core.json"
    )


@pytest.mark.parametrize("logical_path", ["/assets/examplemod/lang/en_us.json", "../outside.json", "assets\\bad.json"])
def test_logical_resource_paths_reject_unsafe_forms(tmp_path: Path, logical_path: str) -> None:
    root = tmp_path / "project"
    snapshot = _snapshot(root, root / "src/main/resources")

    with pytest.raises(MutationPathResolutionError):
        resolve_logical_resource_path(snapshot, logical_path)


def test_resource_root_outside_project_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "project"
    snapshot = _snapshot(root, tmp_path / "outside/resources")

    with pytest.raises(MutationPathResolutionError):
        resolve_logical_resource_path(snapshot, "assets/examplemod/lang/en_us.json")


def test_ambiguous_resource_roots_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    snapshot = _snapshot(root, root / "src/main/resources", root / "src/generated/resources")

    with pytest.raises(MutationPathResolutionError, match="ambiguous"):
        resolve_logical_resource_path(snapshot, "assets/examplemod/lang/en_us.json")


def test_targets_are_canonical_and_survive_state_serialization(tmp_path: Path) -> None:
    root = tmp_path / "project"
    target = resolve_logical_resource_path(_snapshot(root, root / "src/main/resources"), "assets/examplemod/lang/en_us.json")
    state = RunState(project_root=root, task="resource")
    state.set_pending_mutation_targets((target,))
    state.record_completed_mutation_target(target)

    restored = RunState.from_dict(state.to_dict())
    assert restored.pending_mutation_targets == ()
    assert restored.completed_mutation_targets == (target,)


def test_real_f6_t2_and_t3_metadata_produces_physical_targets() -> None:
    root = Path("benchmarks/projects/v0_5_fabric_base").resolve()
    snapshot = ProjectSnapshot(
        project_root=root,
        status=ProjectInspectionStatus.READY,
        resource_roots=(root / "src/main/resources",),
        target_subproject=root,
    )

    tasks = {
        task_id: BenchmarkTask.from_dict(
            json.loads(Path(f"benchmarks/tasks/{task_id}-v5.json").read_text(encoding="utf-8"))
        )
        for task_id in ("F6-T1", "F6-T2", "F6-T3")
    }
    assert _task_mutation_targets(tasks["F6-T1"], snapshot) == ("role:source",)
    assert _task_mutation_targets(tasks["F6-T2"], snapshot) == (
        "role:source",
        "src/main/resources/assets/examplemod/lang/en_us.json",
    )
    assert _task_mutation_targets(tasks["F6-T3"], snapshot) == (
        "role:source",
        "src/main/resources/assets/examplemod/lang/en_us.json",
        "src/main/resources/data/examplemod/recipe/server_core.json",
    )
