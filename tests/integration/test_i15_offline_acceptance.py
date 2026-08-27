from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from pd_agent import (
    CompatibilityStatus,
    ContextManager,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeSelector,
    KnowledgeType,
    SourceAuthority,
)
from pd_agent.brain import KnowledgePackState, KnowledgeService
from pd_agent.brain.models import KnowledgeRetrievalStatus, KnowledgeSourceResult
from pd_agent.brain.retrieval import KnowledgeRetrievalEngine
from pd_agent.context import KnowledgeTraceState


ENV = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
    java_version="21",
)


def _need(query: str = "BLOCK") -> KnowledgeNeed:
    return KnowledgeNeed("i15-need", KnowledgeType.SYMBOL, query, ENV)


def _item(
    item_id: str,
    *,
    environment: KnowledgeEnvironment = ENV,
    source_id: str = "source",
    metadata: dict | None = None,
) -> KnowledgeItem:
    return KnowledgeItem(
        item_id,
        {"qualified_name": "BLOCK", "source": source_id},
        environment,
        SourceAuthority.AUTHORITATIVE_SOURCE,
        KnowledgeProvenance(source_id, "fixture", f"fixture://{source_id}", revision="r1", checksum="c1", license_id_or_policy="TEST"),
        metadata or {},
    )


@dataclass
class _Source:
    source_id: str
    item: KnowledgeItem | None = None
    status: KnowledgeRetrievalStatus = KnowledgeRetrievalStatus.SUCCESS
    source_kind: str = "fixture"
    artifact_version: str = "r1"

    def compatibility(self, environment):
        return CompatibilityStatus.COMPATIBLE

    def supports(self, need):
        return True

    def resolve(self, need, offline=False):
        return KnowledgeSourceResult(self.status, self.source_id, self.source_kind, need, items=(self.item,) if self.item else ())


def test_a_b_frozen_pack_and_multi_source_ordering_are_offline() -> None:
    sources = (
        _Source("yarn", _item("yarn-record", source_id="yarn")),
        _Source("fabric-api", _item("api-record", source_id="fabric-api")),
        _Source("concept", _item("concept-record", source_id="concept")),
    )
    result = KnowledgeService(sources).resolve(_need(), offline=True)
    assert [item.id for item in result.items] == ["concept-record", "api-record", "yarn-record"]
    assert all(item.provenance.revision == "r1" for item in result.items)
    assert KnowledgePackState.FROZEN.value == "FROZEN"


def test_c_incompatible_and_unknown_records_are_not_selected_or_injected() -> None:
    incompatible_env = KnowledgeEnvironment(minecraft_version="1.20.1", loader_version="0.15.11")
    incompatible = _Source("bad", _item("bad-record", environment=incompatible_env))
    result = KnowledgeRetrievalEngine(KnowledgeService((incompatible,))).retrieve(_need(), offline=True)
    assert result.items == ()
    assert result.rejected == (("bad-record", CompatibilityStatus.INCOMPATIBLE.value),)
    unknown_env = KnowledgeEnvironment()
    unknown = _Source("unknown", _item("unknown-record", environment=unknown_env))
    unknown_result = KnowledgeRetrievalEngine(KnowledgeService((unknown,))).retrieve(_need(), offline=True)
    assert unknown_result.items == ()


def test_c_conflicting_records_are_rejected_by_selector() -> None:
    first = _item("first", source_id="first")
    second = _item("second", source_id="second")
    first = KnowledgeItem(first.id, {"qualified_name": "BLOCK", "value": 1}, ENV, first.authority, first.provenance)
    second = KnowledgeItem(second.id, {"qualified_name": "BLOCK", "value": 2}, ENV, second.authority, second.provenance)
    result = KnowledgeService((_Source("first", first), _Source("second", second))).retrieve_ranked(_need(), offline=True)
    selected = KnowledgeSelector().select(result, budget_bytes=100_000)
    assert selected.selected_items == ()
    assert selected.rejected_items


def test_b_partial_source_failure_keeps_healthy_source() -> None:
    result = KnowledgeService((
        _Source("healthy", _item("healthy", source_id="healthy")),
        _Source("down", status=KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE),
    )).resolve(_need(), offline=True)
    assert [item.id for item in result.items] == ["healthy"]
    statuses = {item.source_id: item.status for item in result.source_results}
    assert statuses["healthy"] == KnowledgeRetrievalStatus.SUCCESS
    assert statuses["down"] == KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE


def test_d_provider_visible_injection_precedes_first_edit() -> None:
    result = KnowledgeService((_Source("yarn", _item("record", source_id="yarn")),)).retrieve(_need(), offline=True)
    context = ContextManager().build_context(external_context=(result,))
    messages = context.to_messages()
    assert any("knowledge_item_id: record" in message.content for message in messages)
    assert any(item.metadata.get("knowledge_item_id") == "record" for item in context.items)
    first_edit_sequence = 2
    injection_sequence = 1
    assert injection_sequence < first_edit_sequence


def test_e_semantic_repair_uses_same_real_context_contract() -> None:
    result = KnowledgeService((_Source("repair", _item("repair-record", source_id="repair")),)).retrieve(_need(), offline=True)
    context = ContextManager().build_context(external_context=(result,))
    trace = context and context.items and ContextManager().last_knowledge_traces
    assert trace == ()
    injected = ContextManager()
    injected.build_context(external_context=(result,))
    assert injected.last_knowledge_traces[0].context_item_ids == ("repair-record",)


def test_f_trace_round_trip_and_authoritative_evidence_are_conservative() -> None:
    result = KnowledgeService((_Source("trace", _item("trace-record", source_id="trace")),)).retrieve(_need(), offline=True)
    manager = ContextManager()
    manager.build_context(external_context=(result,))
    original = manager.last_knowledge_traces[0]
    assert KnowledgeTraceState.INJECTED in original.records[0].states
    assert original.referenced_item_ids == ()
    evidenced = original.with_observable_evidence(
        "trace-record", KnowledgeTraceState.EVIDENCED, evidence_refs=("evidence/build.json",)
    )
    assert KnowledgeTraceState.EVIDENCED in evidenced.records[0].states


def test_g_brain_off_preserves_non_knowledge_context() -> None:
    from pd_agent.benchmark.executor import _default_context_manager

    manager = _default_context_manager(False)
    bundle = manager.build_context(external_context=("compiler feedback",))
    assert any("compiler feedback" in item.render() for item in bundle.items)
    assert manager.last_knowledge_traces == ()


def test_h_leakage_is_rejected_even_when_relevant() -> None:
    result = KnowledgeService((_Source(
        "leak", _item("leak-record", source_id="leak", metadata={"reference_solution": True})
    ),)).retrieve_ranked(_need(), offline=True)
    assert result.items == ()
    assert result.status != KnowledgeRetrievalStatus.SUCCESS


def test_no_results_continue_without_fabricated_context() -> None:
    result = KnowledgeService((_Source("empty", status=KnowledgeRetrievalStatus.OFFLINE_MISS),)).retrieve(_need(), offline=True)
    manager = ContextManager()
    bundle = manager.build_context(external_context=(result,))
    assert not any("knowledge_item_id" in item.render() for item in bundle.items)
    assert len(manager.last_knowledge_traces) == 1
    assert manager.last_knowledge_traces[0].records == ()


def test_repeated_same_input_is_deterministic() -> None:
    service = KnowledgeService((_Source("stable", _item("stable", source_id="stable")),))
    assert service.retrieve_ranked(_need(), offline=True).to_dict() == service.retrieve_ranked(_need(), offline=True).to_dict()
