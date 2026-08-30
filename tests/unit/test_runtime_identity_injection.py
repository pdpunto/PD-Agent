from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import pd_agent.runtime.controller as controller_module
from pd_agent.core import RunStateError, RunStatus
from pd_agent.project import ProjectInspectionStatus
from pd_agent.reporting import FinalReport, RunStorage
from pd_agent.runtime import RunController


class _FakeRuntime:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def run(self, *, run_state, **_kwargs):  # noqa: ANN001
        for state in (
            RunStatus.PLANNING,
            RunStatus.EDITING,
            RunStatus.BUILDING,
            RunStatus.VALIDATING_ARTIFACT,
            RunStatus.REPORTING,
            RunStatus.COMPLETED,
        ):
            run_state.transition_to(state)
        return run_state, FinalReport(
            run_id=run_state.run_id,
            final_state=run_state.state,
            summary="fake completed run",
        )


class _FakeInspector:
    def inspect(self, _project_root: Path):
        return SimpleNamespace(status=ProjectInspectionStatus.READY, issues=())


def _controller(tmp_path: Path) -> tuple[RunController, RunStorage]:
    storage = RunStorage(tmp_path / "runs")
    controller = RunController(
        provider=object(),
        storage=storage,
        build_runner=object(),
        artifact_validator=object(),
        context_manager=object(),
        project_inspector=_FakeInspector(),
    )
    return controller, storage


def test_optional_injected_identity_is_used_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(controller_module, "AgentRuntime", _FakeRuntime)
    controller, storage = _controller(tmp_path)
    supplied = uuid4()

    state, report = controller.run(tmp_path, "identity", run_id=supplied)

    assert state.run_id == str(supplied)
    assert report.run_id == str(supplied)
    paths = storage.paths_for(str(supplied))
    assert paths.run_dir == storage.storage_root / str(supplied)
    assert json.loads(paths.run_json.read_text(encoding="utf-8"))["run_id"] == str(supplied)
    assert all(event.run_id == str(supplied) for event in storage.read_events(str(supplied)))
    evidence = storage.store_large_payload(str(supplied), "identity", {"run_id": str(supplied)})
    assert evidence.parent == paths.evidence_dir


def test_missing_identity_preserves_generated_uuid4_behavior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(controller_module, "AgentRuntime", _FakeRuntime)
    controller, storage = _controller(tmp_path)

    first, _ = controller.run(tmp_path, "generated one")
    second, _ = controller.run(tmp_path, "generated two")

    assert UUID(first.run_id).version == 4
    assert UUID(second.run_id).version == 4
    assert first.run_id != second.run_id
    assert storage.paths_for(first.run_id).run_json.exists()
    assert storage.paths_for(second.run_id).run_json.exists()


@pytest.mark.parametrize("value", ["not-a-uuid", "00000000-0000-0000-0000-000000000000", "../unsafe"])
def test_malformed_or_wrong_version_identity_fails_closed(tmp_path: Path, value: str) -> None:
    controller, _ = _controller(tmp_path)
    with pytest.raises(RunStateError, match="UUIDv4"):
        controller.run(tmp_path, "invalid", run_id=value)


def test_existing_identity_is_rejected_without_overwrite(tmp_path: Path) -> None:
    controller, storage = _controller(tmp_path)
    supplied = str(uuid4())
    run_root = storage.storage_root / supplied
    run_root.mkdir(parents=True)
    sentinel = run_root / "sentinel.txt"
    sentinel.write_text("previous evidence", encoding="utf-8")

    with pytest.raises(RunStateError, match="already exists"):
        controller.run(tmp_path, "collision", run_id=supplied)

    assert sentinel.read_text(encoding="utf-8") == "previous evidence"
    assert not (run_root / "events.jsonl").exists()
    assert not (run_root / "run.json").exists()
