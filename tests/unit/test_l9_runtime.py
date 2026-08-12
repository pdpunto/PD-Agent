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
from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ExecutionLimits, ProviderContinuation, ToolCall
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
    assert provider.requests[0].tool_results == ()
    assert any("BUILD SUCCESSFUL" in line for line in paths.events_jsonl.read_text(encoding="utf-8").splitlines()) is False


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
    assert "escalation_state: normal" in provider.requests[3].messages[0].content
    assert "ACTION REQUIRED: Investigation has consumed several consecutive steps without operational progress." in provider.requests[4].messages[0].content
    assert "Use the evidence already gathered to perform a concrete modification or other task-directed action now" in provider.requests[4].messages[0].content
    assert "If further inspection is required, identify the specific unresolved blocker" in provider.requests[4].messages[0].content
    assert "escalation_state: action_required" in provider.requests[4].messages[0].content
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
            AgentResponse(assistant_message="step2", tool_calls=(ToolCall(call_id="2", tool_name="search_text", arguments={"query": "runtime", "paths": ["."], "max_results": 5}),)),
            AgentResponse(assistant_message="step3", tool_calls=(ToolCall(call_id="3", tool_name="list_directory", arguments={"path": "."}),)),
            AgentResponse(assistant_message="step4", tool_calls=(ToolCall(call_id="4", tool_name="read_file", arguments={"path": "gradle.properties", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step5", tool_calls=(ToolCall(call_id="5", tool_name="search_text", arguments={"query": "loader", "paths": ["."], "max_results": 5}),)),
            AgentResponse(assistant_message="step6", tool_calls=(ToolCall(call_id="6", tool_name="list_directory", arguments={"path": "src"}),)),
            AgentResponse(assistant_message="step7", tool_calls=(ToolCall(call_id="7", tool_name="read_file", arguments={"path": "settings.gradle.kts", "max_bytes": 64}),)),
            AgentResponse(assistant_message="step8", tool_calls=(ToolCall(call_id="8", tool_name="search_text", arguments={"query": "package", "paths": ["src"], "max_results": 5}),)),
        ]
    )
    controller, _storage = _controller(root, provider, limits=ExecutionLimits(max_agent_steps=20, max_tool_calls=20, max_build_attempts=5))

    run_state, report = controller.run(root, "stall")

    assert run_state.state.value == "FAILED"
    assert report.final_state.value == "FAILED"
    assert run_state.termination_reason == "exploration stalled without operational progress"
    assert run_state.agent_step_count == 8
    assert len(provider.requests) == 8
    for index in range(4, 7):
        assert "escalation_state: action_required" in provider.requests[index].messages[0].content
        assert "STALL WARNING" not in provider.requests[index].messages[0].content
    assert "consecutive_inspection_steps: 4" in provider.requests[4].messages[0].content
    assert "consecutive_inspection_steps: 7" in provider.requests[7].messages[0].content
    assert all("STALL WARNING" not in request.messages[0].content for request in provider.requests)


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
