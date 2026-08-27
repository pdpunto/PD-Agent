from __future__ import annotations

from pd_agent.brain import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeRetrievalCandidate,
    KnowledgeRetrievalStatus,
    KnowledgeService,
    KnowledgeSourceResult,
    KnowledgeType,
    RetrievalMatchClass,
    SourceAuthority,
)
from pd_agent.context import ContextManager, ExternalContextSource, KnowledgeContextSource, KnowledgeSelector
from pd_agent.context.models import ContextRequest


ENV = KnowledgeEnvironment(minecraft_version="1.21.11")
NEED = KnowledgeNeed("need", KnowledgeType.CONCEPT, "registry", ENV)


def _item(item_id: str, content: object, authority=SourceAuthority.AUTHORITATIVE_ARTIFACT) -> KnowledgeItem:
    return KnowledgeItem(
        item_id, content, ENV, authority,
        KnowledgeProvenance("source-" + item_id, "test", "fixture:" + item_id),
    )


def _ranked(*items: KnowledgeItem):
    candidates = tuple(
        KnowledgeRetrievalCandidate(item, RetrievalMatchClass.EXACT, CompatibilityStatus.COMPATIBLE,
                                    4, 1, 3, "test") for item in items
    )
    from pd_agent.brain import RankedKnowledgeRetrievalResult
    return RankedKnowledgeRetrievalResult(KnowledgeRetrievalStatus.SUCCESS, NEED, candidates=candidates)


def test_selector_preserves_i9_order_and_distinguishes_retrieved_from_selected() -> None:
    result = _ranked(_item("first", {"title": "one"}), _item("second", {"title": "two"}))
    selected = KnowledgeSelector().select(result, budget_bytes=100_000)
    assert tuple(item.id for item in selected.selected_items) == ("first", "second")
    assert selected.trace.retrieved_item_ids == ("first", "second")


def test_unresolved_conflict_is_excluded_from_provider_context() -> None:
    first = _item("first", {"capability": "registry", "value": "one"})
    second = _item("second", {"capability": "registry", "value": "two"})
    first = KnowledgeItem(first.id, first.content, first.environment, first.authority, first.provenance,
                          {"capability": "registry"})
    second = KnowledgeItem(second.id, second.content, second.environment, second.authority, second.provenance,
                           {"capability": "registry"})
    from pd_agent.brain import RankedKnowledgeRetrievalResult
    conflict = _ranked(first, second)
    conflict = RankedKnowledgeRetrievalResult(
        conflict.status, conflict.need,
        candidates=tuple(
            KnowledgeRetrievalCandidate(candidate.item, candidate.match_class, candidate.compatibility,
                                        candidate.authority_score, candidate.specificity_score,
                                        candidate.relevance_score, candidate.rank_reason, ("first", "second"))
            for candidate in conflict.candidates
        ),
        conflicts=(),
    )
    source = KnowledgeContextSource()
    context = source.get(ContextRequest(external_context=(conflict,)))
    assert context == ()
    assert source.last_traces[0].selected_item_ids == ()


def test_context_source_enforces_item_bound_and_reports_injected_ids() -> None:
    result = _ranked(*(_item(str(index), {"title": "registry"}) for index in range(4)))
    source = KnowledgeContextSource(max_items=2)
    context = source.get(ContextRequest(external_context=(result,)))
    assert len(context) == 2
    assert source.last_traces[0].selected_item_ids == ("0", "1", "2", "3")
    assert source.last_traces[0].context_item_ids == ("0", "1")


def test_brain_off_context_has_external_but_no_knowledge() -> None:
    manager = ContextManager(sources=(
        ("external", ExternalContextSource()),
    ))
    bundle = manager.build_context(external_context=("runtime evidence",))
    assert "runtime evidence" in bundle.to_text()
    assert "retrieved external knowledge" not in bundle.to_text()


def test_provider_neutral_context_contains_only_injected_records() -> None:
    result = _ranked(_item("visible", {"title": "registry"}), _item("hidden", {"title": "other"}))
    selected = KnowledgeSelector().select(result, budget_bytes=100_000)
    messages = ContextManager().to_messages(ContextRequest(external_context=(selected,)))
    rendered = messages[0].content
    assert "knowledge_item_id" in rendered
    assert "visible" in rendered and "hidden" in rendered
