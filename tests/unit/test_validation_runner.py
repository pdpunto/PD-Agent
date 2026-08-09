from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest


def _load_runner():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "validation" / "validate_v0_1.py"
    spec = importlib.util.spec_from_file_location("validate_v0_1", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_append_marker_once() -> None:
    runner = _load_runner()
    original = "Line 1\n"
    updated = runner._append_marker(original, "Marker")
    assert "Marker" in updated
    assert runner._append_marker(updated, "Marker") == updated


def test_gradle_build_command_windows_shape() -> None:
    runner = _load_runner()
    command = runner._gradle_build_command(Path(r"C:\\tmp\\copy"), ["build", "--no-daemon"])
    assert command[0] == "cmd"
    assert command[1] == "/c"
    assert command[-2:] == ["build", "--no-daemon"]


def test_prepare_working_copy_ignores_generated_dirs() -> None:
    runner = _load_runner()
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "source"
        validation = Path(temp_dir) / "validation"
        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=source,
            validation_root=validation,
        )
        summary.working_root = validation / "working"
        summary.evidence_root = validation / "evidence"
        (source / "src").mkdir(parents=True)
        (source / ".git").mkdir()
        (source / "build").mkdir()
        (source / "README.md").write_text("hello", encoding="utf-8")
        (source / "src" / "file.txt").write_text("ok", encoding="utf-8")
        (source / "build" / "ignored.txt").write_text("no", encoding="utf-8")
        (source / ".git" / "ignored.txt").write_text("no", encoding="utf-8")

        copied = runner._prepare_working_copy(summary, suffix="copy")
        assert (copied / "README.md").exists()
        assert (copied / "src" / "file.txt").exists()
        assert not (copied / "build").exists()
        assert not (copied / ".git").exists()


def test_prepare_source_edit_uses_java_or_kt_not_markdown() -> None:
    runner = _load_runner()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "README.md").write_text("markdown", encoding="utf-8")
        source = root / "src" / "main" / "java" / "dev" / "pdpunto" / "sample" / "Sample.java"
        source.parent.mkdir(parents=True)
        source.write_text(
            """package dev.pdpunto.sample;

public final class Sample {
    public String message() {
        return "";
    }
}
""",
            encoding="utf-8",
        )

        edit = runner._prepare_source_edit(root)

        assert edit.relative_path.suffix == ".java"
        assert edit.relative_path.name != "README.md"
        assert edit.before_hash != edit.after_hash
        assert edit.before_text != edit.after_text
        assert edit.after_text == source.read_text(encoding="utf-8").replace('return "";', 'return "PD Agent L11 acceptance";')


def test_security_scenario_records_outside_absence_and_tool_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()
    import pd_agent
    import pd_agent.config as config_module
    import pd_agent.context as context_module
    import pd_agent.runtime as runtime_module

    class FakeLimits:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeRunner:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeInspector:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeValidator:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeContextManager:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeStateValue:
        value = "FAILED"

    class FakeRunState:
        def __init__(self) -> None:
            self.run_id = "run-1"
            self.state = FakeStateValue()
            self.termination_reason = "tool rejected"

        def to_dict(self) -> dict[str, object]:
            return {
                "run_id": self.run_id,
                "state": self.state.value,
                "termination_reason": self.termination_reason,
            }

    class FakeReport:
        def to_dict(self) -> dict[str, object]:
            return {"final_state": "FAILED"}

    class FakeController:
        def __init__(self, *, storage: object, **kwargs: object) -> None:
            self.storage = storage

        def run(self, work_root: Path, task: str) -> tuple[FakeRunState, FakeReport]:
            from pd_agent.reporting import RunEvent, RunEventType

            self.storage.append_event(
                RunEvent(
                    run_id="run-1",
                    event_type=RunEventType.TOOL_REJECTED,
                    payload={"path": r"..\outside.txt"},
                )
            )
            return FakeRunState(), FakeReport()

    monkeypatch.setattr(pd_agent, "ArtifactValidator", FakeValidator)
    monkeypatch.setattr(pd_agent, "GradleBuildRunner", FakeRunner)
    monkeypatch.setattr(pd_agent, "ProjectInspector", FakeInspector)
    monkeypatch.setattr(context_module, "ContextManager", FakeContextManager)
    monkeypatch.setattr(config_module, "ExecutionLimits", FakeLimits)
    monkeypatch.setattr(runtime_module, "RunController", FakeController)

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        candidate = base / "candidate"
        validation = base / "validation"
        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=candidate,
            validation_root=validation,
        )
        summary.working_root = validation / "working"
        summary.evidence_root = validation / "evidence"
        source = candidate / "src" / "main" / "java" / "dev" / "pdpunto" / "sample" / "Sample.java"
        source.parent.mkdir(parents=True)
        source.write_text(
            """package dev.pdpunto.sample;

public final class Sample {
    public String message() {
        return "";
    }
}
""",
            encoding="utf-8",
        )

        result = runner._run_security_scenario(summary, SimpleNamespace())
        evaluation_path = summary.evidence_root / "security" / "evaluation.json"
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        outside_path = Path(evaluation["outside_path"])

        assert result.status == "PASS"
        assert result.details["outside_exists"] is False
        assert result.details["tool_rejected_seen"] is True
        assert outside_path.exists() is False
        assert "TOOL_REJECTED" in evaluation["event_types"]


def test_cleanup_removes_working_and_gradle_homes() -> None:
    runner = _load_runner()
    with tempfile.TemporaryDirectory() as temp_dir:
        validation = Path(temp_dir) / "validation"
        working = validation / "working"
        evidence = validation / "evidence"
        gradle_home = validation / "gradle-home-one"
        gradle_home.mkdir(parents=True)
        (working / "child").mkdir(parents=True)
        (evidence).mkdir(parents=True)
        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            validation_root=validation,
            working_root=working,
            evidence_root=evidence,
        )
        runner._cleanup(summary, keep_working_copy=False)
        assert not working.exists()
        assert not gradle_home.exists()
