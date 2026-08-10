from __future__ import annotations

import io
import json
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import zipfile

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


def test_v0_1_fixture_has_stable_source_edit_target() -> None:
    runner = _load_runner()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            """package dev.pdpunto.l11;

public final class ExampleMod {
    public String message() {
        return "";
    }
}
""",
            encoding="utf-8",
        )

        edit = runner._prepare_source_edit(root)

    assert edit.relative_path == Path("src/main/java/dev/pdpunto/l11/ExampleMod.java")
    assert edit.replacement == 'return "PD Agent L11 acceptance";'
    assert edit.before_hash != edit.after_hash
    assert "PD Agent L11 acceptance" in edit.after_text


def test_v0_1_suite_clears_pytest_temp_root(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()

    def fake_run_command(command, *, cwd, timeout_seconds, extra_env=None):  # noqa: ANN001
        pytest_temp = Path(extra_env["PYTEST_DEBUG_TEMPROOT"])  # type: ignore[index]
        assert pytest_temp.exists()
        assert list(pytest_temp.iterdir()) == []
        return runner.CommandResult(
            command=tuple(command),
            cwd=cwd,
            exit_code=0,
            timed_out=False,
            stdout=".",
            stderr="",
            duration_seconds=0.1,
        )

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    with tempfile.TemporaryDirectory() as temp_dir:
        validation = Path(temp_dir) / "validation"
        validation.mkdir(parents=True, exist_ok=True)
        stale = validation / "pytest-tmp"
        (stale / "pytest-of-Usuario" / "old").mkdir(parents=True, exist_ok=True)
        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            validation_root=validation,
        )
        summary.evidence_root = validation / "evidence"
        summary.evidence_root.mkdir(parents=True, exist_ok=True)
        result = runner._run_suite(summary, SimpleNamespace(pytest_timeout_seconds=30))

    assert result.status == "PASS"
    assert not (stale / "pytest-of-Usuario" / "old").exists()


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
        assert "selected model: gemini-3.1-flash-lite" in summary.notes
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


def _yarn_artifact_bytes() -> bytes:
    root = Path(__file__).resolve().parents[1] / "fixtures" / "brain" / "yarn_sample.tiny"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mappings/mappings.tiny", root.read_text(encoding="utf-8"))
    return buffer.getvalue()


def test_v03_prepare_workspace_resets_fixture_and_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner("validate_v0_3.py")

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        candidate = base / "candidate"
        harness = base / "harness"
        validation = base / "validation"
        (candidate / "build").mkdir(parents=True)
        (candidate / ".gradle").mkdir(parents=True)
        target_source = candidate / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"
        target_source.parent.mkdir(parents=True, exist_ok=True)
        target_source.write_text(
            """package dev.pdpunto.l11;

import net.minecraft.block.Blocks;

public final class ExampleMod {
    public static final Object PROBE = Blocks.DIAMOND_BLOCK;
}
""",
            encoding="utf-8",
        )
        (candidate / "build" / "stale.txt").write_text("stale", encoding="utf-8")
        (harness / "src" / "main" / "java").mkdir(parents=True)
        (harness / "src" / "main" / "java" / "Harness.java").write_text("class Harness {}", encoding="utf-8")
        (harness / "build").mkdir(parents=True)
        (harness / "build" / "stale.txt").write_text("stale", encoding="utf-8")

        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=candidate,
            validation_root=validation,
        )
        summary.working_root = validation / "working"
        summary.evidence_root = validation / "evidence"
        monkeypatch.setattr(runner, "DEFAULT_HARNESS_ROOT", harness)

        runner._prepare_workspace(summary)

        assert (summary.target_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java").exists()
        assert (summary.harness_root / "src" / "main" / "java" / "Harness.java").exists()
        assert not (summary.target_root / "build").exists()
        assert not (summary.harness_root / "build").exists()
        target_source_text = (summary.target_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java").read_text(encoding="utf-8")

    assert "Blocks.DIAMOND_BLOCK" in target_source_text
    assert "Registries.BLOCK" not in target_source_text


def test_v03_prepare_acceptance_workspace_keeps_cases_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner("validate_v0_3.py")

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        candidate = base / "candidate"
        harness = base / "harness"
        validation = base / "validation"
        source = candidate / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            """package dev.pdpunto.l11;

import net.minecraft.block.Blocks;

public final class ExampleMod {
    public static final Object PROBE = Blocks.DIAMOND_BLOCK;
}
""",
            encoding="utf-8",
        )
        (harness / "src" / "main" / "java").mkdir(parents=True)
        (harness / "src" / "main" / "java" / "Harness.java").write_text("class Harness {}", encoding="utf-8")

        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=candidate,
            validation_root=validation,
        )
        summary.working_root = validation / "working"
        summary.evidence_root = validation / "evidence"
        monkeypatch.setattr(runner, "DEFAULT_HARNESS_ROOT", harness)

        off_target, off_harness = runner._prepare_acceptance_workspace(summary, "brain-off")
        (off_target / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java").write_text(
            """package dev.pdpunto.l11;

import net.minecraft.block.Blocks;

public final class ExampleMod {
    public static final Object PROBE = Registries.BLOCK.get(Identifier.of("minecraft", "diamond_block"));
}
""",
            encoding="utf-8",
        )
        on_target, on_harness = runner._prepare_acceptance_workspace(summary, "brain-on")
        on_text = (on_target / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java").read_text(encoding="utf-8")

    assert off_target != on_target
    assert off_harness != on_harness
    assert "Blocks.DIAMOND_BLOCK" in on_text
    assert "Registries.BLOCK" not in on_text


def test_v03_knowledge_need_uses_detected_environment() -> None:
    runner = _load_runner("validate_v0_3.py")
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "l11_fabric_fixture"

    with tempfile.TemporaryDirectory() as temp_dir:
        validation = Path(temp_dir) / "validation"
        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=fixture,
            validation_root=validation,
        )
        summary.working_root = validation / "working"
        summary.evidence_root = validation / "evidence"
        summary.target_root = fixture
        summary.environment_resolution = runner._scenario_result("Environment resolution", "PASS", "detected")

        need = runner._build_knowledge_need(summary)

    assert need.query == "Identifier Registries Block registry lookup"
    assert tuple(need.hints) == ("Identifier", "Registries", "Block registry lookup")
    assert need.environment.minecraft_version == "1.21.11"
    assert need.environment.loader_version == "0.19.3"
    assert need.environment.loom_version == "1.13.3"


def test_v03_brain_retrieval_records_provenance_and_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner("validate_v0_3.py")
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "l11_fabric_fixture"

    with tempfile.TemporaryDirectory() as temp_dir:
        validation = Path(temp_dir) / "validation"
        validation.mkdir(parents=True, exist_ok=True)
        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=fixture,
            validation_root=validation,
        )
        summary.working_root = validation / "working"
        summary.evidence_root = validation / "evidence"
        summary.target_root = fixture
        summary.environment_resolution = runner._scenario_result("Environment resolution", "PASS", "detected")
        monkeypatch.setattr(
            runner,
            "YarnKnowledgeSource",
            lambda: __import__("pd_agent").YarnKnowledgeSource(artifact_bytes=_yarn_artifact_bytes()),
        )

        result = runner._run_brain_retrieval(summary)
        evidence = json.loads((summary.evidence_root / "knowledge.json").read_text(encoding="utf-8"))

    assert result.status == "PASS"
    assert summary.knowledge_result is not None
    assert summary.knowledge_result.items
    assert evidence["retrieved_item_ids"]
    assert evidence["provenance"]
    assert evidence["raw_result"]["source_results"]


def test_v03_acceptance_source_evidence_helpers_capture_real_change() -> None:
    runner = _load_runner("validate_v0_3.py")

    before = """package dev.pdpunto.l11;

public final class ExampleMod {
    private static final String BLOCK = Blocks.DIAMOND_BLOCK.toString();
}
"""
    after = """package dev.pdpunto.l11;

public final class ExampleMod {
    private static final String BLOCK = Registries.BLOCK.get(Identifier.ofVanilla("diamond_block")).toString();
}
"""

    assert runner._source_excerpt(before, "Blocks.DIAMOND_BLOCK") == 'private static final String BLOCK = Blocks.DIAMOND_BLOCK.toString();'
    assert runner._source_excerpt(after, "Registries.BLOCK") == 'private static final String BLOCK = Registries.BLOCK.get(Identifier.ofVanilla("diamond_block")).toString();'
    assert runner._contains_registry_lookup(after) is True
    assert runner._contains_registry_lookup('private static final String BLOCK = Registries.BLOCK.get(Identifier.ofVanilla("diamond_block")).toString();') is True


def test_v03_acceptance_blocks_without_gemini_key(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner("validate_v0_3.py")

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        target = base / "target"
        validation = base / "validation"
        target.mkdir(parents=True)
        validation.mkdir(parents=True)
        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=target,
            validation_root=validation,
        )
        summary.working_root = validation / "working"
        summary.target_root = target
        summary.harness_root = base / "harness"
        summary.evidence_root = validation / "evidence"
        summary.knowledge_result = object()
        summary.evidence_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        result = runner._run_acceptance_main(summary, SimpleNamespace(), runner._scenario_result("Brain retrieval", "PASS", "retrieved"))

    assert result.status == "BLOCKED"
    assert result.reason == "GEMINI_API_KEY missing"


def test_v03_main_runs_brain_off_and_brain_on_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner("validate_v0_3.py")
    calls: list[tuple[str, bool]] = []

    monkeypatch.setattr(runner, "_run_prechecks", lambda summary, args: None)
    monkeypatch.setattr(runner, "_prepare_workspace", lambda summary: None)
    monkeypatch.setattr(runner, "_seed_gradle_home", lambda summary: None)
    monkeypatch.setattr(runner, "_resolve_environment", lambda summary: runner._scenario_result("Environment resolution", "PASS", "detected"))
    monkeypatch.setattr(runner, "_run_brain_retrieval", lambda summary: runner._scenario_result("Brain retrieval", "PASS", "retrieved"))
    monkeypatch.setattr(runner, "_run_gradle_build", lambda *args, **kwargs: runner._scenario_result("build", "PASS", "ok"))

    def fake_acceptance(summary, args, knowledge, *, case_name, brain_enabled):  # noqa: ANN001
        calls.append((case_name, brain_enabled))
        if brain_enabled:
            summary.accepted_target_root = Path("accepted-target")
            summary.accepted_harness_root = Path("accepted-harness")
        return runner._scenario_result(case_name, "PASS", "ok", brain_enabled=brain_enabled)

    monkeypatch.setattr(runner, "_run_acceptance_case", fake_acceptance)
    monkeypatch.setattr(runner, "_run_comparison", lambda summary, run_brain_off, run_brain_on: runner._scenario_result("Brain comparison", "PASS", "ok"))
    monkeypatch.setattr(runner, "_run_minecraft_runtime", lambda summary: runner._scenario_result("Minecraft harness", "PASS", "ok"))
    monkeypatch.setattr(runner, "_run_suite", lambda summary, args: runner._scenario_result("Suite PD Agent", "PASS", "ok"))
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

    assert code == 0
    assert calls == [("brain-off", False), ("brain-on", True)]


def test_v03_comparison_records_context_difference() -> None:
    runner = _load_runner("validate_v0_3.py")

    with tempfile.TemporaryDirectory() as temp_dir:
        validation = Path(temp_dir) / "validation"
        validation.mkdir(parents=True, exist_ok=True)
        summary = runner.ValidationSummary(
            started_at=runner.datetime.now(runner.timezone.utc),
            candidate_root=Path(temp_dir) / "candidate",
            validation_root=validation,
        )
        summary.evidence_root = validation / "evidence"
        summary.evidence_root.mkdir(parents=True, exist_ok=True)
        summary.environment_resolution = runner._scenario_result("Environment resolution", "PASS", "detected", environment={"minecraft": "1.21.11"})
        summary.brain_off_acceptance = runner._scenario_result(
            "Brain OFF comparison",
            "PASS",
            "compared",
            provider="gemini",
            model="gemini-3.1-flash-lite",
            external_context_count=0,
        )
        summary.acceptance_main = runner._scenario_result(
            "Brain ON acceptance",
            "PASS",
            "completed",
            provider="gemini",
            model="gemini-3.1-flash-lite",
            external_context_count=1,
        )

        result = runner._run_comparison(summary, run_brain_off=True, run_brain_on=True)

    assert result.status == "PASS"
    assert result.details["brain_off_external_context_count"] == 0
    assert result.details["brain_on_external_context_count"] == 1


def test_v03_validation_doc_separates_retrieval_from_provider_context() -> None:
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "validation" / "PD_AGENT_V0.3_VALIDATION.md"
    text = doc_path.read_text(encoding="utf-8")

    assert "External knowledge injected into provider" in text
    assert "Retrieval bookkeeping: retrieved items" in text
    assert "Retrieval bookkeeping: selected/context" in text
    assert "no retrieved external knowledge was delivered to Gemini" in text
