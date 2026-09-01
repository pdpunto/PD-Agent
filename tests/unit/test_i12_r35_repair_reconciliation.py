from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pd_agent.context import ContextManager
from pd_agent.brain import (
    CompatibilityStatus,
    KnowledgeItem,
    KnowledgeProvenance,
    KnowledgeSourceResult,
    KnowledgeType,
    KnowledgeRetrievalStatus,
    SourceAuthority,
)
from pd_agent.core import (
    AgentResponse,
    ArtifactResult,
    BuildResult,
    ExecutionLimits,
    RunState,
    RunStatus,
    ToolResult,
    ToolResultStatus,
    ToolCall,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    ValidationViolation,
)
from pd_agent.reporting import RunEventType, RunStorage
from pd_agent.runtime import AgentRuntime
from pd_agent.tools import ToolExecutor, create_filesystem_tools
from pd_agent.validation import PreBuildWorkspaceValidator
from tests.unit.test_i12_semantic_repair_knowledge import ENV
from tests.unit.test_l9_runtime import ScriptedProvider, _runtime_project


def _failure(*, code: str = "SAME_ROOT_CAUSE", category: str = "invalid") -> ValidationResult:
    return ValidationResult(
        stage=ValidationStage.PRE_BUILD,
        status=ValidationStatus.REPAIRABLE_FAIL,
        summary="invalid source",
        violations=(ValidationViolation(
            code=code,
            requirement="source",
            observed={"category": category},
            expected="valid source",
            actual="invalid source",
            message="the root cause remains",
            phase="PRE_BUILD",
            evidence_refs=("src/Main.java",),
        ),),
    )


def _pass() -> ValidationResult:
    return ValidationResult(
        stage=ValidationStage.PRE_BUILD,
        status=ValidationStatus.PASS,
        summary="valid source",
    )


def _runtime(tmp_path: Path, validator: object, events: list[object]) -> AgentRuntime:
    return AgentRuntime(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
        context_manager=ContextManager(),
        pre_build_validator=validator,
        reporting=SimpleNamespace(append_event=events.append),
    )


def _state(tmp_path: Path) -> RunState:
    state = RunState(project_root=tmp_path, task="r35")
    state.transition_to(RunStatus.INSPECTING)
    state.transition_to(RunStatus.PLANNING)
    state.transition_to(RunStatus.EDITING)
    state.record_changed_file("src/Main.java")
    return state


def test_r35_same_failure_is_reported_after_ineffective_repair(tmp_path: Path) -> None:
    class Validator:
        def validate(self, *_args):
            return _failure()

    events: list[object] = []
    runtime = _runtime(tmp_path, Validator(), events)
    state = _state(tmp_path)
    history: list[object] = []
    snapshot = SimpleNamespace(project_root=tmp_path)

    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"

    feedback = history[-1].content
    repair_events = [event for event in events if event.event_type is RunEventType.SEMANTIC_REPAIR_FEEDBACK]
    assert "REPEATED_FAILURE_AFTER_INEFFECTIVE_REPAIR" in feedback
    assert "previous_failure_signature:" in feedback
    assert "src/Main.java" in feedback
    assert len(repair_events) == 2
    assert repair_events[0].payload["classification"] == "FIRST_FAILURE"
    assert repair_events[0].payload["previous_repair_attempt_ref"] is None
    assert repair_events[0].payload["previous_failure_signature"] is None
    assert repair_events[0].payload["previous_mutation_refs"] == []
    assert repair_events[-1].payload["classification"] == "REPEATED_FAILURE_AFTER_INEFFECTIVE_REPAIR"
    assert repair_events[-1].payload["ineffective_repair"] is True
    assert repair_events[-1].payload["previous_repair_attempt_ref"] is not None
    assert state.ineffective_repair is True
    assert state.ineffective_repair_ref == state.last_repair_attempt_ref


def test_r35_successful_repair_clears_ineffective_marker(tmp_path: Path) -> None:
    class Validator:
        results = iter((_failure(), _failure(), _pass()))

        def validate(self, *_args):
            return next(self.results)

    events: list[object] = []
    runtime = _runtime(tmp_path, Validator(), events)
    state = _state(tmp_path)
    history: list[object] = []
    snapshot = SimpleNamespace(project_root=tmp_path)

    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "PASS"
    assert state.ineffective_repair is False
    assert state.ineffective_repair_ref is None


def test_r35_different_failure_is_not_marked_ineffective(tmp_path: Path) -> None:
    class Validator:
        results = iter((_failure(code="FIRST", category="first"), _failure(code="SECOND", category="second")))

        def validate(self, *_args):
            return next(self.results)

    events: list[object] = []
    runtime = _runtime(tmp_path, Validator(), events)
    state = _state(tmp_path)
    history: list[object] = []
    snapshot = SimpleNamespace(project_root=tmp_path)

    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    assert "REPEATED_FAILURE_AFTER_INEFFECTIVE_REPAIR" not in history[-1].content
    assert state.ineffective_repair is False
    assert events[-1].payload["classification"] == "FIRST_FAILURE"


def test_r35_third_same_failure_fails_closed(tmp_path: Path) -> None:
    class Validator:
        def validate(self, *_args):
            return _failure()

    runtime = _runtime(tmp_path, Validator(), [])
    state = _state(tmp_path)
    history: list[object] = []
    snapshot = SimpleNamespace(project_root=tmp_path)

    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "REPAIR"
    state.transition_to(RunStatus.EDITING)
    assert runtime._run_prebuild_validation(state, snapshot, history) == "FAILED"
    assert state.termination_reason == "repeated semantic validation failure"


def test_r35_repair_evidence_round_trips_through_run_state(tmp_path: Path) -> None:
    state = _state(tmp_path)
    signature = "failure-signature"
    attempt_ref = state.record_repair_attempt(signature)
    state.record_ineffective_repair()

    restored = RunState.from_dict(state.to_dict())

    assert restored.repair_attempt_count == 1
    assert restored.last_repair_attempt_ref == attempt_ref
    assert restored.last_repair_failure_signature == signature
    assert restored.last_repair_mutation_refs == ("src/Main.java",)
    assert restored.ineffective_repair is True
    assert restored.ineffective_repair_ref == attempt_ref


def test_r35_integrated_r34_failure_specific_repair_reconciles_to_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "integrated", build_state="pass")
    source = root / "src/main/java/com/example/ExampleMod.java"
    provider = ScriptedProvider([
        AgentResponse(
            assistant_message="initial mutation",
            tool_calls=(ToolCall(
                call_id="initial",
                tool_name="write_file",
                arguments={
                    "path": "src/main/java/com/example/ExampleMod.java",
                    "content": "Block block = new Block(AbstractBlock.Settings.create().strength(1.0f));\n",
                },
            ),),
        ),
        AgentResponse(
            assistant_message="ineffective repair",
            tool_calls=(ToolCall(
                call_id="ineffective",
                tool_name="write_file",
                arguments={
                    "path": "src/main/java/com/example/ExampleMod.java",
                    "content": "Block block = new Block(AbstractBlock.Settings.create().strength(2.0f));\n",
                },
            ),),
        ),
        AgentResponse(
            assistant_message="valid repair",
            tool_calls=(ToolCall(
                call_id="valid",
                tool_name="write_file",
                arguments={
                    "path": "src/main/java/com/example/ExampleMod.java",
                    "content": "Block block = new Block(AbstractBlock.Settings.create().registryKey(key).strength(1.0f));\n",
                },
            ),),
        ),
    ])

    class Source:
        source_id = "r34-r35-integrated-source"
        source_kind = "fixture"
        artifact_version = "r34"
        needs = []

        def supports(self, need):
            return need.type is KnowledgeType.PATTERN

        def compatibility(self, _environment):
            return CompatibilityStatus.COMPATIBLE

        def resolve(self, need, offline=False):
            self.needs.append(need)
            return KnowledgeSourceResult(
                KnowledgeRetrievalStatus.SUCCESS,
                self.source_id,
                self.source_kind,
                need,
                items=(KnowledgeItem(
                    "r34-block-registry-guidance",
                    {"guidance": "register the block with stable registry identity"},
                    need.environment,
                    SourceAuthority.AUTHORITATIVE_SOURCE,
                    KnowledgeProvenance(self.source_id, self.source_kind, "fixture:r34"),
                ),),
            )

    class Build:
        calls = 0

        def run(self, _snapshot, state, _limits):
            self.calls += 1
            result = BuildResult(
                attempt=self.calls,
                command_display="fake build",
                cwd=root,
                started_at=datetime.now(timezone.utc),
                duration_seconds=0.01,
                exit_code=0,
                stdout_log="BUILD SUCCESSFUL",
                stderr_log="",
            )
            state.record_build_attempt()
            state.record_build_result(result)
            return result

    class Artifact:
        def validate(self, _snapshot, _build, *, run_id):
            return ArtifactResult(
                path=Path("artifact.jar"),
                size=1,
                timestamp=datetime.now(timezone.utc),
                classification="VALID",
            )

    from pd_agent.project import ProjectInspector
    storage = RunStorage(root / "runs")
    context = ContextManager()
    knowledge_source = Source()
    runtime = AgentRuntime(
        provider=provider,
        tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        build_runner=Build(),
        artifact_validator=Artifact(),
        context_manager=context,
        reporting=storage,
        pre_build_validator=PreBuildWorkspaceValidator(),
        validation_contract={"required_resources": []},
        repair_knowledge_source=knowledge_source,
        repair_knowledge_environment=ENV,
    )
    snapshot = ProjectInspector().inspect(root)
    state = RunState(project_root=root, task="integrated repair")
    state.transition_to(RunStatus.INSPECTING)
    runtime.run(
        run_state=state,
        project_snapshot=snapshot,
        task="integrated repair",
        limits=ExecutionLimits(max_agent_steps=6),
    )

    def rendered(index: int) -> str:
        return "\n".join(message.content for message in provider.requests[index].messages)

    repair_events = [
        event for event in storage.read_events(state.run_id)
        if event.event_type is RunEventType.SEMANTIC_REPAIR_FEEDBACK
    ]
    assert state.validation_results[0].violations[0].code == "FABRIC_BLOCK_IDENTITY_MISSING"
    assert len(knowledge_source.needs) == 1
    assert knowledge_source.needs[0].id.startswith("semantic-repair:")
    assert "FABRIC_BLOCK_IDENTITY_MISSING" in knowledge_source.needs[0].hints[0]
    assert source.read_text(encoding="utf-8").find("registryKey") >= 0
    assert len(provider.requests) == 3
    assert "FABRIC_BLOCK_IDENTITY_MISSING" in rendered(1)
    assert "r34-block-registry-guidance" in rendered(1)
    assert "FABRIC_BLOCK_IDENTITY_MISSING" in rendered(2)
    assert "r34-block-registry-guidance" in rendered(2)
    assert "REPEATED_FAILURE_AFTER_INEFFECTIVE_REPAIR" in rendered(2)
    assert len(repair_events) == 2
    assert repair_events[0].payload["classification"] == "FIRST_FAILURE"
    assert repair_events[1].payload["classification"] == "REPEATED_FAILURE_AFTER_INEFFECTIVE_REPAIR"
    assert any(
        item.stage is ValidationStage.PRE_BUILD
        and item.status is ValidationStatus.REPAIRABLE_FAIL
        and item.violations[0].code == "FABRIC_BLOCK_IDENTITY_MISSING"
        for item in state.validation_results
    )
    assert state.validation_results[-1].status is ValidationStatus.PASS
    assert state.ineffective_repair is False
    assert runtime.build_runner.calls == 1
    traces = context.last_knowledge_traces
    assert traces
    assert traces[-1].retrieved_item_ids == ("r34-block-registry-guidance",)
    assert traces[-1].selected_item_ids == ("r34-block-registry-guidance",)
    assert traces[-1].context_item_ids == ("r34-block-registry-guidance",)


def test_r35_ordinary_mutation_still_resets_validation_stall(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, object(), [])
    state = _state(tmp_path)
    state.last_validation_signature = "old-failure"
    state.validation_repeat_count = 1
    changed = ToolResult(
        call_id="ordinary",
        tool_name="write_file",
        status=ToolResultStatus.SUCCESS,
        output={"path": "src/Main.java"},
        metadata={"changed": True, "path": "src/Main.java"},
    )

    runtime._observe_progress(state, tool_results=(changed,))

    assert state.last_validation_signature is None
    assert state.validation_repeat_count == 0
