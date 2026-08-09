from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile


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
