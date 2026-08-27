from __future__ import annotations

from types import SimpleNamespace

from pd_agent import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeType,
    SourceAuthority,
)
from pd_agent.brain import KnowledgeDegradedMode, KnowledgeService
from pd_agent.brain.retrieval import KnowledgeRetrievalEngine
from pd_agent.brain.models import KnowledgeRetrievalStatus, KnowledgeSourceResult


ENV = KnowledgeEnvironment(minecraft_version="1.21.11", loader_version="0.19.3")


def _need() -> KnowledgeNeed:
    return KnowledgeNeed("need-1", KnowledgeType.SYMBOL, "BLOCK", ENV)


def _item(item_id: str, metadata: dict | None = None) -> KnowledgeItem:
    return KnowledgeItem(
        item_id, {"qualified_name": "BLOCK"}, ENV, SourceAuthority.AUTHORITATIVE_SOURCE,
        KnowledgeProvenance("source", "fixture", "fixture://source", revision="r1"),
        metadata or {},
    )


class Source:
    source_kind = "fixture"
    artifact_version = "r1"

    def __init__(self, status: KnowledgeRetrievalStatus, items: tuple[KnowledgeItem, ...] = (), source_id: str = "source") -> None:
        self.source_id = source_id
        self.status = status
        self.items = items

    def compatibility(self, environment):
        return CompatibilityStatus.COMPATIBLE

    def supports(self, need):
        return True

    def resolve(self, need, offline=False):
        return KnowledgeSourceResult(self.status, self.source_id, self.source_kind, need, items=self.items)


def test_brain_off_has_no_knowledge_source() -> None:
    from pd_agent.benchmark.executor import _default_context_manager

    names = {binding.name for binding in _default_context_manager(False)._sources}
    assert names == {"project", "run", "external"}


def test_partial_source_failure_keeps_healthy_source_results() -> None:
    healthy = Source(KnowledgeRetrievalStatus.SUCCESS, (_item("healthy"),), "healthy")
    unavailable = Source(KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE, source_id="unavailable")
    result = KnowledgeService((unavailable, healthy)).resolve(_need(), offline=True)
    assert result.items == (_item("healthy"),)
    assert any(attempt.status == KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE for attempt in result.source_results)


def test_explicit_leakage_metadata_is_not_served() -> None:
    source = Source(KnowledgeRetrievalStatus.SUCCESS, (_item("answer", {"answer_key": True}),))
    result = KnowledgeService((source,)).resolve(_need(), offline=True)
    assert result.items == ()


def test_degraded_modes_are_stable_and_distinct() -> None:
    assert KnowledgeDegradedMode.CONTINUE_WITHOUT_KNOWLEDGE != KnowledgeDegradedMode.BLOCKED
    assert KnowledgeDegradedMode.DEGRADED.value == "DEGRADED"
    assert KnowledgeDegradedMode.INVALID.value == "INVALID"


def test_invalid_canonical_pack_is_not_injected() -> None:
    source = Source(KnowledgeRetrievalStatus.OFFLINE_MISS)
    invalid_pack = SimpleNamespace(
        manifest=SimpleNamespace(state="FROZEN"),
        verify=lambda: SimpleNamespace(valid=False),
        can_serve=False,
        records=(_item("corrupt"),),
    )
    result = KnowledgeRetrievalEngine(KnowledgeService((source,))).retrieve(
        _need(), packs=(invalid_pack,), offline=True
    )
    assert result.status == KnowledgeRetrievalStatus.PROVENANCE_INVALID
    assert result.items == ()
    assert result.degraded is True
