from __future__ import annotations

from pd_agent.brain import KnowledgeEnvironment, KnowledgeType, SemanticRepairKnowledgeNeedDeriver
from pd_agent.core import ValidationResult, ValidationStage, ValidationStatus, ValidationViolation
from pd_agent.context import ContextManager
from pd_agent.runtime import AgentRuntime
from pd_agent.brain import (
    CompatibilityStatus,
    KnowledgeItem,
    KnowledgeProvenance,
    KnowledgeRetrievalStatus,
    KnowledgeSourceResult,
    SourceAuthority,
)


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
