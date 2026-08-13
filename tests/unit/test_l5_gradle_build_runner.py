from __future__ import annotations

import inspect
import json
import sys
import subprocess
from pathlib import Path

import pytest

from pd_agent import GradleBuildRunner
from pd_agent.core import BuildError, ExecutionLimits, LimitReachedError, RunState
from pd_agent.project import ProjectInspector
from pd_agent.reporting import RunStorage

from tests.fixtures.build_projects import (
    make_build_runner_multimodule_project,
    make_build_runner_simple_project,
)


def _inspect(root: Path):
    return ProjectInspector().inspect(root)


def _runner(storage: RunStorage | None = None, platform_override: str | None = None):
    return GradleBuildRunner(reporting=storage, platform_override=platform_override)


def test_wrapper_success_and_events_and_attempt_count(tmp_path: Path) -> None:
    root = make_build_runner_simple_project(tmp_path / "ok", mode="success")
    snapshot = _inspect(root)
    storage = RunStorage(root / "runs")
    state = RunState(project_root=root, task="build")
    runner = _runner(storage)

    result = runner.run(snapshot, state, ExecutionLimits(process_timeout_seconds=10))

    assert result.success is True
    assert result.exit_code == 0
    assert state.build_attempt_count == 1
    assert len(state.build_results) == 1
    assert "stdout:build" in result.stdout_log
    assert "stderr:warn" in result.stderr_log

    run_dir = storage.paths_for(state.run_id)
    assert run_dir.builds_dir.joinpath("001.stdout.log").read_text(encoding="utf-8")
    assert run_dir.builds_dir.joinpath("001.stderr.log").read_text(encoding="utf-8")

    events = [
        json.loads(line)
        for line in run_dir.events_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event_type"] for event in events] == [
        "BUILD_STARTED",
        "BUILD_FINISHED",
    ]
    assert events[0]["payload"]["attempt"] == 1
    assert events[1]["payload"]["success"] is True
    assert events[1]["payload"]["exit_code"] == 0


def test_wrapper_failure(tmp_path: Path) -> None:
    root = make_build_runner_simple_project(tmp_path / "fail", mode="fail")
    snapshot = _inspect(root)
    state = RunState(project_root=root, task="build")
    runner = _runner()

    result = runner.run(snapshot, state, ExecutionLimits(process_timeout_seconds=10))

    assert result.success is False
    assert result.exit_code == 2
    assert state.build_attempt_count == 1
    assert "stderr:boom" in result.stderr_log


def test_timeout_terminates_tree_and_emits_failure(tmp_path: Path) -> None:
    root = make_build_runner_simple_project(tmp_path / "timeout", mode="timeout")
    snapshot = _inspect(root)
    storage = RunStorage(root / "runs")
    state = RunState(project_root=root, task="build")
    runner = _runner(storage)
    sentinel = root / "child-survived.txt"

    result = runner.run(snapshot, state, ExecutionLimits(process_timeout_seconds=1))

    assert result.success is False
    assert result.exit_code == -1
    assert state.build_attempt_count == 1
    assert state.termination_reason == "build timeout"
    assert sentinel.exists() is False

    events = [
        json.loads(line)
        for line in storage.paths_for(state.run_id).events_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    finished = events[-1]
    assert finished["event_type"] == "BUILD_FINISHED"
    assert finished["payload"]["timeout"] is True
    assert finished["payload"]["success"] is False


def test_wrapper_absent_and_no_global_fallback(tmp_path: Path) -> None:
    root = make_build_runner_simple_project(tmp_path / "missing", mode="success")
    (root / "gradlew.bat").unlink()
    snapshot = _inspect(root)
    state = RunState(project_root=root, task="build")
    runner = _runner()

    with pytest.raises(BuildError) as excinfo:
        runner.run(snapshot, state, ExecutionLimits(process_timeout_seconds=10))

    assert "Gradle Wrapper absent" in str(excinfo.value)
    assert state.build_attempt_count == 0
    assert not (root / "gradlew.bat").exists()


def test_command_injection_impossible_and_shell_false(tmp_path: Path) -> None:
    root = make_build_runner_simple_project(tmp_path / "safe", mode="success")
    snapshot = _inspect(root)
    runner = _runner()
    invocation = runner.build_invocation(snapshot)

    assert invocation.shell is False
    assert "build" in invocation.argv[-1]
    assert invocation.command_display.endswith(" build")
    assert len(invocation.argv) == 2

    sig = inspect.signature(GradleBuildRunner.run)
    assert "command" not in sig.parameters
    assert "shell" not in sig.parameters
    assert "argv" not in sig.parameters


def test_max_build_attempts_enforced(tmp_path: Path) -> None:
    root = make_build_runner_simple_project(tmp_path / "limit", mode="success")
    snapshot = _inspect(root)
    state = RunState(project_root=root, task="build", build_attempt_count=5)
    runner = _runner()

    with pytest.raises(LimitReachedError):
        runner.run(snapshot, state, ExecutionLimits(max_build_attempts=5))

    assert state.build_attempt_count == 5


def test_windows_and_posix_argv_and_multimodule_task(tmp_path: Path) -> None:
    simple_root = make_build_runner_simple_project(tmp_path / "argv", mode="success")
    multi_root = make_build_runner_multimodule_project(tmp_path / "multi")

    simple_snapshot = _inspect(simple_root)
    multi_snapshot = _inspect(multi_root)

    windows_invocation = _runner(platform_override="windows").build_invocation(simple_snapshot)
    posix_invocation = _runner(platform_override="posix").build_invocation(simple_snapshot)
    multi_invocation = _runner(platform_override="windows").build_invocation(multi_snapshot)

    assert windows_invocation.argv[0].lower().endswith("gradlew.bat")
    assert posix_invocation.argv[0] == "./gradlew"
    assert multi_invocation.argv[-1] == ":mod-a:build"
    assert multi_invocation.cwd == multi_root.resolve()


def test_environment_overrides_reach_gradle_wrapper(tmp_path: Path) -> None:
    root = make_build_runner_simple_project(tmp_path / "env", mode="success")
    sentinel = root / "gradle-user-home.txt"
    probe = root / "env_probe.py"
    probe.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import os",
                "import sys",
                "from pathlib import Path",
                "sentinel = Path(sys.argv[1])",
                "sentinel.write_text(os.environ.get('GRADLE_USER_HOME', ''), encoding='utf-8')",
                "print('stdout:env')",
                "raise SystemExit(0)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "gradlew.bat").write_text(
        "\n".join(
            [
                "@echo off",
                f"\"{sys.executable}\" \"{probe}\" \"{sentinel}\" %*",
                "exit /b %ERRORLEVEL%",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    storage = RunStorage(root / "runs")
    state = RunState(project_root=root, task="build")
    runner = GradleBuildRunner(
        reporting=storage,
        environment_overrides={"GRADLE_USER_HOME": str(tmp_path / "isolated-gradle-home")},
    )

    result = runner.run(_inspect(root), state, ExecutionLimits(process_timeout_seconds=10))

    assert result.success is True
    assert sentinel.read_text(encoding="utf-8") == str(tmp_path / "isolated-gradle-home")
    events = [
        json.loads(line)
        for line in storage.paths_for(state.run_id).events_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["payload"]["environment_overrides"]["GRADLE_USER_HOME"] == str(tmp_path / "isolated-gradle-home")
