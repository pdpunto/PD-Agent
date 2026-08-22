from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pd_agent.minecraft import MinecraftProcessEvidence


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

    def fake_compute(path: Path, *, algorithm: str | None = None) -> str:
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


def test_validate_control_reads_process_logs_from_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()
    spec = runner._control_specs()[1]
    target_root, harness_root, evidence_root = runner._prepare_case_workspace(tmp_path, spec.task, spec.fixture_version)
    (target_root / "build" / "libs").mkdir(parents=True, exist_ok=True)
    target_jar = target_root / "build" / "libs" / "pd-agent-l11-fixture.jar"
    target_jar.write_text("jar", encoding="utf-8")
    (harness_root / "build" / "libs").mkdir(parents=True, exist_ok=True)
    (evidence_root / "minecraft").mkdir(parents=True, exist_ok=True)
    harness_result_path = evidence_root / "minecraft" / "run" / "harness-result.json"
    harness_result_path.parent.mkdir(parents=True, exist_ok=True)
    harness_result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "functional_test_result": "PASS",
                "target_loaded": True,
                "target_origin_resolved": True,
                "target_sha_match": True,
                "server_started": True,
                "shutdown_requested": True,
                "neighbor_update_triggered": False,
            }
        ),
        encoding="utf-8",
    )
    stdout_log = evidence_root / "minecraft" / "run" / "stdout.log"
    stderr_log = evidence_root / "minecraft" / "run" / "stderr.log"
    stdout_log.write_text("stdout line\n", encoding="utf-8")
    stderr_log.write_text("stderr line\n", encoding="utf-8")

    def fake_run_gradle_build(**kwargs):  # noqa: ANN001
        return SimpleNamespace(exit_code=0, timed_out=False, stdout="build ok\n", stderr="")

    def fake_validate_target(self, spec_for_validation, *, java_version=None):  # noqa: ANN001
        return SimpleNamespace(path=target_jar, sha256="a" * 64)

    def fake_run(self, spec_for_run, *, run_id, java_version, expected_sha256):  # noqa: ANN001
        return SimpleNamespace(
            status=SimpleNamespace(value="PASS"),
            process_evidence=MinecraftProcessEvidence(
                command_display="cmd",
                cwd=harness_root,
                started_at=runner.datetime.now(runner.timezone.utc),
                finished_at=runner.datetime.now(runner.timezone.utc),
                duration_seconds=1.0,
                exit_code=0,
                timed_out=False,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            ),
            evidence_paths=SimpleNamespace(harness_result_json=harness_result_path),
        )

    monkeypatch.setattr(runner, "_run_gradle_build", fake_run_gradle_build)
    monkeypatch.setattr(runner.MinecraftTestRunner, "validate_target", fake_validate_target, raising=False)
    monkeypatch.setattr(runner.MinecraftTestRunner, "run", fake_run, raising=False)

    result = runner._validate_control(
        spec=spec,
        target_root=target_root,
        harness_root=harness_root,
        evidence_root=evidence_root,
        gradle_exe=runner.DEFAULT_GRADLE_EXE,
        gradle_user_home=tmp_path / "gradle-home",
        timeout_seconds=5,
        repo_root=runner.REPO_ROOT,
    )

    assert result.harness_run_stdout_tail == "stdout line"
    assert result.harness_run_stderr_tail == "stderr line"
