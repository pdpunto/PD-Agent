"""Knowledge selection and provider context bridge."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Sequence

from pd_agent.brain.models import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeRetrievalResult,
    KnowledgeRetrievalStatus,
    SourceAuthority,
)
from pd_agent.brain.retrieval import RankedKnowledgeRetrievalResult
from pd_agent.core import ContextSource

from .models import ContextItem, ContextRequest


_AUTHORITY_ORDER: dict[SourceAuthority, int] = {
    SourceAuthority.AUTHORITATIVE_ARTIFACT: 0,
    SourceAuthority.AUTHORITATIVE_SOURCE: 1,
    SourceAuthority.OFFICIAL_DOCUMENTATION: 2,
    SourceAuthority.SECONDARY: 3,
}


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _item_signature(item: KnowledgeItem) -> str:
    content = item.content
    if isinstance(content, Mapping):
        symbol = content.get("symbol")
        if isinstance(symbol, Mapping):
            data = {
                "kind": symbol.get("kind"),
                "official": symbol.get("official"),
                "intermediary": symbol.get("intermediary"),
                "named": symbol.get("named"),
                "descriptor": symbol.get("descriptor"),
            }
            return _stable_json(data)
    return _stable_json(content)


def _relevance_score(item: KnowledgeItem) -> int:
    score = item.metadata.get("match_score")
    if isinstance(score, int):
        return score
    if isinstance(score, float):
        return int(score)
    return 0


def _context_text(result: KnowledgeRetrievalResult | RankedKnowledgeRetrievalResult, item: KnowledgeItem) -> str:
    symbol = item.content.get("symbol") if isinstance(item.content, Mapping) else None
    lines = [
        "retrieved external knowledge",
        f"need_id: {result.need.id}",
        f"need_type: {result.need.type.value}",
        f"query: {result.need.query}",
        f"knowledge_item_id: {item.id}",
        f"authority: {item.authority.value}",
        f"source_id: {item.provenance.source_id}",
        f"source_kind: {item.provenance.source_kind}",
        f"version: {item.provenance.artifact_or_document_version}",
        f"revision: {item.provenance.revision}",
        f"checksum: {item.provenance.checksum}",
        f"locator: {item.provenance.locator}",
    ]
    if symbol is not None:
        lines.append(f"symbol: {_stable_json(symbol)}")
    else:
        lines.append(f"content: {_stable_json(item.content)}")
    return "\n".join(lines)


def _context_bytes(result: KnowledgeRetrievalResult, item: KnowledgeItem) -> int:
    context_item = ContextItem.from_text(
        source="knowledge",
        priority=35,
        label=item.content.get("symbol", {}).get("named") if isinstance(item.content, Mapping) else item.id,
        content=_context_text(result, item),
        metadata={
            "knowledge_item_id": item.id,
            "knowledge_need_id": result.need.id,
            "authority": item.authority.value,
            "source_id": item.provenance.source_id,
            "source_kind": item.provenance.source_kind,
            "version": item.provenance.artifact_or_document_version,
            "revision": item.provenance.revision,
            "checksum": item.provenance.checksum,
            "locator": item.provenance.locator,
            "environment": result.need.environment.to_dict(),
        },
    )
    return len(context_item.render().encode("utf-8"))


@dataclass(frozen=True, slots=True)
class KnowledgeSourceAttempt:
    """Single source attempt trace."""

    source_id: str
    source_kind: str
    status: KnowledgeRetrievalStatus
    retrieved_item_ids: tuple[str, ...] = ()
    locator: str | None = None
    revision: str | None = None
    checksum: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "status": self.status.value,
            "retrieved_item_ids": list(self.retrieved_item_ids),
            "locator": self.locator,
            "revision": self.revision,
            "checksum": self.checksum,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeSourceAttempt":
        return cls(
            source_id=str(data["source_id"]),
            source_kind=str(data["source_kind"]),
            status=KnowledgeRetrievalStatus(str(data["status"])),
            retrieved_item_ids=tuple(str(item) for item in data.get("retrieved_item_ids", [])),
            locator=data.get("locator"),
            revision=data.get("revision"),
            checksum=data.get("checksum"),
            error=data.get("error"),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeRejection:
    """Selection rejection record."""

    item_id: str
    reason: str
    authority: SourceAuthority

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "reason": self.reason,
            "authority": self.authority.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeRejection":
        return cls(
            item_id=str(data["item_id"]),
            reason=str(data["reason"]),
            authority=SourceAuthority(str(data["authority"])),
        )


class KnowledgeTraceState(StrEnum):
    """Observable stages in the knowledge evidence chain."""

    RETRIEVED = "RETRIEVED"
    SELECTED = "SELECTED"
    INJECTED = "INJECTED"
    REFERENCED = "REFERENCED"
    EVIDENCED = "EVIDENCED"


@dataclass(frozen=True, slots=True)
class KnowledgeTraceRecord:
    """Bounded identity and observable state for one knowledge record."""

    item_id: str
    states: tuple[KnowledgeTraceState, ...] = ()
    need_id: str | None = None
    source_id: str | None = None
    source_revision: str | None = None
    checksum: str | None = None
    context_item_id: str | None = None
    provider_turn: int | None = None
    stage: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "states": [state.value for state in self.states],
            "need_id": self.need_id,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "checksum": self.checksum,
            "context_item_id": self.context_item_id,
            "provider_turn": self.provider_turn,
            "stage": self.stage,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeTraceRecord":
        return cls(
            item_id=str(data["item_id"]),
            states=tuple(KnowledgeTraceState(str(state)) for state in data.get("states", [])),
            need_id=data.get("need_id"),
            source_id=data.get("source_id"),
            source_revision=data.get("source_revision"),
            checksum=data.get("checksum"),
            context_item_id=data.get("context_item_id"),
            provider_turn=(int(data["provider_turn"]) if data.get("provider_turn") is not None else None),
            stage=data.get("stage"),
            evidence_refs=tuple(str(ref) for ref in data.get("evidence_refs", [])),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeTrace:
    """Machine-readable trace for knowledge flow."""

    run_id: str | None
    environment: KnowledgeEnvironment
    needs: tuple[KnowledgeNeed, ...] = ()
    source_attempts: tuple[KnowledgeSourceAttempt, ...] = ()
    retrieved_item_ids: tuple[str, ...] = ()
    rejected_items: tuple[KnowledgeRejection, ...] = ()
    selected_item_ids: tuple[str, ...] = ()
    context_item_ids: tuple[str, ...] = ()
    misses: tuple[str, ...] = ()
    records: tuple[KnowledgeTraceRecord, ...] = ()
    stage: str | None = None
    provider_turn: int | None = None
    evidence_refs: tuple[str, ...] = ()
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.records:
            return
        selected = set(self.selected_item_ids)
        injected = set(self.context_item_ids)
        source_by_item: dict[str, KnowledgeSourceAttempt] = {}
        for attempt in self.source_attempts:
            for item_id in attempt.retrieved_item_ids:
                source_by_item.setdefault(item_id, attempt)
        need_id = self.needs[0].id if self.needs else None
        records: list[KnowledgeTraceRecord] = []
        for item_id in self.retrieved_item_ids:
            attempt = source_by_item.get(item_id)
            states = [KnowledgeTraceState.RETRIEVED]
            if item_id in selected:
                states.append(KnowledgeTraceState.SELECTED)
            if item_id in injected:
                states.append(KnowledgeTraceState.INJECTED)
            records.append(KnowledgeTraceRecord(
                item_id=item_id,
                states=tuple(states),
                need_id=need_id,
                source_id=attempt.source_id if attempt else None,
                source_revision=attempt.revision if attempt else None,
                checksum=attempt.checksum if attempt else None,
                context_item_id=item_id if item_id in injected else None,
                stage=self.stage,
                provider_turn=self.provider_turn if item_id in injected else None,
            ))
        object.__setattr__(self, "records", tuple(records))

    @property
    def referenced_item_ids(self) -> tuple[str, ...]:
        return tuple(record.item_id for record in self.records if KnowledgeTraceState.REFERENCED in record.states)

    @property
    def evidenced_item_ids(self) -> tuple[str, ...]:
        return tuple(record.item_id for record in self.records if KnowledgeTraceState.EVIDENCED in record.states)

    def with_observable_evidence(
        self,
        item_id: str,
        state: KnowledgeTraceState,
        *,
        evidence_refs: Sequence[str] = (),
        provider_turn: int | None = None,
        stage: str | None = None,
    ) -> "KnowledgeTrace":
        """Add only explicitly observed reference/evidence, never infer it."""
        if state not in {KnowledgeTraceState.REFERENCED, KnowledgeTraceState.EVIDENCED}:
            raise ValueError("only REFERENCED or EVIDENCED may be added explicitly")
        records = list(self.records)
        for index, record in enumerate(records):
            if record.item_id != item_id:
                continue
            states = tuple(dict.fromkeys((*record.states, state)))
            records[index] = KnowledgeTraceRecord(
                item_id=record.item_id, states=states, need_id=record.need_id,
                source_id=record.source_id, source_revision=record.source_revision,
                checksum=record.checksum, context_item_id=record.context_item_id,
                provider_turn=provider_turn if provider_turn is not None else record.provider_turn,
                stage=stage if stage is not None else record.stage,
                evidence_refs=tuple(dict.fromkeys((*record.evidence_refs, *evidence_refs))),
            )
            return KnowledgeTrace(
                run_id=self.run_id, environment=self.environment, needs=self.needs,
                source_attempts=self.source_attempts, retrieved_item_ids=self.retrieved_item_ids,
                rejected_items=self.rejected_items, selected_item_ids=self.selected_item_ids,
                context_item_ids=self.context_item_ids, misses=self.misses, records=tuple(records),
                stage=self.stage, provider_turn=self.provider_turn, evidence_refs=tuple(
                    dict.fromkeys((*self.evidence_refs, *evidence_refs))
                ), started_at=self.started_at, finished_at=datetime.now(timezone.utc),
            )
        raise ValueError(f"unknown knowledge item: {item_id}")

    def with_provider_turn(self, provider_turn: int, *, stage: str | None = None) -> "KnowledgeTrace":
        """Bind this injection to the logical provider turn that received it."""
        if provider_turn < 1:
            raise ValueError("provider_turn must be positive")
        effective_stage = stage if stage is not None else self.stage
        records = tuple(
            KnowledgeTraceRecord(
                item_id=record.item_id,
                states=record.states,
                need_id=record.need_id,
                source_id=record.source_id,
                source_revision=record.source_revision,
                checksum=record.checksum,
                context_item_id=record.context_item_id,
                provider_turn=(provider_turn if KnowledgeTraceState.INJECTED in record.states else record.provider_turn),
                stage=effective_stage,
                evidence_refs=record.evidence_refs,
            )
            for record in self.records
        )
        return KnowledgeTrace(
            run_id=self.run_id, environment=self.environment, needs=self.needs,
            source_attempts=self.source_attempts, retrieved_item_ids=self.retrieved_item_ids,
            rejected_items=self.rejected_items, selected_item_ids=self.selected_item_ids,
            context_item_ids=self.context_item_ids, misses=self.misses, records=records,
            stage=effective_stage,
            provider_turn=(provider_turn if self.context_item_ids else self.provider_turn),
            evidence_refs=self.evidence_refs, started_at=self.started_at,
            finished_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.7",
            "run_id": self.run_id,
            "environment": self.environment.to_dict(),
            "needs": [need.to_dict() for need in self.needs],
            "source_attempts": [item.to_dict() for item in self.source_attempts],
            "retrieved_item_ids": list(self.retrieved_item_ids),
            "rejected_items": [item.to_dict() for item in self.rejected_items],
            "selected_item_ids": list(self.selected_item_ids),
            "context_item_ids": list(self.context_item_ids),
            "misses": list(self.misses),
            "records": [record.to_dict() for record in self.records],
            "stage": self.stage,
            "provider_turn": self.provider_turn,
            "evidence_refs": list(self.evidence_refs),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeTrace":
        return cls(
            run_id=data.get("run_id"),
            environment=KnowledgeEnvironment.from_dict(dict(data["environment"])),
            needs=tuple(KnowledgeNeed.from_dict(item) for item in data.get("needs", [])),
            source_attempts=tuple(
                KnowledgeSourceAttempt.from_dict(item) for item in data.get("source_attempts", [])
            ),
            retrieved_item_ids=tuple(str(item) for item in data.get("retrieved_item_ids", [])),
            rejected_items=tuple(
                KnowledgeRejection.from_dict(item) for item in data.get("rejected_items", [])
            ),
            selected_item_ids=tuple(str(item) for item in data.get("selected_item_ids", [])),
            context_item_ids=tuple(str(item) for item in data.get("context_item_ids", [])),
            misses=tuple(str(item) for item in data.get("misses", [])),
            records=tuple(KnowledgeTraceRecord.from_dict(item) for item in data.get("records", [])),
            stage=data.get("stage"),
            provider_turn=(int(data["provider_turn"]) if data.get("provider_turn") is not None else None),
            evidence_refs=tuple(str(ref) for ref in data.get("evidence_refs", [])),
            started_at=datetime.fromisoformat(str(data["started_at"])),
            finished_at=datetime.fromisoformat(str(data["finished_at"])),
        )


@dataclass(frozen=True, slots=True)
class SelectedKnowledge:
    """Selected knowledge after ranking and budget."""

    retrieval_result: KnowledgeRetrievalResult | RankedKnowledgeRetrievalResult
    selected_items: tuple[KnowledgeItem, ...]
    rejected_items: tuple[KnowledgeRejection, ...]
    trace: KnowledgeTrace

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_result": self.retrieval_result.to_dict(),
            "selected_items": [item.to_dict() for item in self.selected_items],
            "rejected_items": [item.to_dict() for item in self.rejected_items],
            "trace": self.trace.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SelectedKnowledge":
        return cls(
            retrieval_result=KnowledgeRetrievalResult.from_dict(dict(data["retrieval_result"])),
            selected_items=tuple(
                KnowledgeItem.from_dict(item) for item in data.get("selected_items", [])
            ),
            rejected_items=tuple(
                KnowledgeRejection.from_dict(item) for item in data.get("rejected_items", [])
            ),
            trace=KnowledgeTrace.from_dict(dict(data["trace"])),
        )


class KnowledgeSelector:
    """Deterministic ranker for retrieved knowledge."""

    def select(
        self,
        result: KnowledgeRetrievalResult | RankedKnowledgeRetrievalResult,
        *,
        budget_bytes: int,
        run_id: str | None = None,
    ) -> SelectedKnowledge:
        started_at = datetime.now(timezone.utc)
        trace = KnowledgeTrace(
            run_id=run_id,
            environment=result.need.environment,
            needs=(result.need,),
            source_attempts=self._source_attempts(result),
            retrieved_item_ids=tuple(item.id for item in result.items),
            misses=(),
            started_at=started_at,
            finished_at=started_at,
        )
        if result.status != KnowledgeRetrievalStatus.SUCCESS or not result.items:
            misses = self._misses(result)
            return SelectedKnowledge(
                retrieval_result=result,
                selected_items=(),
                rejected_items=(),
                trace=KnowledgeTrace(
                    run_id=trace.run_id,
                    environment=trace.environment,
                    needs=trace.needs,
                    source_attempts=trace.source_attempts,
                    retrieved_item_ids=trace.retrieved_item_ids,
                    rejected_items=(),
                    selected_item_ids=(),
                    context_item_ids=(),
                    misses=misses,
                    started_at=trace.started_at,
                    finished_at=datetime.now(timezone.utc),
                ),
            )

        if isinstance(result, RankedKnowledgeRetrievalResult):
            ordered = []
            rejected = []
            for candidate in result.candidates:
                if candidate.conflict_ids:
                    rejected.append(KnowledgeRejection(
                        item_id=candidate.item.id,
                        reason="UNRESOLVED_CONFLICT",
                        authority=candidate.item.authority,
                    ))
                else:
                    ordered.append(candidate.item)
        else:
            deduped, rejected = self._dedupe(result.items)
            ordered = sorted(
                deduped,
                key=lambda item: (
                    _AUTHORITY_ORDER.get(item.authority, 99),
                    -_relevance_score(item),
                    item.id,
                ),
            )
        selected: list[KnowledgeItem] = []
        selected_ids: list[str] = []
        context_ids: list[str] = []
        budget_used = 0
        for item in ordered:
            size = _context_bytes(result, item)
            if budget_used + size > budget_bytes:
                rejected.append(KnowledgeRejection(item_id=item.id, reason="CONTEXT_BUDGET", authority=item.authority))
                continue
            selected.append(item)
            selected_ids.append(item.id)
            context_ids.append(item.id)
            budget_used += size
        return SelectedKnowledge(
            retrieval_result=result,
            selected_items=tuple(selected),
            rejected_items=tuple(rejected),
            trace=KnowledgeTrace(
                run_id=run_id,
                environment=result.need.environment,
                needs=(result.need,),
                source_attempts=trace.source_attempts,
                retrieved_item_ids=trace.retrieved_item_ids,
                rejected_items=tuple(rejected),
                selected_item_ids=tuple(selected_ids),
                context_item_ids=tuple(context_ids),
                misses=self._misses(result),
                started_at=trace.started_at,
                finished_at=datetime.now(timezone.utc),
            ),
        )

    def _dedupe(self, items: Sequence[KnowledgeItem]) -> tuple[tuple[KnowledgeItem, ...], list[KnowledgeRejection]]:
        grouped: dict[str, list[KnowledgeItem]] = {}
        for item in items:
            grouped.setdefault(_item_signature(item), []).append(item)
        deduped: list[KnowledgeItem] = []
        rejected: list[KnowledgeRejection] = []
        for group_items in grouped.values():
            ordered = sorted(
                group_items,
                key=lambda item: (
                    _AUTHORITY_ORDER.get(item.authority, 99),
                    -_relevance_score(item),
                    item.id,
                ),
            )
            deduped.append(ordered[0])
            rejected.extend(
                KnowledgeRejection(item_id=item.id, reason="LOWER_AUTHORITY_DUPLICATE", authority=item.authority)
                for item in ordered[1:]
            )
        return tuple(deduped), rejected

    def _source_attempts(self, result: KnowledgeRetrievalResult) -> tuple[KnowledgeSourceAttempt, ...]:
        if result.source_results:
            attempts = []
            for source_result in result.source_results:
                attempts.append(
                    KnowledgeSourceAttempt(
                        source_id=source_result.source_id,
                        source_kind=source_result.source_kind,
                        status=source_result.status,
                        retrieved_item_ids=tuple(item.id for item in source_result.items),
                        locator=(source_result.provenance[0].locator if source_result.provenance else None),
                        revision=(source_result.provenance[0].revision if source_result.provenance else None),
                        checksum=(source_result.provenance[0].checksum if source_result.provenance else None),
                        error=source_result.error,
                    )
                )
            return tuple(attempts)
        return (
            KnowledgeSourceAttempt(
                source_id="unknown",
                source_kind="unknown",
                status=result.status,
                retrieved_item_ids=tuple(item.id for item in result.items),
                error=getattr(result, "error", None),
            ),
        )

    def _misses(self, result: KnowledgeRetrievalResult) -> tuple[str, ...]:
        if result.status == KnowledgeRetrievalStatus.SUCCESS:
            return ()
        if result.status == KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE:
            return ("UNKNOWN_COMPATIBILITY",)
        if result.status == KnowledgeRetrievalStatus.VERSION_MISMATCH:
            return ("VERSION_MISMATCH",)
        if result.status in {KnowledgeRetrievalStatus.SOURCE_ERROR, KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE}:
            return ("SOURCE_ERROR",)
        if result.status == KnowledgeRetrievalStatus.OFFLINE_MISS:
            return ("OFFLINE_MISS",)
        return (result.status.value,)


@dataclass(slots=True)
class KnowledgeContextSource:
    """ContextSource adapter for selected knowledge."""

    selector: KnowledgeSelector = field(default_factory=KnowledgeSelector)
    max_items: int = 5
    max_context_bytes: int = 8_192
    name: str = "knowledge"
    last_traces: tuple[KnowledgeTrace, ...] = ()

    def get(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        raw_inputs = tuple(
            item
            for item in request.external_context
            if isinstance(item, (KnowledgeRetrievalResult, RankedKnowledgeRetrievalResult, SelectedKnowledge))
        )
        if not raw_inputs:
            self.last_traces = ()
            return ()

        budget = self.max_context_bytes
        if request.limits is not None:
            budget = min(budget, request.limits.max_context_bytes)

        # A current failure is more actionable than stale or generic context.
        # Keep the single global budget, but allocate it in this order.
        raw_inputs = tuple(sorted(raw_inputs, key=lambda item: (
            0 if self._is_failure_specific(item) else 1,
        )))
        items: list[ContextItem] = []
        traces: list[KnowledgeTrace] = []
        remaining_budget = budget
        context_index = 0
        for raw in raw_inputs:
            retrieval = raw.retrieval_result if isinstance(raw, SelectedKnowledge) else raw
            selected = self.selector.select(
                retrieval,
                budget_bytes=remaining_budget,
                run_id=request.run_state.run_id if request.run_state is not None else None,
            )
            injected_ids: list[str] = []
            for item in selected.selected_items[:self.max_items]:
                context_item = self._to_context_item(selected.retrieval_result, item, context_index)
                context_index += 1
                items.append(context_item)
                injected_ids.append(item.id)
                remaining_budget = max(0, remaining_budget - len(context_item.render().encode("utf-8")))
            trace = selected.trace
            if tuple(injected_ids) != trace.context_item_ids:
                trace = KnowledgeTrace(
                    run_id=trace.run_id, environment=trace.environment, needs=trace.needs,
                    source_attempts=trace.source_attempts, retrieved_item_ids=trace.retrieved_item_ids,
                    rejected_items=trace.rejected_items, selected_item_ids=trace.selected_item_ids,
                    context_item_ids=tuple(injected_ids), misses=trace.misses, records=tuple(
                        KnowledgeTraceRecord(
                            item_id=record.item_id,
                            states=tuple(dict.fromkeys((*record.states, KnowledgeTraceState.INJECTED)))
                            if record.item_id in injected_ids else record.states,
                            need_id=record.need_id, source_id=record.source_id,
                            source_revision=record.source_revision, checksum=record.checksum,
                            context_item_id=record.item_id if record.item_id in injected_ids else record.context_item_id,
                            provider_turn=record.provider_turn, stage=record.stage,
                            evidence_refs=record.evidence_refs,
                        ) for record in trace.records
                    ), stage=trace.stage, provider_turn=trace.provider_turn,
                    evidence_refs=trace.evidence_refs,
                    started_at=trace.started_at, finished_at=datetime.now(timezone.utc),
                )
            traces.append(trace)

        self.last_traces = tuple(traces)
        return tuple(items)

    @staticmethod
    def _is_failure_specific(raw: KnowledgeRetrievalResult | RankedKnowledgeRetrievalResult | SelectedKnowledge) -> bool:
        retrieval = raw.retrieval_result if isinstance(raw, SelectedKnowledge) else raw
        return retrieval.need.id.casefold().startswith("semantic-repair:")

    def _to_context_item(self, result: KnowledgeRetrievalResult | RankedKnowledgeRetrievalResult,
                         item: KnowledgeItem, index: int) -> ContextItem:
        content = _context_text(result, item)
        metadata = {
            "knowledge_item_id": item.id,
            "knowledge_need_id": result.need.id,
            "knowledge_need_type": result.need.type.value,
            "environment": result.need.environment.to_dict(),
            "authority": item.authority.value,
            "source_id": item.provenance.source_id,
            "source_kind": item.provenance.source_kind,
            "locator": item.provenance.locator,
            "version": item.provenance.artifact_or_document_version,
            "revision": item.provenance.revision,
            "checksum": item.provenance.checksum,
        }
        return ContextItem.from_text(
            source=self.name,
            priority=35 + index,
            label=f"knowledge-{item.id[:8]}",
            content=content,
            metadata=metadata,
        )
