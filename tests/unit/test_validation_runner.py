from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest


def _load_runner(script_name: str = "validate_v0_1.py"):
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "validation" / script_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
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


def test_l11_fixture_is_recognized_by_project_inspector() -> None:
    from pd_agent.project import ProjectInspectionStatus, ProjectInspector

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "l11_fabric_fixture"
    snapshot = ProjectInspector().inspect(fixture)

    assert snapshot.status == ProjectInspectionStatus.READY
    assert snapshot.wrapper.present is True
    assert snapshot.target_subproject == fixture
    assert snapshot.detected_versions["minecraft"].value == "1.21.11"
    assert snapshot.detected_versions["loader"].value == "0.19.3"
    assert snapshot.detected_versions["loom"].value == "1.13.3"
    assert any(path.as_posix().endswith("src/main/java") for path in snapshot.source_roots)
    assert any(path.name == "fabric.mod.json" for path in snapshot.relevant_files)


def test_pick_source_target_stays_in_source_root() -> None:
    runner = _load_runner()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        noisy = root / ".local-backups" / "bad"
        noisy.mkdir(parents=True)
        (noisy / "Bad.java").write_text('class Bad { String x = "no"; }', encoding="utf-8")
        good = root / "src" / "main" / "java" / "dev" / "pdpunto" / "sample"
        good.mkdir(parents=True)
        (good / "Good.java").write_text(
            'package dev.pdpunto.sample; public class Good { String x = "ok"; }',
            encoding="utf-8",
        )
        (root / "README.md").write_text("readme", encoding="utf-8")

        picked = runner._pick_source_target(root)

        assert picked == good / "Good.java"
        assert ".local-backups" not in picked.as_posix()
        assert picked.suffix == ".java"


def test_main_fails_fast_on_baseline_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()
    calls: list[str] = []

    monkeypatch.setattr(runner, "_run_prechecks", lambda summary, args: calls.append("prechecks"))
    monkeypatch.setattr(
        runner,
        "_run_baseline_build",
        lambda summary, args: runner._scenario_result("Baseline Fabric build", "FAIL", "build failed"),
    )

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("later scenario should not run")

    monkeypatch.setattr(runner, "_run_acceptance_main", _boom)
    monkeypatch.setattr(runner, "_run_repair_scenario", _boom)
    monkeypatch.setattr(runner, "_run_security_scenario", _boom)
    monkeypatch.setattr(runner, "_run_negative_artifact", _boom)
    monkeypatch.setattr(runner, "_run_openai_live", _boom)
    monkeypatch.setattr(runner, "_run_suite", _boom)
    monkeypatch.setattr(runner, "_finalize", lambda summary: None)
    monkeypatch.setattr(runner, "_write_artifacts", lambda summary: None)
    monkeypatch.setattr(runner, "_print_summary", lambda summary: None)
    monkeypatch.setattr(runner, "_cleanup", lambda summary, keep_working_copy=False: None)

    with tempfile.TemporaryDirectory() as temp_dir:
        validation = Path(temp_dir) / "validation"
        candidate = Path(temp_dir) / "candidate"
        candidate.mkdir()
        code = runner.main(
            [
                "--candidate-root",
                str(candidate),
                "--validation-root",
                str(validation),
            ]
        )

    assert code == 2
    assert calls == ["prechecks"]


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


def test_v011_prechecks_require_gemini_provider_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner("validate_v0_1_1.py")
    monkeypatch.setattr(runner.base, "_check_pd_agent_import", lambda: None)
    monkeypatch.setattr(runner.base, "_check_java", lambda: None)
    monkeypatch.setattr(runner, "_check_git_clean", lambda summary, root: None)

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        candidate = base / "candidate"
        validation = base / "validation"
        candidate.mkdir()
        (candidate / "gradlew.bat").write_text("@echo off", encoding="utf-8")
        summary = runner.LiveSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=candidate,
            validation_root=validation,
        )
        summary.working_root = validation / "working"
        summary.evidence_root = validation / "evidence"
        args = SimpleNamespace(candidate_root=candidate)

        monkeypatch.setenv("PD_AGENT_PROVIDER", "gemini")
        monkeypatch.setenv("PD_AGENT_MODEL", "gemini-2.5-flash")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        runner._run_prechecks(summary, args)

        assert "provider: gemini" in summary.notes
        assert "PD_AGENT_MODEL env: gemini-2.5-flash" in summary.notes
        assert "selected model: gemini-3.5-flash" in summary.notes
        assert "GEMINI_API_KEY: present" in summary.notes


def test_v011_tool_sequence_reads_gemini_function_calls() -> None:
    runner = _load_runner("validate_v0_1_1.py")
    call = runner.RecordedGenerateContentCall(
        request={
            "model": "gemini-2.5-flash",
            "contents": [
                {
                    "role": "model",
                    "parts": [
                        {
                            "type": "function_call",
                            "function_call": {
                                "call_id": "call_a",
                                "name": "read_file",
                                "arguments": {"path": "ExampleMod.java"},
                            },
                        },
                        {
                            "type": "function_call",
                            "function_call": {
                                "call_id": "call_b",
                                "name": "write_file",
                                "arguments": {"path": "ExampleMod.java", "text": "ok"},
                            },
                        },
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {
                            "type": "function_response",
                            "function_response": {
                                "call_id": "call_a",
                                "name": "read_file",
                                "output": {"status": "success"},
                            },
                        },
                        {
                            "type": "function_response",
                            "function_response": {
                                "call_id": "call_b",
                                "name": "write_file",
                                "output": {"status": "success"},
                            },
                        },
                    ],
                },
            ],
        },
        response=None,
    )

    sequence = runner._tool_call_sequence([call])

    assert [item["type"] for item in sequence] == [
        "function_call",
        "function_call",
        "function_call_output",
        "function_call_output",
    ]
    assert [item["call_id"] for item in sequence] == ["call_a", "call_b", "call_a", "call_b"]
    assert sequence[0]["name"] == "read_file"
    assert sequence[1]["arguments"] == {"path": "ExampleMod.java", "text": "ok"}
    assert sequence[2]["output"] == {"status": "success"}


def test_v011_continuation_summary_hides_raw_signature() -> None:
    runner = _load_runner("validate_v0_1_1.py")
    call = runner.RecordedGenerateContentCall(
        request={
            "model": "gemini-3.5-flash",
            "contents": [
                {
                    "role": "model",
                    "parts": [
                        {
                            "type": "function_call",
                            "function_call": {
                                "call_id": "call_a",
                                "name": "read_file",
                                "arguments": {"path": "ExampleMod.java"},
                            },
                            "thought_signature_present": True,
                            "thought_signature_sha256": "hash-a",
                            "thought_signature_position": 0,
                        }
                    ],
                }
            ],
        },
        response={
            "output": [
                {
                    "content": [
                        {
                            "type": "function_call",
                            "function_call": {
                                "call_id": "call_a",
                                "name": "read_file",
                                "arguments": {"path": "ExampleMod.java"},
                            },
                            "thought_signature_present": True,
                            "thought_signature_sha256": "hash-a",
                            "thought_signature_position": 0,
                        }
                    ]
                }
            ]
        },
    )

    summary = runner._continuation_summary([call])

    assert summary["continuation_detected"] is True
    assert summary["provider"] == "gemini"
    assert summary["payload_present"] is True
    assert summary["replay_success"] is True
    assert summary["response_records"][0]["payload_sha256"] == "hash-a"
    assert summary["request_records"][0]["payload_sha256"] == "hash-a"
