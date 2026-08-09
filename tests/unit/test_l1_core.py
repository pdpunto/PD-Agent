from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import UUID

import pytest

from pd_agent.core import (
    AgentMessage,
    AgentRequest,
    AgentResponse,
    ArtifactResult,
    ArtifactValidationError,
    BuildError,
    BuildResult,
    ConfigurationError,
    ContextSource,
    ExecutionLimits,
    LimitReachedError,
    ModelProvider,
    PDAgentError,
    ProjectInspectionError,
    ProviderError,
    RunState,
    RunStateError,
    RunStatus,
    SecurityViolation,
    StateTransitionError,
    Tool,
    ToolCall,
    ToolExecutionError,
    ToolResult,
    ToolResultStatus,
    ToolValidationError,
    generate_run_id,
)


class FakeProvider:
    def execute(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            assistant_message=f"seen {len(request.messages)} message(s)",
            tool_calls=(ToolCall(call_id="c1", tool_name="noop", arguments={}),),
            usage={"input_tokens": 1, "output_tokens": 2},
            provider_metadata={"provider": "fake"},
        )


class FakeTool:
    name = "fake_tool"
    description = "Fake tool"
    input_schema = {"type": "object"}

    def execute(self, context, arguments):
        return ToolResult(
            call_id=str(arguments["call_id"]),
            tool_name=self.name,
            status=ToolResultStatus.SUCCESS,
            output={"context": context, "arguments": dict(arguments)},
        )


class FakeContextSource:
    def get(self, request):
        return ("ctx-a", "ctx-b")


def test_run_id_unique_and_valid() -> None:
    first = generate_run_id()
    second = generate_run_id()

    assert first != second
    assert UUID(first)
    assert UUID(second)


def test_execution_limits_defaults_are_safe() -> None:
    limits = ExecutionLimits()

    assert limits.max_agent_steps == 40
    assert limits.max_tool_calls == 120
    assert limits.max_build_attempts == 5
    assert limits.provider_retry_limit == 2
    assert limits.process_timeout_seconds == 600
    assert limits.max_tool_output_bytes == 1_000_000
    assert limits.max_context_bytes == 2_000_000


@pytest.mark.parametrize(
    "status",
    [
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.BLOCKED,
        RunStatus.LIMIT_REACHED,
        RunStatus.ABORTED,
    ],
)
def test_terminal_states_are_terminal(status: RunStatus) -> None:
    assert status.is_terminal()


def test_valid_state_transitions() -> None:
    run_state = RunState(task="demo")

    for target in (
        RunStatus.INSPECTING,
        RunStatus.PLANNING,
        RunStatus.EDITING,
        RunStatus.BUILDING,
        RunStatus.DIAGNOSING,
        RunStatus.CORRECTING,
        RunStatus.BUILDING,
        RunStatus.VALIDATING_ARTIFACT,
        RunStatus.REPORTING,
        RunStatus.COMPLETED,
    ):
        assert run_state.can_transition_to(target)
        run_state.transition_to(target)

    assert run_state.state == RunStatus.COMPLETED
    assert run_state.state.is_terminal()


def test_non_success_terminal_transition_allowed() -> None:
    run_state = RunState()

    run_state.transition_to(RunStatus.FAILED)

    assert run_state.state == RunStatus.FAILED
    assert run_state.state.is_terminal()


@pytest.mark.parametrize(
    "invalid_target",
    [RunStatus.BUILDING, RunStatus.COMPLETED, RunStatus.EDITING],
)
def test_invalid_state_transitions_raise(invalid_target: RunStatus) -> None:
    run_state = RunState()

    with pytest.raises(StateTransitionError):
        run_state.transition_to(invalid_target)


def test_counters_and_limits() -> None:
    run_state = RunState()
    limits = ExecutionLimits(max_agent_steps=1, max_tool_calls=2, max_build_attempts=3)

    assert run_state.within_limits(limits)

    run_state.record_agent_step()
    run_state.record_tool_call()
    run_state.record_tool_call()
    run_state.record_build_attempt()

    assert run_state.limit_violations(limits) == ("max_agent_steps", "max_tool_calls")
    assert not run_state.within_limits(limits)

    with pytest.raises(LimitReachedError):
        run_state.raise_if_limits_reached(limits)


def test_serialization_round_trip() -> None:
    build_result = BuildResult(
        attempt=1,
        command_display="gradlew.bat build",
        cwd=Path("C:/dev/project"),
        started_at=RunState().started_at,
        duration_seconds=1.5,
        exit_code=0,
        stdout_log="ok",
        stderr_log="",
    )
    artifact_result = ArtifactResult(
        path=Path("C:/dev/project/build/libs/example.jar"),
        size=1234,
        timestamp=RunState().started_at,
        classification="fabric-mod",
        metadata={"jar": True},
    )
    run_state = RunState(
        project_root=Path("C:/dev/project"),
        task="update docs",
        project_snapshot={"name": "example", "version": 1},
        current_plan="inspect, edit, build",
        changed_files=("src/Main.java", "README.md"),
        tool_call_count=3,
        agent_step_count=2,
        build_attempt_count=1,
        build_results=(build_result,),
        artifact_result=artifact_result,
        last_error="none",
        termination_reason="completed",
    )
    request = AgentRequest(
        messages=(AgentMessage(role="user", content="hello"),),
        tool_calls=(
            ToolCall(call_id="call-1", tool_name="fake_tool", arguments={"path": "a.txt"}),
        ),
        tool_results=(
            ToolResult(
                call_id="tool-1",
                tool_name="fake_tool",
                status=ToolResultStatus.SUCCESS,
                output={"ok": True},
            ),
        ),
        tools=(
            {
                "name": "fake_tool",
                "description": "Fake tool",
                "input_schema": {"type": "object"},
            },
        ),
        model_config={"model": "fake"},
    )
    response = AgentResponse(
        assistant_message="done",
        tool_calls=(ToolCall(call_id="1", tool_name="fake_tool", arguments={"x": 1}),),
        usage={"input_tokens": 2},
        provider_metadata={"provider": "fake"},
    )

    payload = {
        "limits": ExecutionLimits().to_dict(),
        "run_state": run_state.to_dict(),
        "request": request.to_dict(),
        "response": response.to_dict(),
        "build_result": build_result.to_dict(),
        "artifact_result": artifact_result.to_dict(),
    }
    encoded = json.loads(json.dumps(payload))

    assert ExecutionLimits.from_dict(encoded["limits"]) == ExecutionLimits()
    assert RunState.from_dict(encoded["run_state"]).to_dict() == run_state.to_dict()
    assert AgentRequest.from_dict(encoded["request"]).to_dict() == request.to_dict()
    assert AgentResponse.from_dict(encoded["response"]).to_dict() == response.to_dict()
    assert BuildResult.from_dict(encoded["build_result"]).to_dict() == build_result.to_dict()
    assert (
        ArtifactResult.from_dict(encoded["artifact_result"]).to_dict()
        == artifact_result.to_dict()
    )


def test_fake_provider_and_tool_are_compatible() -> None:
    provider = FakeProvider()
    tool = FakeTool()
    context_source = FakeContextSource()
    request = AgentRequest(
        messages=(AgentMessage(role="user", content="hi"),),
        tool_calls=(
            ToolCall(call_id="abc", tool_name=tool.name, arguments={"path": "file.txt"}),
        ),
        tool_results=(
            ToolResult(
                call_id="abc",
                tool_name=tool.name,
                status=ToolResultStatus.SUCCESS,
                output={"ok": True},
            ),
        ),
        tools=(
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            },
        ),
        model_config={"model": "fake"},
    )

    response = provider.execute(request)
    result = tool.execute(context_source.get(request), {"call_id": "abc"})

    assert isinstance(response, AgentResponse)
    assert response.tool_calls[0].tool_name == "noop"
    assert isinstance(result, ToolResult)
    assert result.tool_name == tool.name
    assert context_source.get(request) == ("ctx-a", "ctx-b")


@pytest.mark.parametrize(
    "error_type",
    [
        PDAgentError,
        ConfigurationError,
        ProjectInspectionError,
        SecurityViolation,
        ToolValidationError,
        ToolExecutionError,
        ProviderError,
        BuildError,
        ArtifactValidationError,
        LimitReachedError,
        RunStateError,
        StateTransitionError,
    ],
)
def test_normalized_errors_work_without_providers(error_type) -> None:
    error = error_type("boom")

    assert isinstance(error, Exception)
    assert "boom" in str(error)


def test_core_does_not_import_external_provider_modules() -> None:
    import inspect
    import pd_agent.core.contracts
    import pd_agent.core.errors
    import pd_agent.core.state

    source = "\n".join(
        inspect.getsource(module)
        for module in (pd_agent.core.contracts, pd_agent.core.errors, pd_agent.core.state)
    )
    assert "openai" not in source.lower()
    assert "fabric" not in source.lower()
