from __future__ import annotations

import inspect
import json
import sys
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pd_agent import AgentRuntime, ContextManager, RunController
from pd_agent.build import GradleBuildRunner
from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ExecutionLimits, ToolCall
from pd_agent.core.errors import ProviderError
from pd_agent.project import ProjectInspectionStatus
from pd_agent.reporting import FinalReport, RunEventType, RunStorage
from pd_agent.artifacts import ArtifactValidator
from pd_agent.tools import ToolExecutor, create_filesystem_tools


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _runtime_project(root: Path, *, build_state: str = "pass") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "settings.gradle.kts", 'rootProject.name = "runtime"\n')
    _write(
        root / "build.gradle.kts",
        'plugins { id("fabric-loom") version "1.8-SNAPSHOT" }\n',
    )
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
              "id": "runtime-example",
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
    _write(root / "build-state.txt", f"{build_state}\n")

    script = root / "fake_gradle.py"
    _write(
        script,
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

            jar_path = root / "build" / "libs" / "runtime-example-1.0.0.jar"
            jar_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(jar_path, "w", compression=zipfile.ZIP_DEFLATED) as jar:
                jar.writestr(
                    "fabric.mod.json",
                    json.dumps(
                        {
                            "schemaVersion": 1,
                            "id": "runtime-example",
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
    _write(
        root / "gradlew.bat",
        f'@echo off\n"{sys.executable}" "{script}" %*\nexit /b %ERRORLEVEL%\n',
    )
    _write(root / "gradlew", "#!/bin/sh\n")
    return root


class ScriptedProvider:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[AgentRequest] = []

    def execute(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _controller(root: Path, provider: ScriptedProvider, *, limits: ExecutionLimits | None = None) -> tuple[RunController, RunStorage]:
    storage = RunStorage(root / "runs")
    controller = RunController(
        provider=provider,
        storage=storage,
        build_runner=GradleBuildRunner(reporting=storage),
        artifact_validator=ArtifactValidator(reporting=storage),
        context_manager=ContextManager(),
        tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        limits=limits or ExecutionLimits(),
    )
    return controller, storage


def test_edit_build_artifact_valid(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "ok", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="write_file",
                        arguments={
                            "path": "src/main/java/com/example/ExampleMod.java",
                            "content": "package com.example; class ExampleMod { int x = 1; }\n",
                        },
                    ),
                ),
            ),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "edit and build")
    paths = storage.paths_for(run_state.run_id)

    assert run_state.state.value == "COMPLETED"
    assert run_state.current_plan == "plan"
    assert run_state.artifact_result is not None
    assert report.final_state.value == "COMPLETED"
    assert paths.final_report_json.exists()
    assert paths.events_jsonl.exists()
    assert "project_root" in provider.requests[0].messages[0].content
    assert "tool_results" not in provider.requests[0].messages[-1].content
    assert any("BUILD SUCCESSFUL" in line for line in paths.events_jsonl.read_text(encoding="utf-8").splitlines()) is False


def test_build_fail_diagnose_correct_rebuild(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "repair", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(assistant_message="plan", tool_calls=()),
            AgentResponse(
                assistant_message="fix build state",
                tool_calls=(
                    ToolCall(
                        call_id="2",
                        tool_name="write_file",
                        arguments={"path": "build-state.txt", "content": "pass\n"},
                    ),
                ),
            ),
            AgentResponse(assistant_message="rebuild", tool_calls=()),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "repair the build")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert run_state.build_attempt_count == 2
    assert len(provider.requests) >= 2
    assert any("tool_results" in message.content for message in provider.requests[2].messages)
    assert storage.paths_for(run_state.run_id).final_report_md.exists()


def test_invalid_tool_call_fails(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "bad-tool", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(ToolCall(call_id="1", tool_name="no_such_tool", arguments={}),),
            )
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "bad tool")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert run_state.termination_reason == "tool rejected"
    assert storage.paths_for(run_state.run_id).final_report_json.exists()


def test_security_rejection_fails(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "security", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(ToolCall(call_id="1", tool_name="read_file", arguments={"path": "../secret.txt"}),),
            )
        ]
    )
    controller, _storage = _controller(root, provider)

    run_state, report = controller.run(root, "security")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert run_state.termination_reason == "tool rejected"


def test_provider_failure_fails_and_reports(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "provider", build_state="pass")
    provider = ScriptedProvider([ProviderError("boom", kind="protocol", provider="fake", retryable=False)])
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "provider fails")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert "boom" in (run_state.last_error or "")
    assert storage.paths_for(run_state.run_id).final_report_json.exists()


def test_limits_reached_stop_run(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "limits", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(),
            )
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=1, max_tool_calls=10, max_build_attempts=10))

    run_state, report = controller.run(root, "limit")

    assert run_state.state.value == "LIMIT_REACHED"
    assert report.final_state.value == "LIMIT_REACHED"
    assert run_state.termination_reason == "max_agent_steps"


def test_max_tool_calls_and_builds(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "tool-limit", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="write_file", arguments={"path": "build-state.txt", "content": "fail\n"}),
                    ToolCall(call_id="2", tool_name="write_file", arguments={"path": "build-state.txt", "content": "fail\n"}),
                ),
            ),
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=1, max_build_attempts=1))

    run_state, report = controller.run(root, "tool limit")

    assert run_state.state.value == "LIMIT_REACHED"
    assert report.final_state.value == "LIMIT_REACHED"
    assert run_state.termination_reason in {"max_tool_calls", "max_build_attempts reached"}


def test_antiloop_stops_on_repeated_noop(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "loop", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="write_file", arguments={"path": "build-state.txt", "content": "fail\n"}),
                ),
            ),
            AgentResponse(
                assistant_message="still failing",
                tool_calls=(
                    ToolCall(call_id="2", tool_name="write_file", arguments={"path": "build-state.txt", "content": "fail\n"}),
                ),
            ),
            AgentResponse(assistant_message="retry", tool_calls=()),
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5))

    run_state, report = controller.run(root, "loop")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert "repeated" in (run_state.termination_reason or "")


def test_runtime_source_has_no_openai_imports() -> None:
    import pd_agent.runtime.controller as controller_module
    import pd_agent.runtime.engine as engine_module

    source = inspect.getsource(controller_module) + inspect.getsource(engine_module)
    lower = source.lower()

    assert "import openai" not in lower
    assert "from openai" not in lower
    assert "requests" not in lower
    assert "subprocess" not in lower
