from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest


def _load_runner():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "validation" / "validate_v0_4_dataset_freeze.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_git_status_header_not_dirty() -> None:
    runner = _load_runner()
    assert runner._git_status_dirty("## main...origin/main\n") is False
    assert runner._git_status_dirty("## main...origin/main\n M file.py\n") is True


def test_compute_fixture_identity_helper_uses_real_import(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()
    calls: list[Path] = []

    def fake_compute(path: Path) -> str:
        calls.append(path)
        return "sha"

    monkeypatch.setattr(runner, "compute_fixture_identity", fake_compute)

    value = runner._case_fixture_identity("B001", "1")

    assert value == "sha"
    assert calls == [runner.BENCHMARK_ROOT / "fixtures" / "B001-v1"]


def test_control_result_truth_table() -> None:
    runner = _load_runner()

    assert runner._control_result("FAIL", "FAIL") == "PASS"
    assert runner._control_result("PASS", "PASS") == "PASS"
    assert runner._control_result("PASS", "FAIL") == "FAIL"
    assert runner._control_result("FAIL", "PASS") == "FAIL"
    assert runner._control_result("PASS", "BLOCKED") == "BLOCKED"


def test_summary_requires_all_cases() -> None:
    runner = _load_runner()
    summary = runner._build_summary(Path("C:/repo"), Path("C:/temp"))

    assert summary.ready is False
    assert "Task | Control | Build" in summary.table()

    summary.cases = [
        runner.CaseResult(
            task=f"T{i}",
            task_version="1",
            control="positive",
            expected="PASS",
            actual_acceptance="PASS",
            control_result="PASS",
            build="PASS",
            artifact="PASS",
            minecraft="N/A",
            neighbor="N/A",
            fixture_path="x",
        )
        for i in range(11)
    ]

    assert summary.ready is True


def test_summary_tolerates_blocked_case() -> None:
    runner = _load_runner()
    summary = runner._build_summary(Path("C:/repo"), Path("C:/temp"))
    summary.cases = [
        runner.CaseResult(
            task="B001",
            task_version="1",
            control="baseline",
            expected="FAIL",
            actual_acceptance="BLOCKED",
            control_result="BLOCKED",
            build="BLOCKED",
            artifact="BLOCKED",
            minecraft="BLOCKED",
            neighbor="N/A",
            fixture_path="x",
            error="boom",
        )
    ]

    assert summary.ready is False
    assert summary.to_dict()["error"] is None


def test_canonical_fixture_identity_matches_manifest() -> None:
    runner = _load_runner()
    for task_id, version in (("B001", "1"), ("B002", "2"), ("B003", "2")):
        manifest = json.loads((runner.BENCHMARK_ROOT / "tasks" / f"{task_id}-v{version}.json").read_text(encoding="utf-8"))
        assert runner._case_fixture_identity(task_id, version) == manifest["fixture"]["fixture_identity"]


def test_temp_copy_does_not_touch_canonical_fixture(tmp_path: Path) -> None:
    runner = _load_runner()
    source = runner.BENCHMARK_ROOT / "fixtures" / "B001-v1"
    before = runner.compute_fixture_identity(source)
    copied = tmp_path / "copy"
    shutil = __import__("shutil")
    shutil.copytree(source, copied)
    text = copied / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"
    text.write_text(text.read_text(encoding="utf-8").replace("Blocks.DIAMOND_BLOCK", "Blocks.DIAMOND_BLOCK"), encoding="utf-8")
    after = runner.compute_fixture_identity(source)

    assert before == after
