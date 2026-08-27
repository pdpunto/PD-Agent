"""Knowledge selection and provider context bridge."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "environment": self.environment.to_dict(),
            "needs": [need.to_dict() for need in self.needs],
            "source_attempts": [item.to_dict() for item in self.source_attempts],
            "retrieved_item_ids": list(self.retrieved_item_ids),
            "rejected_items": [item.to_dict() for item in self.rejected_items],
            "selected_item_ids": list(self.selected_item_ids),
            "context_item_ids": list(self.context_item_ids),
            "misses": list(self.misses),
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

        items: list[ContextItem] = []
        traces: list[KnowledgeTrace] = []
        remaining_budget = budget
        context_index = 0
        for raw in raw_inputs:
            if isinstance(raw, SelectedKnowledge):
                selected = raw
            else:
                selected = self.selector.select(
                    raw,
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
                    context_item_ids=tuple(injected_ids), misses=trace.misses,
                    started_at=trace.started_at, finished_at=datetime.now(timezone.utc),
                )
            traces.append(trace)

        self.last_traces = tuple(traces)
        return tuple(items)

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
