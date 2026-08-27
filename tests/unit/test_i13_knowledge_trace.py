from __future__ import annotations

import json
from pathlib import Path

from pd_agent import (
    KnowledgeEnvironment,
    KnowledgeNeed,
    KnowledgeType,
    KnowledgeTrace,
    KnowledgeTraceState,
)
from pd_agent.reporting.events import RunEvent, RunEventType
from pd_agent.reporting import RunStorage


ENV = KnowledgeEnvironment(minecraft_version="1.21.11", loader_version="0.19.3")


def _trace() -> KnowledgeTrace:
    need = KnowledgeNeed(id="need-1", type=KnowledgeType.SYMBOL, query="Registries.BLOCK", environment=ENV)
    return KnowledgeTrace(
        run_id="run-1",
        environment=ENV,
        needs=(need,),
        retrieved_item_ids=("record-1", "record-2"),
        selected_item_ids=("record-1",),
        context_item_ids=("record-1",),
        source_attempts=(),
        stage="PRE_CODE",
        provider_turn=2,
    )


def test_trace_distinguishes_retrieved_selected_and_injected() -> None:
    trace = _trace()
    states = {record.item_id: set(record.states) for record in trace.records}
    assert states["record-1"] == {
        KnowledgeTraceState.RETRIEVED,
        KnowledgeTraceState.SELECTED,
        KnowledgeTraceState.INJECTED,
    }
    assert states["record-2"] == {KnowledgeTraceState.RETRIEVED}


def test_reference_requires_explicit_deterministic_observation() -> None:
    trace = _trace()
    assert trace.referenced_item_ids == ()
    referenced = trace.with_observable_evidence(
        "record-1", KnowledgeTraceState.REFERENCED,
        evidence_refs=("evidence/tool.json",), provider_turn=3, stage="SEMANTIC_REPAIR",
    )
    assert referenced.referenced_item_ids == ("record-1",)
    assert referenced.evidenced_item_ids == ()
    record = referenced.records[0]
    assert record.context_item_id == "record-1"
    assert record.provider_turn == 3
    assert record.evidence_refs == ("evidence/tool.json",)


def test_evidence_state_is_explicit_and_preserves_chain() -> None:
    trace = _trace().with_observable_evidence(
        "record-1", KnowledgeTraceState.REFERENCED, evidence_refs=("evidence/mutation.json",)
    )
    evidenced = trace.with_observable_evidence(
        "record-1", KnowledgeTraceState.EVIDENCED, evidence_refs=("evidence/build.json",)
    )
    assert evidenced.referenced_item_ids == ("record-1",)
    assert evidenced.evidenced_item_ids == ("record-1",)
    assert evidenced.records[0].states[-2:] == (
        KnowledgeTraceState.REFERENCED, KnowledgeTraceState.EVIDENCED
    )


def test_trace_round_trip_preserves_identity_and_states() -> None:
    trace = _trace().with_observable_evidence(
        "record-1", KnowledgeTraceState.EVIDENCED, evidence_refs=("evidence/runtime.json",)
    )
    restored = KnowledgeTrace.from_dict(json.loads(json.dumps(trace.to_dict())))
    assert restored == trace
    assert restored.stage == "PRE_CODE"
    assert restored.provider_turn == 2


def test_provider_turn_binding_updates_only_injected_records() -> None:
    trace = _trace().with_provider_turn(7, stage="PRE_CODE")

    assert trace.provider_turn == 7
    assert trace.stage == "PRE_CODE"
    assert trace.records[0].provider_turn == 7
    assert trace.records[1].provider_turn is None
    restored = KnowledgeTrace.from_dict(json.loads(json.dumps(trace.to_dict())))
    assert restored == trace


def test_legacy_trace_without_i13_fields_remains_readable() -> None:
    payload = _trace().to_dict()
    for key in ("schema_version", "records", "stage", "provider_turn", "evidence_refs"):
        payload.pop(key, None)
    restored = KnowledgeTrace.from_dict(payload)
    assert restored.retrieved_item_ids == ("record-1", "record-2")
    assert restored.selected_item_ids == ("record-1",)
    assert restored.records[0].states[-1] == KnowledgeTraceState.INJECTED


def test_events_jsonl_round_trip_keeps_knowledge_event_and_redacts_secret(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path, secrets=("secret-token",))
    event = storage.append_event(RunEvent(
        run_id="run-1",
        event_type=RunEventType.KNOWLEDGE_INJECTED,
        payload={"item_id": "record-1", "stage": "PRE_CODE", "secret": "secret-token"},
    ))
    restored = storage.read_events("run-1")
    assert event.sequence == 1
    assert restored[0].event_type == RunEventType.KNOWLEDGE_INJECTED
    assert restored[0].payload["secret"] == "[REDACTED]"


def test_brain_off_trace_has_no_knowledge_states() -> None:
    trace = KnowledgeTrace(run_id="run-off", environment=ENV)
    assert trace.records == ()
    assert trace.retrieved_item_ids == ()
    assert trace.selected_item_ids == ()
    assert trace.context_item_ids == ()
    assert trace.referenced_item_ids == ()
    assert trace.evidenced_item_ids == ()
