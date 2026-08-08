from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from pd_agent.artifacts import ArtifactValidator
from pd_agent.bootstrap import RuntimeBundle
from pd_agent.build import GradleBuildRunner
from pd_agent.cli import EXIT_CONFIG_ERROR, EXIT_OK, EXIT_RUN_FAILED, main
from pd_agent.config import AppConfig
from pd_agent.context import ContextManager
from pd_agent.core import AgentResponse, ArtifactResult, BuildResult, ExecutionLimits, RunState, RunStatus, ToolCall
from pd_agent.pass_policy import evaluate_pass
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage
from pd_agent.runtime import RunController
from pd_agent.tools import ToolExecutor, create_filesystem_tools


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _fake_fabric_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "settings.gradle.kts", 'rootProject.name = "cli-runtime"\n')
    _write(root / "build.gradle.kts", 'plugins { id("fabric-loom") version "1.8-SNAPSHOT" }\n')
    _write(
        root / "gradle.properties",
        "\n".join(
            [
                "minecraft_version=1.20.1",
                "mappings=1.20.1+build.10",
                "fabric_version=0.92.1+1.20.1",
                "loader_version=0.15.11",
                "loom_version=1.8-SNAPSHOT",
            ]
        )
        + "\n",
    )
    _write(
        root / "src" / "main" / "resources" / "fabric.mod.json",
        textwrap.dedent(
            """
            {
              "schemaVersion": 1,
              "id": "cli-runtime",
              "version": "1.0.0",
              "environment": "*",
              "entrypoints": {
                "main": ["com.example.ExampleMod"]
              }
            }
            """
        ).strip()
        + "\n",
    )
    _write(root / "src" / "main" / "java" / "com" / "example" / "ExampleMod.java", "package com.example; class ExampleMod {}\n")
    _write(root / "build-state.txt", "fail\n")
    _write(
        root / "fake_gradle.py",
        textwrap.dedent(
            """
            from __future__ import annotations

            import json
            import sys
            import zipfile
            from pathlib import Path

            root = Path(__file__).resolve().parent
            state = (root / "build-state.txt").read_text(encoding="utf-8").strip()

            if state != "pass":
                print(f"BUILD FAILED: {state}", file=sys.stderr)
                raise SystemExit(2)

            jar_path = root / "build" / "libs" / "cli-runtime-1.0.0.jar"
            jar_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(jar_path, "w", compression=zipfile.ZIP_DEFLATED) as jar:
                jar.writestr(
                    "fabric.mod.json",
                    json.dumps(
                        {
                            "schemaVersion": 1,
                            "id": "cli-runtime",
                            "version": "1.0.0",
                            "environment": "*",
                        }
                    ),
                )
                jar.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\\n")
            print("BUILD SUCCESSFUL")
            raise SystemExit(0)
            """
        ).strip()
        + "\n",
    )
    _write(root / "gradlew.bat", f'@echo off\n"{sys.executable}" "{root / "fake_gradle.py"}" %*\nexit /b %ERRORLEVEL%\n')
    _write(root / "gradlew", "#!/bin/sh\n")
    return root


class ScriptedProvider:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)

    def execute(self, request):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _runtime_bundle_factory(project_root: Path, runs_root: Path, provider: ScriptedProvider):
    def factory(config: AppConfig) -> RuntimeBundle:
        storage = RunStorage(runs_root)
        controller = RunController(
            provider=provider,
            storage=storage,
            build_runner=GradleBuildRunner(reporting=storage),
            artifact_validator=ArtifactValidator(reporting=storage),
            context_manager=ContextManager(),
            tool_executor=ToolExecutor(tools=create_filesystem_tools()),
            limits=config.execution_limits,
            model_config={},
        )
        return RuntimeBundle(config=config, storage=storage, controller=controller, provider=provider)

    return factory


def _build_success_bundle(runs_root: Path, run_id: str = "11111111-1111-4111-8111-111111111111") -> tuple[RunStorage, RunState, FinalReport]:
    storage = RunStorage(runs_root)
    started_at = RunState().started_at
    build = BuildResult(
        attempt=1,
        command_display="gradlew build",
        cwd=Path("C:/dev/project"),
        started_at=started_at,
        duration_seconds=1.0,
        exit_code=0,
        stdout_log="BUILD SUCCESSFUL",
        stderr_log="",
    )
    artifact = ArtifactResult(
        path=Path("C:/dev/project/build/libs/example.jar"),
        size=1234,
        timestamp=started_at,
        classification="VALID",
        metadata={"valid": True},
    )
    run_state = RunState(
        run_id=run_id,
        project_root=Path("C:/dev/project"),
        task="repair",
        state=RunStatus.COMPLETED,
        build_results=(build,),
        build_attempt_count=1,
        artifact_result=artifact,
        termination_reason="completed",
    )
    report = FinalReport(
        run_id=run_id,
        final_state=RunStatus.COMPLETED,
        summary="state=COMPLETED steps=1 tools=1 builds=1",
        project="C:/dev/project",
        requested_task="repair",
        build_attempts=(build,),
        final_build=build,
        artifact=artifact,
        termination_reason="completed",
    )
    storage.write_run_state(run_state)
    storage.write_final_report(report)
    storage.event_writer(run_id).append(
        RunEvent(run_id=run_id, event_type=RunEventType.RUN_STARTED, payload={"task": "repair"})
    )
    return storage, run_state, report


def _persist_policy_evidence(
    runs_root: Path,
    *,
    final_state: RunStatus,
    include_build: bool = True,
    include_report: bool = True,
    artifact_classification: str = "VALID",
    build_exit_code: int = 0,
) -> tuple[RunStorage, str]:
    storage = RunStorage(runs_root)
    run_id = RunState().run_id
    started_at = RunState().started_at
    build = BuildResult(
        attempt=1,
        command_display="gradlew build",
        cwd=Path("C:/dev/project"),
        started_at=started_at,
        duration_seconds=1.0,
        exit_code=build_exit_code,
        stdout_log="BUILD SUCCESSFUL" if build_exit_code == 0 else "BUILD FAILED",
        stderr_log="" if build_exit_code == 0 else "boom",
    )
    artifact = ArtifactResult(
        path=Path("C:/dev/project/build/libs/example.jar"),
        size=1234,
        timestamp=started_at,
        classification=artifact_classification,
        metadata={"valid": artifact_classification == "VALID"},
    )
    run_state = RunState(
        run_id=run_id,
        project_root=Path("C:/dev/project"),
        task="repair",
        state=final_state,
        build_results=(build,) if include_build else (),
        build_attempt_count=1 if include_build else 0,
        artifact_result=artifact,
        termination_reason=final_state.value.lower(),
    )
    report = FinalReport(
        run_id=run_id,
        final_state=final_state,
        summary="summary",
        project="C:/dev/project",
        requested_task="repair",
        build_attempts=(build,) if include_build else (),
        final_build=build if include_build else None,
        artifact=artifact,
        termination_reason=final_state.value.lower(),
    )

    storage.write_run_state(run_state)
    storage.event_writer(run_id).append(
        RunEvent(run_id=run_id, event_type=RunEventType.RUN_STARTED, payload={"task": "repair"})
    )
    if include_report:
        storage.write_final_report(report)
    return storage, run_id


def _static_runtime_factory(storage: RunStorage, run_state: RunState, report: FinalReport):
    class _Controller:
        def run(self, project_root: Path, task: str):
            return run_state, report

    def factory(config: AppConfig) -> RuntimeBundle:
        return RuntimeBundle(config=config, storage=storage, controller=_Controller(), provider=object())

    return factory


def test_pass_policy_table(tmp_path: Path) -> None:
    cases = [
        ("pass", RunStatus.COMPLETED, True, True, True, 0, "pass criteria satisfied"),
        ("missing-report", RunStatus.COMPLETED, True, True, False, 0, "missing persisted file(s): final-report.json"),
        ("invalid-artifact", RunStatus.COMPLETED, True, False, True, 0, "artifact classification is INVALID_METADATA"),
        ("no-build", RunStatus.COMPLETED, False, True, True, 0, "missing final build in run state"),
        ("build-failed", RunStatus.COMPLETED, True, True, True, 2, "final build did not succeed"),
        ("failed", RunStatus.FAILED, True, True, True, 0, "final state is FAILED"),
        ("blocked", RunStatus.BLOCKED, True, True, True, 0, "final state is BLOCKED"),
        ("limit", RunStatus.LIMIT_REACHED, True, True, True, 0, "final state is LIMIT_REACHED"),
    ]

    for name, final_state, include_build, valid_artifact, include_report, build_exit_code, expected_reason in cases:
        runs_root = tmp_path / name / "runs"
        storage, run_id = _persist_policy_evidence(
            runs_root,
            final_state=final_state,
            include_build=include_build,
            include_report=include_report,
            artifact_classification="VALID" if valid_artifact else "INVALID_METADATA",
            build_exit_code=build_exit_code,
        )
        evaluation = evaluate_pass(storage, run_id)

        expected_pass = final_state == RunStatus.COMPLETED and include_build and valid_artifact and include_report and build_exit_code == 0
        assert evaluation.passed == expected_pass
        assert expected_reason in evaluation.reason
        assert evaluation.final_report is not None or not evaluation.passed
        if evaluation.passed:
            assert evaluation.paths is not None
            assert evaluation.paths.run_json.exists()
            assert evaluation.paths.events_jsonl.exists()
            assert evaluation.paths.final_report_json.exists()
            assert evaluation.paths.final_report_md.exists()
            assert evaluation.final_report is not None
            assert evaluation.final_report.minecraft_runtime_validation == "NOT PERFORMED (v0.1)"


def test_cli_rejects_invalid_inputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing"
    code = main(
        [
            "run",
            "--project",
            str(missing),
            "--task",
            "repair",
        ],
        runtime_factory=lambda config: None,
    )
    assert code == EXIT_CONFIG_ERROR
    assert "project root does not exist" in capsys.readouterr().err

    empty_project = tmp_path / "project"
    empty_project.mkdir()
    code = main(
        [
            "run",
            "--project",
            str(empty_project),
            "--task",
            "   ",
        ],
        runtime_factory=lambda config: None,
    )
    assert code == EXIT_CONFIG_ERROR
    assert "task cannot be empty" in capsys.readouterr().err


def test_cli_end_to_end_pass_and_secret_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    project_root = _fake_fabric_project(tmp_path / "project")
    runs_root = tmp_path / "runs"
    secret = "sk-secret-should-not-leak"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="write_file",
                        arguments={"path": "build-state.txt", "content": "pass\n"},
                    ),
                ),
            )
        ]
    )
    factory = _runtime_bundle_factory(project_root, runs_root, provider)

    code = main(
        [
            "run",
            "--project",
            str(project_root),
            "--task",
            "repair the build",
            "--runs-dir",
            str(runs_root),
            "--model",
            "gpt-test",
        ],
        runtime_factory=factory,
    )

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "PASS: yes" in captured.out
    assert "run_id:" in captured.out
    assert "Minecraft runtime validation: NOT PERFORMED (v0.1)" in captured.out
    assert secret not in captured.out
    assert secret not in captured.err

    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir / "run.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "final-report.json").exists()
    assert (run_dir / "final-report.md").exists()
    assert secret not in (run_dir / "run.json").read_text(encoding="utf-8")
    assert secret not in (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert secret not in (run_dir / "final-report.json").read_text(encoding="utf-8")
    assert secret not in (run_dir / "final-report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "final_state,expected_reason",
    [
        (RunStatus.FAILED, "final state is FAILED"),
        (RunStatus.BLOCKED, "final state is BLOCKED"),
        (RunStatus.LIMIT_REACHED, "final state is LIMIT_REACHED"),
    ],
)
def test_cli_failures_are_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    final_state: RunStatus,
    expected_reason: str,
) -> None:
    runs_root = tmp_path / "runs"
    storage, run_id = _persist_policy_evidence(
        runs_root,
        final_state=final_state,
        include_build=True,
        include_report=True,
    )
    run_state = storage.read_run_state(run_id)
    report = storage.read_final_report(run_id)
    factory = _static_runtime_factory(storage, run_state, report)

    project_root = _fake_fabric_project(tmp_path / "project")
    code = main(
        [
            "run",
            "--project",
            str(project_root),
            "--task",
            "repair",
            "--runs-dir",
            str(runs_root),
            "--model",
            "gpt-test",
        ],
        runtime_factory=factory,
    )

    captured = capsys.readouterr()
    assert code == EXIT_RUN_FAILED
    assert "PASS: no" in captured.err
    assert expected_reason in captured.err


def test_cli_internal_error_returns_fail(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_root = _fake_fabric_project(tmp_path / "project")

    def factory(config: AppConfig):
        raise RuntimeError("boom")

    code = main(
        [
            "run",
            "--project",
            str(project_root),
            "--task",
            "repair",
            "--model",
            "gpt-test",
        ],
        runtime_factory=factory,
    )

    captured = capsys.readouterr()
    assert code == EXIT_RUN_FAILED
    assert "internal error" in captured.err


def test_cli_help_and_version_via_python_module() -> None:
    help_result = subprocess.run(
        [sys.executable, "-m", "pd_agent", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    version_result = subprocess.run(
        [sys.executable, "-m", "pd_agent", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert help_result.returncode == 0
    assert "usage:" in help_result.stdout.lower()
    assert version_result.returncode == 0
    assert "pd-agent 0.1.0" in version_result.stdout.lower()


def test_console_script_help_and_version() -> None:
    script = Path(sys.executable).with_name("pd-agent.exe")
    if not script.exists():
        pytest.skip("pd-agent console script not installed")

    help_result = subprocess.run(
        [str(script), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    version_result = subprocess.run(
        [str(script), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert help_result.returncode == 0
    assert "usage:" in help_result.stdout.lower()
    assert version_result.returncode == 0
    assert "pd-agent 0.1.0" in version_result.stdout.lower()
