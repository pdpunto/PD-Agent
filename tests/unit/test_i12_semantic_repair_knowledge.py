from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pd_agent.brain import KnowledgeEnvironment, KnowledgeType, SemanticRepairKnowledgeNeedDeriver
from pd_agent.core import AgentMessage, AgentResponse, ArtifactResult, BuildResult, ExecutionLimits, RunState, RunStatus, ToolCall, ValidationResult, ValidationStage, ValidationStatus, ValidationViolation
from pd_agent.context import ContextManager, KnowledgeContextSource
from pd_agent.runtime import AgentRuntime
from pd_agent.brain import (
    CompatibilityStatus,
    KnowledgeItem,
    KnowledgeProvenance,
    KnowledgeNeed,
    KnowledgeRetrievalResult,
    KnowledgeRetrievalStatus,
    KnowledgeService,
    KnowledgeSourceResult,
    SourceAuthority,
)
from pd_agent.tools import ToolExecutor, create_filesystem_tools
from pd_agent.validation import PreBuildWorkspaceValidator
from tests.unit.test_l9_runtime import ScriptedProvider, _runtime_project


ENV = KnowledgeEnvironment(minecraft_version="1.21.11", loader_version="0.19.3")


def _violation(code: str, message: str) -> ValidationViolation:
    return ValidationViolation(
        code=code, requirement="repair requirement", observed={"message": message},
        message=message, expected={"value": "expected"}, actual={"value": "actual"},
    )


def test_cannot_find_symbol_maps_to_bounded_versioned_needs() -> None:
    result = SemanticRepairKnowledgeNeedDeriver().derive(
        _violation("COMPILER_ERROR", "cannot find symbol Registries.BLOCK"), ENV
    )
    assert len(result.needs) <= 4
    assert {need.type for need in result.needs} == {
        KnowledgeType.SYMBOL, KnowledgeType.API, KnowledgeType.VERSION_CHANGE,
    }
    assert result.needs[0].query == "Registries.BLOCK"
    assert all(need.version_sensitive and need.environment == ENV for need in result.needs)


def test_signature_fabric_and_persistence_failures_use_relevant_types() -> None:
    deriver = SemanticRepairKnowledgeNeedDeriver()
    signature = deriver.derive(_violation("METHOD_SIGNATURE_MISMATCH", "wrong overload"), ENV)
    fabric = deriver.derive(_violation("FABRIC_API_MISMATCH", "Fabric API method changed"), ENV)
    persistence = deriver.derive(_violation("PERSISTED_STATE_MISMATCH", "runtime persistence mismatch"), ENV)
    assert {need.type for need in signature.needs} == {KnowledgeType.API, KnowledgeType.SYMBOL, KnowledgeType.PATTERN}
    assert KnowledgeType.PATTERN in {need.type for need in fabric.needs}
    assert KnowledgeType.DIAGNOSTIC in {need.type for need in persistence.needs}


def test_runtime_startup_failure_preserves_runtime_diagnostic_signal() -> None:
    result = SemanticRepairKnowledgeNeedDeriver().derive(
        _violation("RUNTIME_TARGET_STARTUP_FAILURE", "NullPointerException: Block id not set"), ENV
    )
    assert len(result.needs) == 4
    assert {need.type for need in result.needs} == {
        KnowledgeType.DIAGNOSTIC, KnowledgeType.PATTERN, KnowledgeType.SYMBOL, KnowledgeType.API,
    }
    assert all("persistence" not in need.query.casefold() for need in result.needs)


def test_structured_failure_derives_failure_specific_query_and_identity() -> None:
    violation = ValidationViolation(
        code="FABRIC_BLOCK_IDENTITY_MISSING",
        requirement="src/main/java/example/ExampleMod.java",
        observed={"path": "src/main/java/example/ExampleMod.java", "line": 2},
        expected="AbstractBlock.Settings.registryKey(...) before Block construction",
        actual="inline Block construction without registryKey",
        message="Block construction lacks registry identity before registration",
        phase="PRE_BUILD",
        evidence_refs=("src/main/java/example/ExampleMod.java",),
    )

    result = SemanticRepairKnowledgeNeedDeriver().derive(violation, ENV)

    assert any(need.query == "block" for need in result.needs)
    assert all("failure_code=FABRIC_BLOCK_IDENTITY_MISSING" in need.hints for need in result.needs)
    assert all("phase=PRE_BUILD" in need.hints for need in result.needs)
    assert all(any(hint.startswith("expected=") for hint in need.hints) for need in result.needs)
    assert all(any(hint.startswith("actual=") for hint in need.hints) for need in result.needs)
    assert all("registrykey" in hint for need in result.needs for hint in need.hints if hint.startswith("failure_terms="))


def test_prebuild_failure_retrieval_and_injection_stays_failure_specific() -> None:
    violation = ValidationViolation(
        code="FABRIC_BLOCK_IDENTITY_MISSING",
        requirement="ExampleMod.java",
        observed={"path": "ExampleMod.java", "line": 2},
        expected="registry identity before construction",
        actual="Block construction without registryKey",
        message="Block construction lacks registry identity before registration",
        phase="PRE_BUILD",
    )

    class Source:
        source_id = "r34-repair-source"
        source_kind = "fixture"
        artifact_version = "r34"

        def supports(self, need):
            return need.type is KnowledgeType.PATTERN

        def compatibility(self, _environment):
            return CompatibilityStatus.COMPATIBLE

        def resolve(self, need, offline=False):
            item = KnowledgeItem(
                "block-registration-guidance",
                {"guidance": "register the block with a stable registry identity"},
                need.environment,
                SourceAuthority.AUTHORITATIVE_SOURCE,
                KnowledgeProvenance(self.source_id, self.source_kind, "fixture:r34"),
            )
            return KnowledgeSourceResult(
                KnowledgeRetrievalStatus.SUCCESS, self.source_id, self.source_kind,
                need, items=(item,),
            )

    derivation = SemanticRepairKnowledgeNeedDeriver().derive(violation, ENV)
    pattern_need = next(need for need in derivation.needs if need.type is KnowledgeType.PATTERN)
    retrieved = KnowledgeService((Source(),)).retrieve(pattern_need, offline=True)
    context = ContextManager().build_context(external_context=(retrieved,))

    assert retrieved.items
    assert pattern_need.query == "block"
    assert context.items
    assert "block-registration-guidance" in context.items[0].metadata["knowledge_item_id"]
    assert "registry" in context.items[0].content


def test_repair_context_reaches_fake_provider_under_8192_byte_pressure(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "provider-boundary")
    from pd_agent.project import ProjectInspector
    snapshot = ProjectInspector().inspect(root)
    provider = ScriptedProvider([AgentResponse(assistant_message="captured")])

    class Source:
        source_id = "r34-provider-source"
        source_kind = "fixture"
        artifact_version = "r34"

        def supports(self, _need):
            return True

        def compatibility(self, _environment):
            return CompatibilityStatus.COMPATIBLE

        def resolve(self, need, offline=False):
            item = KnowledgeItem(
                "r34-specific-block-guidance",
                {"guidance": "register the block with stable registry identity"},
                need.environment, SourceAuthority.AUTHORITATIVE_SOURCE,
                KnowledgeProvenance(self.source_id, self.source_kind, "fixture:r34"),
            )
            return KnowledgeSourceResult(KnowledgeRetrievalStatus.SUCCESS, self.source_id, self.source_kind, need, items=(item,))

    context_manager = ContextManager(sources=(("knowledge", KnowledgeContextSource(max_context_bytes=8192)),))
    runtime = AgentRuntime(
        provider=provider, build_runner=object(), artifact_validator=object(),
        context_manager=context_manager, filesystem_tools=create_filesystem_tools(),
        repair_knowledge_source=Source(), repair_knowledge_environment=ENV,
    )
    violation = ValidationViolation(
        code="FABRIC_BLOCK_IDENTITY_MISSING", requirement="ExampleMod.java",
        observed={"line": 2}, expected="registry identity", actual="Block without registryKey",
        message="Block construction lacks registry identity", phase="PRE_BUILD",
    )
    runtime._prepare_repair_knowledge(ValidationResult(
        stage=ValidationStage.PRE_BUILD, status=ValidationStatus.REPAIRABLE_FAIL,
        summary="repair", violations=(violation,),
    ))
    generic = KnowledgeRetrievalResult(
        KnowledgeRetrievalStatus.SUCCESS,
        KnowledgeNeed("pre-code:generic", KnowledgeType.PATTERN, "generic", ENV),
        (KnowledgeItem("generic-large", {"text": "g" * 7000}, ENV, SourceAuthority.SECONDARY,
                       KnowledgeProvenance("generic", "fixture", "fixture:generic")),),
    )
    state = RunState(project_root=root, task="repair")
    state.transition_to(RunStatus.INSPECTING)
    runtime._call_provider(
        run_state=state, project_snapshot=snapshot, limits=ExecutionLimits(),
        external_context=(generic,),
        history=[AgentMessage(role="user", content="PRE_BUILD FABRIC_BLOCK_IDENTITY_MISSING: repair")],
        tool_calls=(), tool_results=(), provider_continuations=(),
    )

    request = provider.requests[0]
    rendered = "\n".join(message.content for message in request.messages)
    assert "FABRIC_BLOCK_IDENTITY_MISSING" in rendered
    assert "r34-specific-block-guidance" in rendered
    assert "registry identity" in rendered
    assert context_manager.last_knowledge_traces[0].context_item_ids == ("r34-specific-block-guidance",)
    assert any(item.reason == "CONTEXT_BUDGET" for item in context_manager.last_knowledge_traces[-1].rejected_items)


def test_r32_like_offline_prebuild_repair_makes_build_eligible(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "vertical")
    source = root / "src/main/java/com/example/ExampleMod.java"
    provider = ScriptedProvider([
        AgentResponse(assistant_message="initial", tool_calls=(ToolCall(
            call_id="initial", tool_name="write_file",
            arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "Block block = new Block(AbstractBlock.Settings.create().strength(1.0f));\n"},
        ),)),
        AgentResponse(assistant_message="repair", tool_calls=(ToolCall(
            call_id="repair", tool_name="write_file",
            arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "Block block = new Block(AbstractBlock.Settings.create().registryKey(key).strength(1.0f));\n"},
        ),)),
    ])

    class Build:
        calls = 0

        def run(self, _snapshot, state, _limits):
            self.calls += 1
            result = BuildResult(
                attempt=self.calls, command_display="fake build", cwd=root,
                started_at=datetime.now(timezone.utc), duration_seconds=0.01,
                exit_code=0, stdout_log="BUILD SUCCESSFUL", stderr_log="",
            )
            state.record_build_attempt()
            state.record_build_result(result)
            return result

    class Artifact:
        def validate(self, _snapshot, _build, *, run_id):
            return ArtifactResult(path=Path("artifact.jar"), size=1,
                                  timestamp=datetime.now(timezone.utc), classification="VALID")

    class Source:
        source_id = "r34-vertical-source"
        source_kind = "fixture"
        artifact_version = "r34"

        def supports(self, need):
            return need.type is KnowledgeType.PATTERN

        def compatibility(self, _environment):
            return CompatibilityStatus.COMPATIBLE

        def resolve(self, need, offline=False):
            return KnowledgeSourceResult(
                KnowledgeRetrievalStatus.SUCCESS, self.source_id, self.source_kind, need,
                items=(KnowledgeItem("r34-vertical-block", {"guidance": "register block identity"}, need.environment,
                                     SourceAuthority.AUTHORITATIVE_SOURCE,
                                     KnowledgeProvenance(self.source_id, self.source_kind, "fixture:r34")),),
            )

    runtime = AgentRuntime(
        provider=provider, tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        build_runner=Build(), artifact_validator=Artifact(), context_manager=ContextManager(),
        pre_build_validator=PreBuildWorkspaceValidator(),
        validation_contract={"required_resources": []},
        repair_knowledge_source=Source(), repair_knowledge_environment=ENV,
    )
    from pd_agent.project import ProjectInspector
    snapshot = ProjectInspector().inspect(root)
    state = RunState(project_root=root, task="repair block")
    state.transition_to(RunStatus.INSPECTING)
    state, _report = runtime.run(
        run_state=state,
        project_snapshot=snapshot, task="repair block",
        limits=ExecutionLimits(max_agent_steps=4),
    )

    assert source.read_text(encoding="utf-8").find("registryKey") >= 0
    assert state.validation_results[0].violations[0].code == "FABRIC_BLOCK_IDENTITY_MISSING"
    assert state.validation_results[-1].status is ValidationStatus.PASS
    assert state.build_attempt_count == 1


def test_brain_off_keeps_repair_feedback_without_external_knowledge(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "brain-off")
    from pd_agent.project import ProjectInspector
    snapshot = ProjectInspector().inspect(root)
    provider = ScriptedProvider([AgentResponse(assistant_message="captured")])
    runtime = AgentRuntime(
        provider=provider, build_runner=object(), artifact_validator=object(),
        context_manager=ContextManager(sources=(("knowledge", KnowledgeContextSource()),)),
        filesystem_tools=create_filesystem_tools(),
    )
    state = RunState(project_root=root, task="brain off repair")
    state.transition_to(RunStatus.INSPECTING)
    runtime._call_provider(
        run_state=state, project_snapshot=snapshot, limits=ExecutionLimits(),
        external_context=(),
        history=[AgentMessage(role="user", content="PRE_BUILD FABRIC_BLOCK_IDENTITY_MISSING: repair")],
        tool_calls=(), tool_results=(), provider_continuations=(),
    )

    rendered = "\n".join(message.content for message in provider.requests[0].messages)
    assert "FABRIC_BLOCK_IDENTITY_MISSING" in rendered
    assert "retrieved external knowledge" not in rendered


def test_generic_failure_does_not_invent_fabric_terms() -> None:
    violation = _violation("GENERIC_FAILURE", "operation failed")

    result = SemanticRepairKnowledgeNeedDeriver().derive(violation, ENV)

    assert result.needs
    assert all(
        not any(term in f"{need.query} {' '.join(need.hints)}".casefold()
                for term in ("fabric", "registry", "block", "minecraft"))
        for need in result.needs
    )


def test_same_failure_is_deterministic_and_noise_is_bounded() -> None:
    violation = _violation("BUILD_DIAGNOSTIC", "cannot find symbol " + "x" * 5000)
    deriver = SemanticRepairKnowledgeNeedDeriver()
    assert deriver.derive(violation, ENV) == deriver.derive(violation, ENV)
    assert all(len(need.query) < 2000 for need in deriver.derive(violation, ENV).needs)


def test_empty_signal_is_valid_and_does_not_force_retrieval() -> None:
    violation = _violation("VALIDATION", "no useful information")
    result = SemanticRepairKnowledgeNeedDeriver().derive(violation, ENV)
    assert result.needs == ()


def test_sensitive_labels_are_redacted_from_derived_queries() -> None:
    result = SemanticRepairKnowledgeNeedDeriver().derive(
        _violation("API_KEY_ERROR", "token secret password authorization"), ENV
    )
    assert all("secret" not in need.query.casefold() for need in result.needs)


def test_runtime_prepares_repair_context_before_next_provider_turn() -> None:
    class Source:
        source_id = "repair-source"
        source_kind = "fixture"
        artifact_version = "1"

        def supports(self, need):
            return True

        def compatibility(self, environment):
            return CompatibilityStatus.COMPATIBLE

        def resolve(self, need, offline=False):
            item = KnowledgeItem(
                "repair-record", {"title": "Registries.BLOCK mapping guidance"}, environment=need.environment,
                authority=SourceAuthority.AUTHORITATIVE_SOURCE,
                provenance=KnowledgeProvenance("repair-source", "fixture", "fixture:repair"),
            )
            return KnowledgeSourceResult(
                status=KnowledgeRetrievalStatus.SUCCESS, source_id=self.source_id,
                source_kind=self.source_kind, need=need, items=(item,),
            )

    runtime = AgentRuntime(
        provider=object(), build_runner=object(), artifact_validator=object(),
        context_manager=ContextManager(), repair_knowledge_source=Source(),
        repair_knowledge_environment=ENV,
    )
    violation = _violation("COMPILER_ERROR", "cannot find symbol Registries.BLOCK")
    runtime._prepare_repair_knowledge(ValidationResult(
        stage=ValidationStage.PRE_BUILD, status=ValidationStatus.REPAIRABLE_FAIL,
        summary="build failed", violations=(violation,),
    ))
    assert 1 <= len(runtime._repair_context) <= 3
    assert all(item.items[0].id == "repair-record" for item in runtime._repair_context)
