from __future__ import annotations

from pathlib import Path

from pd_agent.build import BuildFailureNormalizer
from pd_agent.core import (
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    RunState,
    RunStatus,
    TaskProgressLedger,
)
from tests.unit.test_l9_runtime import ScriptedProvider, _runtime_project, _runtime
from pd_agent.core import AgentResponse, ExecutionLimits, ToolCall


class CountingNormalizer(BuildFailureNormalizer):
    def __init__(self) -> None:
        self.calls = 0
        self.requirement_ids = ()

    def normalize(self, result, **kwargs):  # noqa: ANN001
        self.calls += 1
        self.requirement_ids = kwargs.get("requirement_ids", ())
        return super().normalize(result, **kwargs)


def _build_contract() -> FabricTaskContract:
    return FabricTaskContract(
        task_id="lot4",
        revision="1",
        goal="build",
        requirements=(
            FabricRequirement(requirement_id="requirement:source", description="source"),
            FabricRequirement(requirement_id="requirement:artifact", description="artifact"),
        ),
        validation_requirements=(FabricValidationRequirement(
            validation_requirement_id="validation:build",
            requirement_ids=("requirement:source", "requirement:artifact"),
            kind="build",
        ),),
    )


def test_agent_runtime_normalizes_failed_build_once_and_exposes_structured_feedback(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "failure", build_state="fail")
    provider = ScriptedProvider([
        AgentResponse(
            assistant_message="plan",
            tool_calls=(ToolCall(call_id="1", tool_name="write_file", arguments={
                "path": "src/main/java/com/example/ExampleMod.java",
                "content": "package com.example; class ExampleMod { int x = 1; }\n",
            }),),
        ),
        AgentResponse(assistant_message="diagnose", tool_calls=()),
    ])
    normalizer = CountingNormalizer()
    runtime, _storage, snapshot = _runtime(root, provider)
    runtime.build_failure_normalizer = normalizer
    state = RunState(
        project_root=root,
        state=RunStatus.INSPECTING,
        task_contract=_build_contract(),
        progress_ledger=TaskProgressLedger(contract_identity=_build_contract().identity()),
    )

    result, _report = runtime.run(
        run_state=state,
        project_snapshot=snapshot,
        task="build",
        limits=ExecutionLimits(max_agent_steps=4, max_tool_calls=4, max_build_attempts=2),
    )

    assert result.build_attempt_count == 1
    assert normalizer.calls == 1
    assert normalizer.requirement_ids == ("requirement:source", "requirement:artifact")
    assert result.progress_ledger is not None
    assert len(result.progress_ledger.failures) == 1
    failure = result.progress_ledger.failures[0]
    assert failure.requirement_ids == ("requirement:source", "requirement:artifact")
    assert all(not item.startswith("validation:") for item in failure.requirement_ids)
    assert provider.requests[1].messages
    assert any("normalized_build_failure" in message.content for message in provider.requests[1].messages)
    assert result.build_results[0].stderr_log == "BUILD FAILED: fail\n"


def test_agent_runtime_success_does_not_normalize(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "success", build_state="pass")
    provider = ScriptedProvider([AgentResponse(assistant_message="plan", tool_calls=(ToolCall(
        call_id="1", tool_name="write_file", arguments={
            "path": "src/main/java/com/example/ExampleMod.java",
            "content": "package com.example; class ExampleMod { int x = 1; }\n",
        },
    ),))])
    normalizer = CountingNormalizer()
    runtime, _storage, snapshot = _runtime(root, provider)
    runtime.build_failure_normalizer = normalizer

    result, _report = runtime.run(
        run_state=RunState(project_root=root, state=RunStatus.INSPECTING),
        project_snapshot=snapshot,
        task="build",
        limits=ExecutionLimits(max_agent_steps=100, max_tool_calls=120, max_build_attempts=2),
    )

    assert result.state.value == "COMPLETED", result.termination_reason
    assert normalizer.calls == 0
    assert result.progress_ledger is None or not result.progress_ledger.failures
