from __future__ import annotations

from pd_agent.brain import (
    BrainTrigger,
    FabricBrainOrchestrator,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeProvenance,
    KnowledgeService,
    SourceAuthority,
)
from pd_agent.core import FabricRequirement, FabricTaskContract, FabricValidationRequirement, TaskProgressLedger, ValidationViolation


ENV = KnowledgeEnvironment(minecraft_version="1.21.11", loader_version="0.19.3")


class FakeKnowledgeSource:
    source_id = "fake"
    source_kind = "test"
    artifact_version = "1"

    def supports(self, need):
        return True

    def compatibility(self, environment):
        from pd_agent.brain import CompatibilityStatus
        return CompatibilityStatus.COMPATIBLE

    def resolve(self, need, offline=False):
        from pd_agent.brain import KnowledgeRetrievalStatus, KnowledgeSourceResult
        item = KnowledgeItem(
            id=f"item:{need.id}",
            content={"knowledge": need.query},
            environment=need.environment,
            authority=SourceAuthority.OFFICIAL_DOCUMENTATION,
            provenance=KnowledgeProvenance(source_id="fake", source_kind="test", locator="fixture", revision="1"),
        )
        return KnowledgeSourceResult(status=KnowledgeRetrievalStatus.SUCCESS, source_id="fake", source_kind="test", need=need, items=(item,), provenance=(item.provenance,))


def _contract() -> FabricTaskContract:
    return FabricTaskContract(
        task_id="task",
        revision="1",
        goal="implement a block entity with inventory persistence",
        requirements=(FabricRequirement(requirement_id="r1", description="inventory persistence"),),
        required_capabilities=("block_entities", "inventories"),
        validation_requirements=(FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=("r1",), kind="build"),),
    )


def _orchestrator() -> FabricBrainOrchestrator:
    return FabricBrainOrchestrator(knowledge_service=KnowledgeService((FakeKnowledgeSource(),)))


def test_precode_is_bounded_and_provider_visible() -> None:
    result = _orchestrator().prepare(contract=_contract(), environment=ENV)
    assert result.brain_enabled is True
    assert len(result.needs) <= 8
    assert result.retrieved_count > 0
    assert result.selected_count > 0
    assert result.injected_context_item_ids
    assert result.provider_messages
    assert result.traces[0].context_item_ids


def test_zero_needs_is_valid_and_brain_off_does_not_derive_or_retrieve() -> None:
    empty = FabricTaskContract(task_id="empty", revision="1", goal="plain task", requirements=())
    result = _orchestrator().prepare(contract=empty, environment=ENV)
    assert result.needs == ()
    assert result.retrieval_results == ()
    off = _orchestrator().prepare(contract=_contract(), environment=ENV, brain_enabled=False)
    assert off.needs == () and off.retrieval_results == () and off.context_bundle is None


def test_same_trigger_and_environment_deduplicate_but_new_failure_does_not() -> None:
    orchestrator = _orchestrator()
    first = orchestrator.prepare(contract=_contract(), environment=ENV, trigger=BrainTrigger.PRE_CODE)
    duplicate = orchestrator.prepare(contract=_contract(), environment=ENV, trigger=BrainTrigger.PRE_CODE)
    failure = ValidationViolation(code="BUILD_MISSING_SYMBOL", requirement="build", observed={}, message="missing symbol Foo", expected="Foo", actual=None)
    repair = orchestrator.prepare(contract=_contract(), environment=ENV, trigger=BrainTrigger.BUILD_FAILURE, failure=failure)
    assert first.retrieval_results
    assert duplicate.deduplicated is True
    assert repair.needs and repair.retrieval_results


def test_repair_is_bounded_and_blocked_failures_do_not_repair() -> None:
    orchestrator = _orchestrator()
    repair = orchestrator.prepare(contract=_contract(), environment=ENV, trigger=BrainTrigger.BUILD_FAILURE, failure=ValidationViolation(code="BUILD_MISSING_SYMBOL", requirement="build", observed={}, message="cannot find symbol Foo", expected="Foo", actual=None))
    assert len(repair.needs) <= 4
    blocked = orchestrator.prepare(contract=_contract(), environment=ENV, trigger=BrainTrigger.BUILD_FAILURE, failure=ValidationViolation(code="BUILD_TIMEOUT", requirement="build", observed={}, message="timeout", expected="success", actual="timeout"))
    assert blocked.needs == ()


def test_pending_required_requirement_correlates_without_satisfying_it() -> None:
    contract = _contract()
    ledger = TaskProgressLedger(contract_identity=contract.identity())
    result = _orchestrator().prepare(contract=contract, environment=ENV, ledger=ledger, trigger=BrainTrigger.PENDING_REQUIREMENT)
    assert result.needs
    assert result.ledger is not None
    assert result.ledger.satisfied_requirement_ids == ()
