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
from pd_agent.context import ContextItem
from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ExecutionLimits, ProviderContinuation, RunState, RunStatus, ToolCall, ToolResult, ToolResultStatus
from pd_agent.core.errors import ProviderError
from pd_agent.project import ProjectInspectionStatus, ProjectInspector, ProjectSnapshot
from pd_agent.reporting import FinalReport, RunEventType, RunStorage
from pd_agent.artifacts import ArtifactValidator
from pd_agent.tools import ToolExecutor, create_filesystem_tools
import pd_agent.runtime.engine as runtime_engine


def _tool_names(request: AgentRequest) -> tuple[str, ...]:
    return tuple(str(tool["name"]) for tool in request.tools)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _retained_read_result(*, path: str, content: str, bytes_total: int | None = None, truncated: bool = False) -> ToolResult:
    output = {
        "path": path,
        "content": content,
        "bytes_total": bytes_total if bytes_total is not None else len(content.encode("utf-8")),
        "truncated": truncated,
    }
    metadata = {"changed": False, "truncated": truncated}
    if bytes_total is not None:
        metadata["bytes_total"] = bytes_total
    return ToolResult(
        call_id="1",
        tool_name="read_file",
        status=ToolResultStatus.SUCCESS,
        output=output,
        metadata=metadata,
    )


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


def _controller(
    root: Path,
    provider: ScriptedProvider,
    *,
    limits: ExecutionLimits | None = None,
) -> tuple[RunController, RunStorage]:
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


def _runtime(
    root: Path,
    provider: ScriptedProvider,
    *,
    limits: ExecutionLimits | None = None,
    context_manager: ContextManager | None = None,
) -> tuple[AgentRuntime, RunStorage, ProjectSnapshot]:
    storage = RunStorage(root / "runs")
    runtime = AgentRuntime(
        provider=provider,
        tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        build_runner=GradleBuildRunner(reporting=storage),
        artifact_validator=ArtifactValidator(reporting=storage),
        context_manager=context_manager or ContextManager(),
        reporting=storage,
        model_config={},
    )
    snapshot = ProjectInspector().inspect(root)
    return runtime, storage, snapshot


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
    assert provider.requests[0].tool_results == ()
    assert any("BUILD SUCCESSFUL" in line for line in paths.events_jsonl.read_text(encoding="utf-8").splitlines()) is False
    assert run_state.changed_files == ("src/main/java/com/example/ExampleMod.java",)
    assert report.files_changed == ("src/main/java/com/example/ExampleMod.java",)


def test_create_file_records_changed_file(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "create-file", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="create",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="create_file",
                        arguments={
                            "path": "src/main/java/com/example/NewFile.java",
                            "content": "package com.example; class NewFile {}\n",
                        },
                    ),
                ),
            ),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "create file")
    paths = storage.paths_for(run_state.run_id)

    assert run_state.state.value == "COMPLETED"
    assert run_state.changed_files == ("src/main/java/com/example/NewFile.java",)
    assert report.files_changed == ("src/main/java/com/example/NewFile.java",)
    assert paths.final_report_json.exists()


def test_model_response_usage_is_persisted_in_events(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "usage", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(),
                usage={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
                provider_metadata={"provider": "fake", "model": "fake-model"},
            ),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, _report = controller.run(root, "inspect usage")
    events = storage.read_events(run_state.run_id)

    model_events = [event for event in events if event.event_type == RunEventType.MODEL_RESPONDED]
    assert model_events
    assert model_events[0].payload["usage"] == {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}


def test_logical_provider_request_count_is_authoritative_and_persisted(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "logical-count", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(),
                usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                provider_metadata={"provider": "fake", "model": "fake-model"},
            ),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "count requests")

    assert run_state.logical_provider_request_count == 1
    assert len(provider.requests) == 1
    assert report.limits_usage is not None
    assert report.limits_usage["logical_provider_request_count"] == 1
    assert storage.read_run_state(run_state.run_id).logical_provider_request_count == 1


def test_logical_provider_request_count_increments_before_provider_error(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "logical-error", build_state="pass")
    provider = ScriptedProvider([ProviderError("boom", kind="protocol", provider="fake", retryable=False)])
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "provider fails")

    assert run_state.state.value == "FAILED"
    assert run_state.logical_provider_request_count == 1
    assert len(provider.requests) == 1
    assert report.limits_usage is not None
    assert report.limits_usage["logical_provider_request_count"] == 1
    assert storage.read_run_state(run_state.run_id).logical_provider_request_count == 1


def test_build_fail_diagnose_correct_rebuild(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "repair", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(assistant_message="plan", tool_calls=()),
            AgentResponse(
                assistant_message="diagnose",
                tool_calls=(
                    ToolCall(
                        call_id="2",
                        tool_name="read_file",
                        arguments={"path": "build-state.txt", "max_bytes": 16},
                    ),
                ),
            ),
            AgentResponse(
                assistant_message="rebuild",
                tool_calls=(
                    ToolCall(
                        call_id="3",
                        tool_name="write_file",
                        arguments={"path": "build-state.txt", "content": "pass\n"},
                    ),
                ),
            ),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "repair the build")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert run_state.build_attempt_count == 2
    assert len(provider.requests) == 3
    assert provider.requests[1].tool_calls == ()
    assert provider.requests[1].tool_results == ()
    assert [call.call_id for call in provider.requests[2].tool_calls] == ["2"]
    assert [result.call_id for result in provider.requests[2].tool_results] == ["2"]
    assert storage.paths_for(run_state.run_id).final_report_md.exists()


def test_planning_read_then_write_continues_to_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "plan-read-write", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),
                ),
            ),
            AgentResponse(
                assistant_message="edit",
                tool_calls=(
                    ToolCall(call_id="2", tool_name="write_file", arguments={"path": "build-state.txt", "content": "pass\n"}),
                ),
            ),
        ]
    )
    controller, _storage = _controller(root, provider)

    run_state, report = controller.run(root, "read then write")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert len(provider.requests) == 2
    assert provider.requests[0].tool_results == ()
    assert [result.call_id for result in provider.requests[1].tool_results] == ["1"]
    assert [call.call_id for call in provider.requests[1].tool_calls] == ["1"]


def test_invalid_tool_call_is_blocked_and_run_continues(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "bad-tool", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(ToolCall(call_id="1", tool_name="no_such_tool", arguments={}),),
            ),
            AgentResponse(
                assistant_message="recover",
                tool_calls=(),
            ),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "bad tool")
    events = storage.read_events(run_state.run_id)
    violation_events = [event for event in events if event.event_type == RunEventType.ACTION_GATE_VIOLATION]

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert run_state.termination_reason == "completed"
    assert violation_events
    assert violation_events[0].payload["requested_tool_names"] == ["no_such_tool"]
    assert violation_events[0].payload["unavailable_tool_names"] == ["no_such_tool"]
    assert violation_events[0].payload["gate_violation"] is True
    assert len(provider.requests) == 2
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
    assert run_state.changed_files == ()


def test_first_file_exists_can_recover_to_write_and_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "file-exists-recover", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="create_file",
                        arguments={"path": "build-state.txt", "content": "pass\n"},
                    ),
                ),
            ),
            AgentResponse(
                assistant_message="recover",
                tool_calls=(
                    ToolCall(
                        call_id="2",
                        tool_name="write_file",
                        arguments={"path": "build-state.txt", "content": "pass\n"},
                    ),
                ),
            ),
        ]
    )
    controller, storage = _controller(
        root,
        provider,
        limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5),
    )

    run_state, report = controller.run(root, "recover from file exists")
    events = storage.read_events(run_state.run_id)
    model_called_events = [event for event in events if event.event_type == RunEventType.MODEL_CALLED]

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert run_state.termination_reason == "completed"
    assert run_state.build_attempt_count == 1
    assert len(provider.requests) == 2
    assert provider.requests[1].tool_results[0].status.value == "rejected"
    assert provider.requests[1].tool_results[0].metadata["rejection_code"] == "file_exists"
    assert provider.requests[1].tool_results[0].metadata["recoverable"] is True
    assert "use write_file" in (provider.requests[1].tool_results[0].error or "")
    assert "consecutive_recoverable_rejections: 1" in provider.requests[1].messages[0].content
    assert any(event.payload["consecutive_recoverable_rejections"] == 1 for event in model_called_events)


def test_repeated_file_exists_rejection_fails_controlled(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "file-exists-repeat", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="create_file",
                        arguments={"path": "build-state.txt", "content": "pass\n"},
                    ),
                ),
            ),
            AgentResponse(
                assistant_message="retry",
                tool_calls=(
                    ToolCall(
                        call_id="2",
                        tool_name="create_file",
                        arguments={"path": "build-state.txt", "content": "pass\n"},
                    ),
                ),
            ),
        ]
    )
    controller, storage = _controller(
        root,
        provider,
        limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5),
    )

    run_state, report = controller.run(root, "repeat file exists")
    events = storage.read_events(run_state.run_id)

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert run_state.termination_reason == "repeated recoverable tool rejection without operational progress"
    assert report.termination_reason == "repeated recoverable tool rejection without operational progress"
    assert len(provider.requests) == 2
    assert run_state.build_attempt_count == 0
    assert provider.requests[1].tool_results[0].metadata["rejection_code"] == "file_exists"
    assert provider.requests[1].tool_results[0].metadata["recoverable"] is True
    assert any(
        event.payload["consecutive_recoverable_rejections"] == 1
        for event in events
        if event.event_type == RunEventType.MODEL_CALLED
    )


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
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5))

    run_state, report = controller.run(root, "loop")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert run_state.termination_reason == "repeated no-op tool calls"
    assert report.termination_reason == "repeated no-op tool calls"
    assert run_state.build_attempt_count == 1
    assert len(provider.requests) == 2


def test_antiloop_stops_on_repeated_build_failure(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "build-loop", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(assistant_message="plan", tool_calls=()),
            AgentResponse(
                assistant_message="diagnose",
                tool_calls=(
                    ToolCall(call_id="2", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),
                ),
            ),
            AgentResponse(assistant_message="correct", tool_calls=()),
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5))

    run_state, report = controller.run(root, "build loop")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert run_state.termination_reason == "repeated build failure"
    assert report.termination_reason == "repeated build failure"
    assert "internal error" not in (run_state.termination_reason or "").lower()
    assert "StateTransitionError" not in (run_state.last_error or "")
    assert run_state.build_attempt_count == 2
    assert len(provider.requests) == 3


def test_action_transition_policy_escalates_explicitly_at_threshold(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "policy", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="step1",
                tool_calls=(ToolCall(call_id="1", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),),
            ),
            AgentResponse(assistant_message="step2", tool_calls=(ToolCall(call_id="2", tool_name="search_text", arguments={"query": "fail", "paths": ["build-state.txt"], "max_results": 5}),)),
            AgentResponse(assistant_message="step3", tool_calls=(ToolCall(call_id="3", tool_name="list_directory", arguments={"path": "."}),)),
            AgentResponse(assistant_message="step4", tool_calls=(ToolCall(call_id="4", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step5", tool_calls=(ToolCall(call_id="5", tool_name="write_file", arguments={"path": "build-state.txt", "content": "still fail\n"}),)),
            AgentResponse(assistant_message="step6", tool_calls=(ToolCall(call_id="6", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step7", tool_calls=(ToolCall(call_id="7", tool_name="write_file", arguments={"path": "build-state.txt", "content": "pass\n"}),)),
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5))

    run_state, report = controller.run(root, "policy")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert len(provider.requests) == 7
    for index in range(3):
        assert "ACTION REQUIRED" not in provider.requests[index].messages[0].content
        assert "escalation_state: normal" in provider.requests[index].messages[0].content
    assert "consecutive_inspection_steps: 3" in provider.requests[3].messages[0].content
    assert "escalation_state: action_required" in provider.requests[3].messages[0].content
    assert "ACTION REQUIRED: Investigation has consumed several consecutive steps without operational progress." in provider.requests[3].messages[0].content
    assert "Use the evidence already gathered to perform a concrete modification or other task-directed action now" in provider.requests[3].messages[0].content
    assert "If further inspection is required, identify the specific unresolved blocker" in provider.requests[3].messages[0].content
    assert "existing path or observed existing file -> write_file" in provider.requests[0].messages[0].content
    assert "genuinely new/nonexistent path -> create_file" in provider.requests[0].messages[0].content
    assert "recent_inspected_paths" in provider.requests[0].messages[0].content
    assert "prefer files and symbols directly supported by the task and retained inspection evidence" in provider.requests[0].messages[0].content
    assert "preserve unrelated structure, declarations, metadata, configuration, entrypoints and public contracts" in provider.requests[0].messages[0].content
    assert "if the evidence is insufficient to choose a target confidently" in provider.requests[0].messages[0].content
    assert "phase: PLANNING" in provider.requests[4].messages[0].content
    assert "escalation_state: action_required" in provider.requests[4].messages[0].content
    assert "ACTION REQUIRED" in provider.requests[4].messages[0].content
    assert "phase: DIAGNOSING" in provider.requests[5].messages[0].content
    assert "escalation_state: normal" in provider.requests[5].messages[0].content
    assert "ACTION REQUIRED" not in provider.requests[5].messages[0].content
    assert "phase: CORRECTING" in provider.requests[6].messages[0].content
    assert "escalation_state: normal" in provider.requests[6].messages[0].content
    assert "ACTION REQUIRED" not in provider.requests[6].messages[0].content


def test_action_transition_escalates_and_stops_before_exhaustion(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "stall", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(assistant_message="step1", tool_calls=(ToolCall(call_id="1", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step2", tool_calls=(ToolCall(call_id="2", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step3", tool_calls=(ToolCall(call_id="3", tool_name="read_file", arguments={"path": "settings.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step4", tool_calls=(ToolCall(call_id="4", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step5", tool_calls=(ToolCall(call_id="5", tool_name="read_file", arguments={"path": "build.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step6", tool_calls=(ToolCall(call_id="6", tool_name="read_file", arguments={"path": "src/main/resources/fabric.mod.json", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step7", tool_calls=(ToolCall(call_id="7", tool_name="read_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step8", tool_calls=(ToolCall(call_id="8", tool_name="read_file", arguments={"path": "README.md", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step9", tool_calls=(ToolCall(call_id="9", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=20, max_tool_calls=20, max_build_attempts=5))

    run_state, report = controller.run(root, "stall")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert run_state.termination_reason == "repeated action gate violation without operational progress"
    assert "IndexError" not in (run_state.last_error or "")
    assert run_state.agent_step_count == 9
    assert len(provider.requests) == 9
    events = _storage.read_events(run_state.run_id)
    violation_events = [event for event in events if event.event_type == RunEventType.ACTION_GATE_VIOLATION]
    assert len(violation_events) == 2
    assert violation_events[0].payload["requested_tool_names"] == ["read_file"]
    assert violation_events[1].payload["requested_tool_names"] == ["read_file"]
    assert all(event.payload["gate_violation"] is True for event in violation_events)
    assert run_state.tool_call_count == 7


def test_action_only_zero_tool_calls_advances_to_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "action-only-build", build_state="pass")
    _write(root / "notes.txt", "alpha\nbeta\n")
    provider = ScriptedProvider(
        [
            AgentResponse(assistant_message="step1", tool_calls=(ToolCall(call_id="1", tool_name="read_file", arguments={"path": "notes.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step2", tool_calls=(ToolCall(call_id="2", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step3", tool_calls=(ToolCall(call_id="3", tool_name="read_file", arguments={"path": "settings.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step4", tool_calls=(ToolCall(call_id="4", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step5", tool_calls=(ToolCall(call_id="5", tool_name="read_file", arguments={"path": "build.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step6", tool_calls=(ToolCall(call_id="6", tool_name="read_file", arguments={"path": "src/main/resources/fabric.mod.json", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step7", tool_calls=(ToolCall(call_id="7", tool_name="read_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step8", tool_calls=()),
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=20, max_tool_calls=20, max_build_attempts=5))

    run_state, report = controller.run(root, "action only zero tool call")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert run_state.build_attempt_count >= 1
    assert len(provider.requests) == 8
    offered = _tool_names(provider.requests[7])
    assert "list_directory" not in offered
    assert "read_file" not in offered
    assert "search_text" not in offered
    assert {"write_file", "create_file", "delete_file"}.issubset(set(offered))
    assert "retained-file:notes.txt" in provider.requests[7].messages[0].content


def test_action_gate_blocks_unoffered_tool_and_keeps_running(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "unoffered-tool", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(assistant_message="step1", tool_calls=(ToolCall(call_id="1", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step2", tool_calls=(ToolCall(call_id="2", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step3", tool_calls=(ToolCall(call_id="3", tool_name="read_file", arguments={"path": "settings.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step4", tool_calls=(ToolCall(call_id="4", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step5", tool_calls=(ToolCall(call_id="5", tool_name="read_file", arguments={"path": "build.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step6", tool_calls=(ToolCall(call_id="6", tool_name="read_file", arguments={"path": "src/main/resources/fabric.mod.json", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step7", tool_calls=(ToolCall(call_id="7", tool_name="read_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step8", tool_calls=(ToolCall(call_id="8", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step9", tool_calls=()),
        ]
    )
    controller, storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=20, max_tool_calls=20, max_build_attempts=5))

    run_state, report = controller.run(root, "unoffered tool")
    events = storage.read_events(run_state.run_id)
    violation_events = [event for event in events if event.event_type == RunEventType.ACTION_GATE_VIOLATION]

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert run_state.termination_reason == "completed"
    assert run_state.build_attempt_count >= 1
    assert run_state.tool_call_count == 7
    assert len(provider.requests) == 9
    assert violation_events
    assert violation_events[0].payload["requested_tool_names"] == ["read_file"]
    assert violation_events[0].payload["offered_tool_names"] == ["write_file", "create_file", "delete_file"]
    assert violation_events[0].payload["unavailable_tool_names"] == ["read_file"]
    assert violation_events[0].payload["gate_violation"] is True
    assert "Tool 'read_file' is not available in the current action gate." in provider.requests[8].tool_results[0].error
    assert provider.requests[8].tool_results[0].metadata["gate_violation"] is True
    assert not any(event.payload["call"]["call_id"] == "8" for event in events if event.event_type == RunEventType.TOOL_EXECUTED)
    assert any(event.payload["action_gate_state"] == "focused_action" for event in events if event.event_type == RunEventType.MODEL_CALLED)


def test_action_only_unoffered_tool_then_zero_tools_advances_to_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "action-only-gate", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(assistant_message="step1", tool_calls=(ToolCall(call_id="1", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step2", tool_calls=(ToolCall(call_id="2", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step3", tool_calls=(ToolCall(call_id="3", tool_name="read_file", arguments={"path": "settings.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step4", tool_calls=(ToolCall(call_id="4", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step5", tool_calls=(ToolCall(call_id="5", tool_name="read_file", arguments={"path": "build.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step6", tool_calls=(ToolCall(call_id="6", tool_name="read_file", arguments={"path": "src/main/resources/fabric.mod.json", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step7", tool_calls=(ToolCall(call_id="7", tool_name="read_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "max_bytes": 128}),)),
            AgentResponse(assistant_message="step8", tool_calls=(ToolCall(call_id="8", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step9", tool_calls=(ToolCall(call_id="9", tool_name="write_file", arguments={"path": "build-state.txt", "content": "pass\n"}),)),
        ]
    )
    controller, storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=20, max_tool_calls=20, max_build_attempts=5))

    run_state, report = controller.run(root, "action only gate")
    events = storage.read_events(run_state.run_id)
    violation_events = [event for event in events if event.event_type == RunEventType.ACTION_GATE_VIOLATION]

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert run_state.termination_reason == "completed"
    assert run_state.tool_call_count == 8
    assert run_state.build_attempt_count >= 1
    assert violation_events
    assert violation_events[0].payload["requested_tool_names"] == ["read_file"]
    assert violation_events[0].payload["offered_tool_names"] == ["write_file", "create_file", "delete_file"]
    assert violation_events[0].payload["unavailable_tool_names"] == ["read_file"]
    assert violation_events[0].payload["gate_violation"] is True
    model_called_events = [event for event in events if event.event_type == RunEventType.MODEL_CALLED]
    assert any(event.payload["action_gate_state"] == "focused_action" for event in model_called_events)
    assert "Tool 'read_file' is not available in the current action gate." in provider.requests[8].tool_results[0].error
    assert provider.requests[8].tool_results[0].metadata["gate_violation"] is True
    assert "list_directory" not in _tool_names(provider.requests[7])
    assert "read_file" not in _tool_names(provider.requests[7])
    response_events = [event for event in events if event.event_type == RunEventType.MODEL_RESPONDED]
    assert response_events[7].payload["requested_tool_names"] == ["read_file"]
    assert response_events[7].payload["gate_violation"] is True
    assert response_events[8].payload["requested_tool_names"] == ["write_file"]
    assert response_events[8].payload["gate_violation"] is False


def test_model_called_event_contains_safe_action_gate_telemetry(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "telemetry", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(),
                usage={"input_tokens": 4, "output_tokens": 1, "total_tokens": 5},
                provider_metadata={"provider": "fake", "model": "fake-model"},
            )
        ]
    )
    controller, storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=9, max_tool_calls=11, max_build_attempts=3))

    run_state, _report = controller.run(root, "telemetry")
    events = storage.read_events(run_state.run_id)
    called = next(event for event in events if event.event_type == RunEventType.MODEL_CALLED)

    assert called.payload["phase"] == "PLANNING"
    assert called.payload["action_gate_state"] == "normal"
    assert called.payload["escalation_state"] == "normal"
    assert called.payload["action_required"] is False
    assert called.payload["consecutive_inspection_steps"] == 0
    assert called.payload["agent_steps_remaining"] == 9
    assert called.payload["tool_calls_remaining"] == 11
    assert called.payload["build_attempts_remaining"] == 3
    assert called.payload["offered_tool_names"] == ["list_directory", "read_file", "search_text", "write_file", "create_file", "delete_file"]


def test_action_gate_policy_is_independent_of_external_context(tmp_path: Path) -> None:
    root_off = _runtime_project(tmp_path / "external-off", build_state="pass")
    root_on = _runtime_project(tmp_path / "external-on", build_state="pass")
    provider_off = ScriptedProvider([AgentResponse(assistant_message="plan", tool_calls=())])
    provider_on = ScriptedProvider([AgentResponse(assistant_message="plan", tool_calls=())])
    controller_off, storage_off = _controller(root_off, provider_off)
    controller_on, storage_on = _controller(root_on, provider_on)

    run_state_off, _ = controller_off.run(root_off, "external gate off")
    run_state_on, _ = controller_on.run(
        root_on,
        "external gate on",
        external_context=(ContextItem.from_text(source="brain", priority=1, label="yarn", content="retrieved yarn"),),
    )

    off_event = next(event for event in storage_off.read_events(run_state_off.run_id) if event.event_type == RunEventType.MODEL_CALLED)
    on_event = next(event for event in storage_on.read_events(run_state_on.run_id) if event.event_type == RunEventType.MODEL_CALLED)

    assert off_event.payload["action_gate_state"] == "normal"
    assert on_event.payload["action_gate_state"] == "normal"
    assert off_event.payload["offered_tool_names"] == on_event.payload["offered_tool_names"]
    assert _tool_names(provider_off.requests[0]) == _tool_names(provider_on.requests[0])


def test_retained_inspection_evidence_is_visible_in_followup_context(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-visible", build_state="pass")
    _write(root / "notes.txt", "alpha\nbeta\n")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "notes.txt", "max_bytes": 32}),
                ),
            ),
            AgentResponse(assistant_message="continue", tool_calls=()),
        ]
    )
    controller, _storage = _controller(root, provider)

    run_state, report = controller.run(root, "retained evidence")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert len(provider.requests) == 2
    followup = provider.requests[1].messages[0].content
    assert "retained_inspection_evidence_count: 1" in followup
    assert "retained-inspection-evidence" in followup
    assert "retained-file:notes.txt" in followup
    assert "path: notes.txt" in followup
    assert "alpha" in followup


def test_brain_context_and_retained_evidence_coexist(tmp_path: Path) -> None:
    root_off = _runtime_project(tmp_path / "retained-off", build_state="pass")
    root_on = _runtime_project(tmp_path / "retained-on", build_state="pass")
    _write(root_off / "notes.txt", "alpha\nbeta\n")
    _write(root_on / "notes.txt", "alpha\nbeta\n")
    provider_off = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "notes.txt", "max_bytes": 32}),
                ),
            ),
            AgentResponse(assistant_message="continue", tool_calls=()),
        ]
    )
    provider_on = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "notes.txt", "max_bytes": 32}),
                ),
            ),
            AgentResponse(assistant_message="continue", tool_calls=()),
        ]
    )
    controller_off, _storage_off = _controller(root_off, provider_off)
    controller_on, _storage_on = _controller(root_on, provider_on)

    run_state_off, report_off = controller_off.run(root_off, "retained off")
    run_state_on, report_on = controller_on.run(
        root_on,
        "retained on",
        external_context=(ContextItem.from_text(source="brain", priority=1, label="yarn", content="retrieved yarn"),),
    )

    assert run_state_off.state.value == "COMPLETED"
    assert report_off.final_state.value == "COMPLETED"
    assert run_state_on.state.value == "COMPLETED"
    assert report_on.final_state.value == "COMPLETED"
    off_followup = provider_off.requests[1].messages[0].content
    on_followup = provider_on.requests[1].messages[0].content
    assert "retained-file:notes.txt" in off_followup
    assert "retained-file:notes.txt" in on_followup
    assert "retrieved yarn" not in off_followup
    assert "retrieved yarn" in on_followup
    assert "prefer files and symbols directly supported by the task and retained inspection evidence" in off_followup
    assert "prefer files and symbols directly supported by the task and retained inspection evidence" in on_followup
    assert "preserve unrelated structure, declarations, metadata, configuration, entrypoints and public contracts" in off_followup
    assert "preserve unrelated structure, declarations, metadata, configuration, entrypoints and public contracts" in on_followup


def test_retained_inspection_evidence_respects_max_total_bytes(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-total", build_state="pass")
    provider = ScriptedProvider([])
    runtime, _storage, _snapshot = _runtime(root, provider)
    run_state = RunState(project_root=root, task="evidence", agent_step_count=1)
    content = "x" * 4096

    for index in range(7):
        run_state.agent_step_count = index + 1
        runtime._record_retained_file_evidence(  # noqa: SLF001
            run_state,
            _retained_read_result(path=f"blob-{index}.txt", content=content, bytes_total=len(content.encode("utf-8"))),
        )

    total_bytes = sum(entry.excerpt_bytes for entry in runtime._telemetry.retained_file_evidence.values())  # noqa: SLF001
    assert total_bytes <= 24576
    assert len(runtime._telemetry.retained_file_evidence) == 6  # noqa: SLF001


def test_retained_inspection_evidence_tie_breaks_by_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _runtime_project(tmp_path / "retained-tie", build_state="pass")
    provider = ScriptedProvider([])
    runtime, _storage, _snapshot = _runtime(root, provider)
    run_state = RunState(project_root=root, task="evidence", agent_step_count=1)
    content = "x" * 4096

    monkeypatch.setattr(runtime_engine, "_MAX_RETAINED_FILE_EVIDENCE", 1)
    monkeypatch.setattr(runtime_engine, "_MAX_RETAINED_FILE_TOTAL_BYTES", 10_000)

    for path in ("b.txt", "a.txt"):
        runtime._record_retained_file_evidence(  # noqa: SLF001
            run_state,
            _retained_read_result(path=path, content=content, bytes_total=len(content.encode("utf-8"))),
        )

    paths = runtime._retained_file_evidence_paths()  # noqa: SLF001
    assert "a.txt" not in paths
    assert paths[0] == "b.txt"
    assert len(paths) == 1


def test_retained_inspection_evidence_reread_updates_entry_and_recency(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-reread", build_state="pass")
    provider = ScriptedProvider([])
    runtime, _storage, _snapshot = _runtime(root, provider)
    run_state = RunState(project_root=root, task="evidence", agent_step_count=1)

    runtime._record_retained_file_evidence(  # noqa: SLF001
        run_state,
        _retained_read_result(path="notes.txt", content="alpha", bytes_total=5),
    )
    run_state.agent_step_count = 4
    runtime._record_retained_file_evidence(  # noqa: SLF001
        run_state,
        _retained_read_result(path="notes.txt", content="beta", bytes_total=4),
    )

    assert len(runtime._telemetry.retained_file_evidence) == 1  # noqa: SLF001
    entry = runtime._telemetry.retained_file_evidence["notes.txt"]  # noqa: SLF001
    assert entry.observed_step == 4
    assert entry.excerpt == "beta"
    assert runtime._retained_file_evidence_paths() == ("notes.txt",)  # noqa: SLF001


def test_retained_inspection_evidence_max_context_bytes_is_bounded(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-context-limit", build_state="pass")
    _write(root / "notes.txt", "alpha\nbeta\n")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "notes.txt", "max_bytes": 32}),
                ),
            ),
            AgentResponse(assistant_message="continue", tool_calls=()),
        ]
    )
    runtime, _storage, snapshot = _runtime(root, provider)
    run_state = RunState(project_root=root, task="bounded")
    run_state.transition_to(RunStatus.INSPECTING)

    run_state, report = runtime.run(
        run_state=run_state,
        project_snapshot=snapshot,
        task="bounded",
        limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5, max_context_bytes=1200),
    )

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    message = provider.requests[1].messages[0]
    assert message.metadata["context_max_bytes"] == 1200
    assert message.metadata["context_bytes"] <= 1200


def test_retained_inspection_evidence_delete_invalidates_path(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-delete", build_state="pass")
    _write(root / "notes.txt", "alpha\nbeta\n")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "notes.txt", "max_bytes": 32}),
                ),
            ),
            AgentResponse(
                assistant_message="delete",
                tool_calls=(
                    ToolCall(call_id="2", tool_name="delete_file", arguments={"path": "notes.txt"}),
                ),
            ),
            AgentResponse(assistant_message="continue", tool_calls=()),
        ]
    )
    controller, _storage = _controller(root, provider)

    run_state, report = controller.run(root, "delete evidence")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert len(provider.requests) == 2
    assert "retained-file:notes.txt" in provider.requests[1].messages[0].content
    assert not (root / "notes.txt").exists()


def test_retained_inspection_evidence_delete_invalidates_path_directly(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-delete-direct", build_state="pass")
    provider = ScriptedProvider([])
    runtime, _storage, _snapshot = _runtime(root, provider)
    run_state = RunState(project_root=root, task="evidence", agent_step_count=1)

    runtime._record_retained_file_evidence(  # noqa: SLF001
        run_state,
        _retained_read_result(path="notes.txt", content="alpha", bytes_total=5),
    )
    runtime._record_retained_file_evidence(  # noqa: SLF001
        run_state,
        ToolResult(
            call_id="2",
            tool_name="delete_file",
            status=ToolResultStatus.SUCCESS,
            output={"path": "notes.txt", "changed": True},
            metadata={"changed": True, "path": "notes.txt"},
        ),
    )

    assert "notes.txt" not in runtime._telemetry.retained_file_evidence  # noqa: SLF001


def test_retained_inspection_evidence_is_invalidated_by_mutation(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-invalidate", build_state="fail")
    _write(root / "notes.txt", "alpha\nbeta\n")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "notes.txt", "max_bytes": 32}),
                ),
            ),
            AgentResponse(
                assistant_message="mutate",
                tool_calls=(
                    ToolCall(
                        call_id="2",
                        tool_name="write_file",
                        arguments={"path": "notes.txt", "content": "gamma\n"},
                    ),
                ),
            ),
            AgentResponse(assistant_message="diagnose", tool_calls=()),
        ]
    )
    controller, _storage = _controller(root, provider)

    run_state, report = controller.run(root, "invalidate evidence")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert len(provider.requests) == 3
    assert "retained-file:notes.txt" in provider.requests[1].messages[0].content
    assert "retained-file:notes.txt" not in provider.requests[2].messages[0].content
    assert "alpha" not in provider.requests[2].messages[0].content
    assert "retained_inspection_evidence_count: 0" in provider.requests[2].messages[0].content


def test_retained_inspection_evidence_is_bounded_and_evicts_oldest(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-evict", build_state="pass")
    provider = ScriptedProvider([])
    runtime, _storage, _snapshot = _runtime(root, provider)
    run_state = RunState(project_root=root, task="evidence", agent_step_count=1)

    for index in range(9):
        run_state.agent_step_count = index + 1
        runtime._record_retained_file_evidence(  # noqa: SLF001
            run_state,
            _retained_read_result(
                path=f"notes-{index}.txt",
                content=f"file-{index}",
                bytes_total=len(f"file-{index}".encode("utf-8")),
            ),
        )

    assert len(runtime._telemetry.retained_file_evidence) == 8  # noqa: SLF001
    assert "notes-0.txt" not in runtime._telemetry.retained_file_evidence  # noqa: SLF001
    assert runtime._retained_file_evidence_paths()[0] == "notes-1.txt"  # noqa: SLF001


def test_retained_inspection_evidence_truncates_utf8_prefix(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-truncate", build_state="pass")
    provider = ScriptedProvider([])
    runtime, _storage, _snapshot = _runtime(root, provider)
    run_state = RunState(project_root=root, task="evidence", agent_step_count=1)
    content = "漢字" * 5000

    runtime._record_retained_file_evidence(  # noqa: SLF001
        run_state,
        _retained_read_result(
            path="unicode.txt",
            content=content,
            bytes_total=len(content.encode("utf-8")),
            truncated=True,
        ),
    )

    entry = runtime._telemetry.retained_file_evidence["unicode.txt"]  # noqa: SLF001
    assert entry.truncated is True
    assert entry.excerpt_bytes <= 4096
    assert "\ufffd" not in entry.excerpt


def test_retained_inspection_evidence_resets_between_runs(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "retained-reset", build_state="pass")
    _write(root / "notes.txt", "alpha\nbeta\n")
    provider_one = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "notes.txt", "max_bytes": 32}),
                ),
            ),
            AgentResponse(assistant_message="continue", tool_calls=()),
        ]
    )
    runtime, _storage, snapshot = _runtime(root, provider_one)

    run_state_one = RunState(project_root=root, task="first run")
    run_state_one.transition_to(RunStatus.INSPECTING)
    run_state_one, report_one = runtime.run(
        run_state=run_state_one,
        project_snapshot=snapshot,
        task="first run",
        limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5),
    )

    assert run_state_one.state.value == "COMPLETED"
    assert report_one.final_state.value == "COMPLETED"
    assert "retained-file:notes.txt" in provider_one.requests[1].messages[0].content
    assert runtime._telemetry.retained_file_evidence  # noqa: SLF001

    provider_two = ScriptedProvider([AgentResponse(assistant_message="fresh", tool_calls=())])
    runtime.provider = provider_two
    run_state_two = RunState(project_root=root, task="second run")
    run_state_two.transition_to(RunStatus.INSPECTING)
    run_state_two, report_two = runtime.run(
        run_state=run_state_two,
        project_snapshot=snapshot,
        task="second run",
        limits=ExecutionLimits(max_agent_steps=10, max_tool_calls=10, max_build_attempts=5),
    )

    assert run_state_two.state.value == "COMPLETED"
    assert report_two.final_state.value == "COMPLETED"
    assert "retained-file:notes.txt" not in provider_two.requests[0].messages[0].content
    assert "alpha" not in provider_two.requests[0].messages[0].content


def test_action_transition_reset_clears_pressure_before_diagnosing(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "diagnose-reset", build_state="fail")
    provider = ScriptedProvider(
        [
            AgentResponse(assistant_message="step1", tool_calls=(ToolCall(call_id="1", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step2", tool_calls=(ToolCall(call_id="2", tool_name="search_text", arguments={"query": "fail", "paths": ["build-state.txt"], "max_results": 5}),)),
            AgentResponse(assistant_message="step3", tool_calls=(ToolCall(call_id="3", tool_name="list_directory", arguments={"path": "."}),)),
            AgentResponse(assistant_message="step4", tool_calls=(ToolCall(call_id="4", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step5", tool_calls=(ToolCall(call_id="5", tool_name="write_file", arguments={"path": "build-state.txt", "content": "still fail\n"}),)),
            AgentResponse(assistant_message="step6", tool_calls=(ToolCall(call_id="6", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),)),
            AgentResponse(assistant_message="step7", tool_calls=(ToolCall(call_id="7", tool_name="write_file", arguments={"path": "build-state.txt", "content": "pass\n"}),)),
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=15, max_tool_calls=15, max_build_attempts=5))

    run_state, report = controller.run(root, "diagnose reset")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert len(provider.requests) == 7
    assert "ACTION REQUIRED" in provider.requests[4].messages[0].content
    assert "phase: DIAGNOSING" in provider.requests[5].messages[0].content
    assert "escalation_state: normal" in provider.requests[5].messages[0].content
    assert "consecutive_inspection_steps: 0" in provider.requests[5].messages[0].content
    assert "ACTION REQUIRED" not in provider.requests[5].messages[0].content
    assert "phase: CORRECTING" in provider.requests[6].messages[0].content


def test_runtime_source_has_no_openai_imports() -> None:
    import pd_agent.runtime.controller as controller_module
    import pd_agent.runtime.engine as engine_module

    source = inspect.getsource(controller_module) + inspect.getsource(engine_module)
    lower = source.lower()

    assert "import openai" not in lower
    assert "from openai" not in lower
    assert "requests" not in lower
    assert "subprocess" not in lower


def test_multiple_tool_calls_continue_with_structured_results(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "multi-tool", build_state="fail")
    continuations = (
        ProviderContinuation(
            provider="gemini",
            kind="thought_signature",
            target_type="function_call",
            target_id="1",
            position=0,
            payload={"thought_signature_b64": "c2lnLWE="},
        ),
        ProviderContinuation(
            provider="gemini",
            kind="thought_signature",
            target_type="function_call",
            target_id="2",
            position=1,
            payload={"thought_signature_b64": "c2lnLWI="},
        ),
    )
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="plan",
                tool_calls=(
                    ToolCall(call_id="1", tool_name="read_file", arguments={"path": "build-state.txt", "max_bytes": 16}),
                    ToolCall(call_id="2", tool_name="list_directory", arguments={"path": "."}),
                ),
                provider_continuations=continuations,
            ),
            AgentResponse(
                assistant_message="diagnose",
                tool_calls=(
                    ToolCall(
                        call_id="3",
                        tool_name="write_file",
                        arguments={"path": "build-state.txt", "content": "pass\n"},
                    ),
                ),
            ),
            AgentResponse(assistant_message="done", tool_calls=()),
        ]
    )
    controller, _storage = _controller(root, provider)

    run_state, report = controller.run(root, "multi tool continuation")

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert len(provider.requests) == 2
    assert [call.call_id for call in provider.requests[1].tool_calls] == ["1", "2"]
    assert [result.call_id for result in provider.requests[1].tool_results] == ["1", "2"]
    assert provider.requests[1].provider_continuations == continuations
    assert all(result.status.value == "success" for result in provider.requests[1].tool_results)


def test_multi_file_single_response_applies_all_mutations_before_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "multi-file", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="batch",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="write_file",
                        arguments={
                            "path": "src/main/java/com/example/ExampleMod.java",
                            "content": "package com.example; class ExampleMod { int a = 1; }\n",
                        },
                    ),
                    ToolCall(
                        call_id="2",
                        tool_name="create_file",
                        arguments={
                            "path": "src/main/java/com/example/FeatureHelper.java",
                            "content": "package com.example; class FeatureHelper {}\n",
                        },
                    ),
                    ToolCall(
                        call_id="3",
                        tool_name="write_file",
                        arguments={
                            "path": "src/main/resources/fabric.mod.json",
                            "content": "{\n  \"enabled\": true\n}\n",
                        },
                    ),
                ),
            ),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "multi file batch")
    events = storage.read_events(run_state.run_id)

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert len(provider.requests) == 1
    assert run_state.tool_call_count == 3
    assert run_state.build_attempt_count == 1
    assert run_state.changed_files == (
        "src/main/java/com/example/ExampleMod.java",
        "src/main/java/com/example/FeatureHelper.java",
        "src/main/resources/fabric.mod.json",
    )
    tool_requested = [event for event in events if event.event_type == RunEventType.TOOL_REQUESTED]
    tool_executed = [event for event in events if event.event_type == RunEventType.TOOL_EXECUTED]
    file_changed = [event for event in events if event.event_type == RunEventType.FILE_CHANGED]
    assert [event.payload["call_id"] for event in tool_requested] == ["1", "2", "3"]
    assert [event.payload["call"]["call_id"] for event in tool_executed] == ["1", "2", "3"]
    assert len(file_changed) == 3
    assert events.index(next(event for event in events if event.event_type == RunEventType.BUILD_STARTED)) > events.index(
        file_changed[-1]
    )
    assert (root / "src" / "main" / "java" / "com" / "example" / "ExampleMod.java").read_text(encoding="utf-8").endswith(
        "int a = 1; }\n"
    )
    assert (root / "src" / "main" / "java" / "com" / "example" / "FeatureHelper.java").exists()
    assert (root / "src" / "main" / "resources" / "fabric.mod.json").read_text(encoding="utf-8") == "{\n  \"enabled\": true\n}\n"
    assert any(event.event_type == RunEventType.BUILD_STARTED for event in events)


def test_multi_turn_source_and_resource_builds_after_both_mutations(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "multi-turn-resource", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="source",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="write_file",
                        arguments={
                            "path": "src/main/java/com/example/ExampleMod.java",
                            "content": "package com.example; class ExampleMod { int a = 1; }\n",
                        },
                    ),
                ),
            ),
            AgentResponse(
                assistant_message="resource",
                tool_calls=(
                    ToolCall(
                        call_id="2",
                        tool_name="create_file",
                        arguments={
                            "path": "src/main/resources/assets/examplemod/lang/en_us.json",
                            "content": "{}\n",
                        },
                    ),
                ),
            ),
        ]
    )
    controller, storage = _controller(
        root,
        provider,
    )

    run_state, report = controller.run(
        root,
        "source and resource",
        pending_mutation_targets=(
            "role:source",
            "src/main/resources/assets/examplemod/lang/en_us.json",
        ),
    )
    events = storage.read_events(run_state.run_id)

    assert run_state.state == RunStatus.COMPLETED
    assert report.final_state == RunStatus.COMPLETED
    assert len(provider.requests) == 2
    assert run_state.pending_mutation_targets == ()
    assert run_state.completed_mutation_targets == (
        "role:source",
        "src/main/resources/assets/examplemod/lang/en_us.json",
    )
    assert run_state.changed_files == (
        "src/main/java/com/example/ExampleMod.java",
        "src/main/resources/assets/examplemod/lang/en_us.json",
    )
    assert run_state.build_attempt_count == 1
    build_index = events.index(next(event for event in events if event.event_type == RunEventType.BUILD_STARTED))
    file_changed_indices = [index for index, event in enumerate(events) if event.event_type == RunEventType.FILE_CHANGED]
    assert build_index > max(file_changed_indices)


def test_multi_turn_source_resource_and_data_requires_all_targets(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "multi-turn-data", build_state="pass")
    lang_path = "src/main/resources/assets/examplemod/lang/en_us.json"
    recipe_path = "src/main/resources/data/examplemod/recipe/server_core.json"
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="source",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="write_file",
                        arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"},
                    ),
                ),
            ),
            AgentResponse(
                assistant_message="lang",
                tool_calls=(
                    ToolCall(
                        call_id="2",
                        tool_name="create_file",
                        arguments={"path": lang_path, "content": "{}\n"},
                    ),
                ),
            ),
            AgentResponse(
                assistant_message="recipe",
                tool_calls=(
                    ToolCall(
                        call_id="3",
                        tool_name="create_file",
                        arguments={"path": recipe_path, "content": "{}\n"},
                    ),
                ),
            ),
        ]
    )
    controller, _storage = _controller(root, provider)

    run_state, report = controller.run(
        root,
        "source, resource and data",
        pending_mutation_targets=("role:source", lang_path, recipe_path),
    )

    assert run_state.state == RunStatus.COMPLETED
    assert report.final_state == RunStatus.COMPLETED
    assert len(provider.requests) == 3
    assert run_state.pending_mutation_targets == ()
    assert run_state.completed_mutation_targets == ("role:source", lang_path, recipe_path)
    assert run_state.build_attempt_count == 1


def test_multi_turn_wrong_target_does_not_complete_pending_target(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "multi-turn-wrong-target", build_state="pass")
    target = "src/main/resources/assets/examplemod/lang/en_us.json"
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="source",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="write_file",
                        arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"},
                    ),
                ),
            ),
            AgentResponse(
                assistant_message="wrong resource",
                tool_calls=(
                    ToolCall(
                        call_id="2",
                        tool_name="create_file",
                        arguments={"path": "src/main/resources/other.json", "content": "{}\n"},
                    ),
                ),
            ),
            AgentResponse(
                assistant_message="correct resource",
                tool_calls=(
                    ToolCall(
                        call_id="3",
                        tool_name="create_file",
                        arguments={"path": target, "content": "{}\n"},
                    ),
                ),
            ),
        ]
    )
    controller, _storage = _controller(root, provider)

    run_state, _report = controller.run(
        root,
        "source and resource",
        pending_mutation_targets=(target,),
    )

    assert len(provider.requests) == 3
    assert run_state.pending_mutation_targets == ()
    assert run_state.completed_mutation_targets == (target,)
    assert "src/main/resources/other.json" in run_state.changed_files
    assert run_state.build_attempt_count == 1


def test_multi_file_recoverable_rejection_keeps_later_mutations(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "multi-file-reject", build_state="pass")
    _write(root / "obsolete.txt", "delete me\n")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="batch",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="create_file",
                        arguments={
                            "path": "build-state.txt",
                            "content": "pass\n",
                        },
                    ),
                    ToolCall(
                        call_id="2",
                        tool_name="write_file",
                        arguments={
                            "path": "src/main/java/com/example/ExampleMod.java",
                            "content": "package com.example; class ExampleMod { int b = 2; }\n",
                        },
                    ),
                    ToolCall(
                        call_id="3",
                        tool_name="delete_file",
                        arguments={"path": "obsolete.txt"},
                    ),
                ),
            ),
        ]
    )
    controller, storage = _controller(root, provider)

    run_state, report = controller.run(root, "multi file rejection")
    events = storage.read_events(run_state.run_id)

    assert run_state.state.value == "COMPLETED"
    assert report.final_state.value == "COMPLETED"
    assert len(provider.requests) == 1
    assert run_state.termination_reason == "completed"
    assert run_state.changed_files == (
        "src/main/java/com/example/ExampleMod.java",
        "obsolete.txt",
    )
    assert run_state.tool_call_count == 3
    assert run_state.build_attempt_count == 1
    assert not (root / "obsolete.txt").exists()
    assert [event.payload["call_id"] for event in events if event.event_type == RunEventType.TOOL_REQUESTED] == ["1", "2", "3"]
    assert [event.payload["call"]["call_id"] for event in events if event.event_type == RunEventType.TOOL_EXECUTED] == ["2", "3"]
    rejected = next(event for event in events if event.event_type == RunEventType.TOOL_REJECTED)
    assert rejected.payload["call"]["call_id"] == "1"
    assert "file already exists" in rejected.payload["reason"]
    assert "use write_file" in rejected.payload["reason"]
    assert (root / "src" / "main" / "java" / "com" / "example" / "ExampleMod.java").read_text(encoding="utf-8").endswith(
        "int b = 2; }\n"
    )
    assert any(event.event_type == RunEventType.TOOL_REJECTED for event in events)
    assert any(event.event_type == RunEventType.BUILD_STARTED for event in events)
