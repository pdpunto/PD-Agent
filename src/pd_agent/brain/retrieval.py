"""Deterministic knowledge retrieval and cache for Minecraft Brain L2."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from .models import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeRetrievalResult,
    KnowledgeRetrievalStatus,
    KnowledgeSourceResult,
    KnowledgeType,
    SourceAuthority,
)
from .canonical import KnowledgeRecord


class RetrievalMatchClass(StrEnum):
    """Deterministic retrieval tier, ordered from strongest to weakest."""

    EXACT = "exact"
    STRUCTURED = "structured"
    LEXICAL = "lexical"


class RetrievalConflictStatus(StrEnum):
    """Conflict state attached to a bounded retrieval result."""

    NONE = "none"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalCandidate:
    """An eligible, explainable candidate produced by the I9 pipeline."""

    item: KnowledgeItem
    match_class: RetrievalMatchClass
    compatibility: CompatibilityStatus
    authority_score: int
    specificity_score: int
    relevance_score: int
    rank_reason: str
    conflict_ids: tuple[str, ...] = ()

    @property
    def record_id(self) -> str:
        return self.item.id

    @property
    def provenance(self) -> KnowledgeProvenance:
        return self.item.provenance


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalConflict:
    """Material contradiction retained without silently merging records."""

    key: str
    candidate_ids: tuple[str, ...]
    provenance: tuple[KnowledgeProvenance, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class RankedKnowledgeRetrievalResult:
    """Bounded I9 result; selection and injection remain later stages."""

    status: KnowledgeRetrievalStatus
    need: KnowledgeNeed
    candidates: tuple[KnowledgeRetrievalCandidate, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()
    conflicts: tuple[KnowledgeRetrievalConflict, ...] = ()
    source_results: tuple[KnowledgeSourceResult, ...] = ()
    degraded: bool = False
    offline: bool = False

    @property
    def items(self) -> tuple[KnowledgeItem, ...]:
        """Compatibility view for consumers that only need retrieved items."""
        return tuple(candidate.item for candidate in self.candidates)

    @property
    def conflict_status(self) -> RetrievalConflictStatus:
        return (RetrievalConflictStatus.UNRESOLVED if self.conflicts
                else RetrievalConflictStatus.NONE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "need": self.need.to_dict(),
            "candidates": [
                {
                    "item": candidate.item.to_dict(),
                    "match_class": candidate.match_class.value,
                    "compatibility": candidate.compatibility.value,
                    "authority_score": candidate.authority_score,
                    "specificity_score": candidate.specificity_score,
                    "relevance_score": candidate.relevance_score,
                    "rank_reason": candidate.rank_reason,
                    "conflict_ids": list(candidate.conflict_ids),
                }
                for candidate in self.candidates
            ],
            "rejected": [list(entry) for entry in self.rejected],
            "conflicts": [
                {
                    "key": conflict.key,
                    "candidate_ids": list(conflict.candidate_ids),
                    "provenance": [item.to_dict() for item in conflict.provenance],
                    "reason": conflict.reason,
                }
                for conflict in self.conflicts
            ],
            "degraded": self.degraded,
            "offline": self.offline,
        }


@runtime_checkable
class KnowledgeSource(Protocol):
    """Minimal source adapter contract."""

    source_id: str
    source_kind: str
    artifact_version: str

    def supports(self, need: KnowledgeNeed) -> bool:
        """Return True when the source can handle the need."""

    def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
        """Return environment compatibility."""

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeSourceResult:
        """Resolve a need into source items."""


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_segment(value: str) -> str:
    cleaned = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    return "".join(cleaned).strip("._") or "unknown"


def _query_hash(need: KnowledgeNeed) -> str:
    data = {
        "type": need.type.value,
        "query": need.query.strip().casefold(),
        "hints": [hint.strip().casefold() for hint in need.hints],
        "environment": need.environment.to_dict(),
    }
    return hashlib.sha256(_stable_json(data).encode("utf-8")).hexdigest()


def _result_cache_key(
    *,
    source_id: str,
    artifact_version: str,
    checksum: str | None,
    need: KnowledgeNeed,
) -> str:
    environment = need.environment.to_dict()
    data = {
        "source_id": source_id,
        "artifact_version": artifact_version,
        "checksum": checksum,
        "knowledge_type": need.type.value,
        "query": need.query.strip().casefold(),
        "minecraft_version": environment["minecraft_version"],
        "mappings_namespace": environment["mappings_namespace"],
        "mappings_version": environment["mappings_version"],
        "fabric_api_version": environment["fabric_api_version"],
    }
    return hashlib.sha256(_stable_json(data).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class FileKnowledgeCache:
    """Simple JSON cache stored on disk."""

    root: Path

    def get(
        self,
        *,
        source_id: str,
        artifact_version: str,
        checksum: str | None,
        need: KnowledgeNeed,
    ) -> KnowledgeRetrievalResult | None:
        path = self._entry_path(
            source_id=source_id,
            artifact_version=artifact_version,
            need=need,
        )
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        result = KnowledgeRetrievalResult.from_dict(data)
        cached_checksum = result.source_results[0].provenance[0].checksum if result.source_results and result.source_results[0].provenance else None
        if checksum is not None and cached_checksum is not None and checksum != cached_checksum:
            return None
        return result

    def put(
        self,
        result: KnowledgeRetrievalResult,
        *,
        source_id: str,
        artifact_version: str,
        checksum: str | None,
    ) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._entry_path(
            source_id=source_id,
            artifact_version=artifact_version,
            need=result.need,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def invalidate(self, *, source_id: str | None = None) -> None:
        if not self.root.exists():
            return
        if source_id is None:
            for path in self.root.rglob("*.json"):
                path.unlink()
            return
        for path in self.root.glob(f"{source_id}/**/*.json"):
            path.unlink()

    def _entry_path(
        self,
        *,
        source_id: str,
        artifact_version: str,
        need: KnowledgeNeed,
    ) -> Path:
        return (
            self.root
            / _safe_segment(source_id)
            / _safe_segment(artifact_version)
            / (need.environment.minecraft_version or "unknown-minecraft")
            / _safe_segment(need.environment.mappings_namespace or "unknown-namespace")
            / _safe_segment(need.environment.mappings_version or "unknown-mappings")
            / f"{_query_hash(need)}.json"
        )


@dataclass(slots=True)
class MinecraftBrain:
    """Minimal orchestrator for deterministic retrieval."""

    source: KnowledgeSource
    cache: FileKnowledgeCache

    def retrieve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeRetrievalResult:
        compatibility = self.source.compatibility(need.environment)
        if compatibility == CompatibilityStatus.INCOMPATIBLE:
            return KnowledgeRetrievalResult(
                status=KnowledgeRetrievalStatus.VERSION_MISMATCH,
                need=need,
                offline=offline,
                error="source environment incompatible",
            )
        if compatibility == CompatibilityStatus.UNKNOWN and need.version_sensitive:
            return KnowledgeRetrievalResult(
                status=KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE,
                need=need,
                offline=offline,
                error="version-sensitive knowledge requires known compatibility",
            )

        checksum = getattr(self.source, "artifact_checksum", None)
        cached = self.cache.get(
            source_id=self.source.source_id,
            artifact_version=self.source.artifact_version,
            checksum=checksum,
            need=need,
        )
        if cached is not None:
            return KnowledgeRetrievalResult(
                status=cached.status,
                need=cached.need,
                items=cached.items,
                source_results=cached.source_results,
                cache_hit=True,
                offline=offline,
                error=cached.error,
            )
        if offline:
            return KnowledgeRetrievalResult(
                status=KnowledgeRetrievalStatus.OFFLINE_MISS,
                need=need,
                offline=True,
                error="offline cache miss",
            )

        source_result = self.source.resolve(need, offline=False)
        if source_result.status != KnowledgeRetrievalStatus.SUCCESS:
            return KnowledgeRetrievalResult(
                status=source_result.status,
                need=need,
                items=(),
                source_results=(source_result,),
                cache_hit=False,
                offline=False,
                error=source_result.error,
            )

        items = self._deduplicate(source_result.items)
        result = KnowledgeRetrievalResult(
            status=KnowledgeRetrievalStatus.SUCCESS,
            need=need,
            items=items,
            source_results=(source_result,),
            cache_hit=False,
            offline=False,
        )
        self.cache.put(
            result,
            source_id=self.source.source_id,
            artifact_version=self.source.artifact_version,
            checksum=checksum,
        )
        return result

    def _deduplicate(self, items: Sequence[KnowledgeItem]) -> tuple[KnowledgeItem, ...]:
        seen: set[str] = set()
        ordered: list[KnowledgeItem] = []
        for item in items:
            key = item.id
            if key in seen:
                continue
            seen.add(key)
            ordered.append(item)
        return tuple(ordered)


@dataclass(slots=True)
class KnowledgeService:
    """Ordered, provider-agnostic aggregator for multiple knowledge sources."""

    sources: tuple[KnowledgeSource, ...] = ()
    cache: FileKnowledgeCache | None = None

    def __post_init__(self) -> None:
        self.sources = tuple(sorted(self.sources, key=lambda source: source.source_id))
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("KnowledgeService source_id values must be unique")

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeRetrievalResult:
        attempts: list[KnowledgeSourceResult] = []
        items: list[KnowledgeItem] = []
        cache_hit = False

        for source in self.sources:
            source_id = source.source_id
            source_kind = source.source_kind
            try:
                compatibility = source.compatibility(need.environment)
            except Exception as exc:
                attempts.append(self._attempt(source, need, KnowledgeRetrievalStatus.SOURCE_ERROR, eligible=False, error=str(exc)))
                continue
            if compatibility == CompatibilityStatus.INCOMPATIBLE:
                attempts.append(self._attempt(source, need, KnowledgeRetrievalStatus.VERSION_MISMATCH,
                                               compatibility=compatibility, eligible=False,
                                               error="source environment incompatible"))
                continue
            if compatibility == CompatibilityStatus.UNKNOWN and need.version_sensitive:
                attempts.append(self._attempt(source, need, KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE,
                                               compatibility=compatibility, eligible=False,
                                               error="version-sensitive knowledge requires known compatibility"))
                continue
            try:
                supported = source.supports(need)
            except Exception as exc:
                attempts.append(self._attempt(source, need, KnowledgeRetrievalStatus.SOURCE_ERROR,
                                               compatibility=compatibility, eligible=False, error=str(exc)))
                continue
            if not supported:
                attempts.append(self._attempt(source, need, KnowledgeRetrievalStatus.UNSUPPORTED_NEED,
                                               compatibility=compatibility, supported=False, eligible=False,
                                               error="source does not support need"))
                continue

            cached = None
            checksum = getattr(source, "artifact_checksum", None)
            if self.cache is not None:
                cached = self.cache.get(source_id=source_id, artifact_version=source.artifact_version,
                                        checksum=checksum, need=need)
            if cached is not None:
                cache_hit = True
                cached_attempt = next((item for item in cached.source_results if item.source_id == source_id), None)
                if cached_attempt is not None:
                    attempts.append(replace(cached_attempt, compatibility=compatibility, supported=True, eligible=True))
                else:
                    attempts.append(self._attempt(source, need, cached.status, compatibility=compatibility,
                                                   supported=True, items=cached.items, eligible=True))
                items.extend(cached.items)
                continue
            try:
                result = source.resolve(need, offline=offline)
            except Exception as exc:
                attempts.append(self._attempt(source, need, KnowledgeRetrievalStatus.SOURCE_ERROR,
                                               compatibility=compatibility, supported=True, eligible=True, error=str(exc)))
                continue
            attempts.append(replace(result, compatibility=compatibility, supported=True, eligible=True))
            if result.status == KnowledgeRetrievalStatus.SUCCESS:
                items.extend(result.items)

        deduplicated = self._deduplicate(items)
        status = KnowledgeRetrievalStatus.SUCCESS if deduplicated else self._aggregate_status(attempts)
        error = "; ".join(item.error for item in attempts if item.error) or None
        return KnowledgeRetrievalResult(status=status, need=need, items=deduplicated,
                                        source_results=tuple(attempts), cache_hit=cache_hit,
                                        offline=offline, error=error)

    def retrieve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeRetrievalResult:
        """Alias matching the historical MinecraftBrain API."""
        return self.resolve(need, offline=offline)

    def retrieve_ranked(self, need: KnowledgeNeed, *, indexes: Sequence[Any] = (),
                        packs: Sequence[Any] = (), offline: bool = False,
                        max_candidates: int = 10) -> RankedKnowledgeRetrievalResult:
        """Run the I9 bounded pipeline without changing legacy retrieval semantics."""
        return KnowledgeRetrievalEngine(self, max_candidates=max_candidates).retrieve(
            need, indexes=indexes, packs=packs, offline=offline
        )

    @staticmethod
    def _attempt(source: KnowledgeSource, need: KnowledgeNeed, status: KnowledgeRetrievalStatus,
                 *, compatibility: CompatibilityStatus | None = None, supported: bool | None = None,
                 eligible: bool, items: tuple[KnowledgeItem, ...] = (), error: str | None = None) -> KnowledgeSourceResult:
        return KnowledgeSourceResult(status=status, source_id=source.source_id, source_kind=source.source_kind,
                                     need=need, items=items, error=error, compatibility=compatibility,
                                     supported=supported, eligible=eligible)

    @staticmethod
    def _aggregate_status(attempts: Sequence[KnowledgeSourceResult]) -> KnowledgeRetrievalStatus:
        if not attempts:
            return KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE
        for status in (KnowledgeRetrievalStatus.SOURCE_ERROR, KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE,
                       KnowledgeRetrievalStatus.OFFLINE_MISS, KnowledgeRetrievalStatus.VERSION_MISMATCH,
                       KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE, KnowledgeRetrievalStatus.UNSUPPORTED_NEED):
            if any(item.status == status for item in attempts):
                return status
        return attempts[0].status

    @staticmethod
    def _deduplicate(items: Sequence[KnowledgeItem]) -> tuple[KnowledgeItem, ...]:
        seen: set[str] = set()
        result: list[KnowledgeItem] = []
        for item in items:
            identity = str(item.metadata.get("record_identity", item.id))
            if identity in seen:
                continue
            seen.add(identity)
            result.append(item)
        return tuple(result)


_AUTHORITY_SCORE = {
    SourceAuthority.AUTHORITATIVE_ARTIFACT: 4,
    SourceAuthority.AUTHORITATIVE_SOURCE: 3,
    SourceAuthority.OFFICIAL_DOCUMENTATION: 2,
    SourceAuthority.SECONDARY: 1,
}
_VERSION_FIELDS = ("minecraft_version", "loader_version", "mappings_namespace",
                   "mappings_version", "fabric_api_version")
_LEXICAL_TOKEN = re.compile(r"[A-Za-z0-9_:.+-]+")


def _record_as_item(record: KnowledgeRecord) -> KnowledgeItem:
    """Adapt canonical data to the legacy retrieval item without losing identity."""
    metadata = {
        "record_identity": record.identity(),
        "record_kind": record.kind.value,
        "capability": record.capability,
        "source_revision": record.source_revision,
    }
    return KnowledgeItem(record.record_id, record.content, record.environment,
                         record.authority, record.provenance, metadata,
                         record.version_sensitive)


def _environment_compatibility(item: KnowledgeItem, need: KnowledgeNeed) -> CompatibilityStatus:
    missing = False
    for field_name in _VERSION_FIELDS:
        requested = getattr(need.environment, field_name)
        available = getattr(item.environment, field_name)
        if requested is not None and available is not None and requested != available:
            return CompatibilityStatus.INCOMPATIBLE
        if requested is not None and available is None:
            missing = True
    if (need.version_sensitive or item.version_sensitive) and missing:
        return CompatibilityStatus.UNKNOWN
    return CompatibilityStatus.COMPATIBLE


def _content_text(item: KnowledgeItem) -> str:
    def flatten(value: Any) -> list[str]:
        if isinstance(value, Mapping):
            return [str(key) for key in value] + [part for child in value.values() for part in flatten(child)]
        if isinstance(value, (list, tuple)):
            return [part for child in value for part in flatten(child)]
        return [str(value)]
    return " ".join(flatten(item.content)).casefold()


@dataclass(slots=True)
class KnowledgeRetrievalEngine:
    """I9 exact/structured/lexical retrieval over sources and canonical indexes."""

    service: KnowledgeService = field(default_factory=KnowledgeService)
    max_candidates: int = 10

    def __post_init__(self) -> None:
        if self.max_candidates <= 0:
            raise ValueError("max_candidates must be positive")

    def retrieve(self, need: KnowledgeNeed, *, indexes: Sequence[Any] = (),
                 packs: Sequence[Any] = (), offline: bool = False) -> RankedKnowledgeRetrievalResult:
        legacy = self.service.resolve(need, offline=offline)
        records: list[KnowledgeRecord] = []
        for index in indexes:
            if not index.verify():
                continue
            records.extend(self._indexed_records(index, need))
        for pack in packs:
            if bool(getattr(pack, "can_serve", False)):
                records.extend(pack.records)

        raw: list[KnowledgeItem] = list(legacy.items)
        raw.extend(_record_as_item(record) for record in records)
        dedup: dict[str, KnowledgeItem] = {}
        rejected: list[tuple[str, str]] = []
        ranked: list[KnowledgeRetrievalCandidate] = []
        query = need.query.strip().casefold()
        query_tokens = set(_LEXICAL_TOKEN.findall(query))
        for item in raw:
            identity = str(item.metadata.get("record_identity", item.id))
            compatibility = _environment_compatibility(item, need)
            if compatibility != CompatibilityStatus.COMPATIBLE:
                rejected.append((item.id, compatibility.value))
                continue
            if identity in dedup:
                continue
            dedup[identity] = item
            match_class, relevance = self._match(item, need, query, query_tokens)
            if match_class is None:
                continue
            authority = _AUTHORITY_SCORE[item.authority]
            specificity = int(item.metadata.get("specificity", 0))
            ranked.append(KnowledgeRetrievalCandidate(
                item=item, match_class=match_class, compatibility=compatibility,
                authority_score=authority, specificity_score=specificity,
                relevance_score=relevance,
                rank_reason=f"{match_class.value}:authority={authority};specificity={specificity};relevance={relevance}",
            ))

        conflicts = self._find_conflicts(ranked)
        conflict_map = {candidate_id for conflict in conflicts for candidate_id in conflict.candidate_ids}
        if conflict_map:
            ranked = [replace(candidate, conflict_ids=next(
                (conflict.candidate_ids for conflict in conflicts
                 if candidate.record_id in conflict.candidate_ids), ()
            )) if candidate.record_id in conflict_map else candidate for candidate in ranked]
        ranked.sort(key=lambda candidate: (
            -self._match_priority(candidate.match_class),
            -candidate.authority_score,
            -candidate.specificity_score,
            -candidate.relevance_score,
            candidate.record_id,
        ))
        candidates = tuple(ranked[:self.max_candidates])
        status = KnowledgeRetrievalStatus.SUCCESS if candidates else legacy.status
        return RankedKnowledgeRetrievalResult(status=status, need=need,
            candidates=candidates, rejected=tuple(rejected), conflicts=tuple(conflicts),
            source_results=legacy.source_results,
            degraded=bool(rejected or any(result.status != KnowledgeRetrievalStatus.SUCCESS
                                          for result in legacy.source_results)), offline=offline)

    @staticmethod
    def _indexed_records(index: Any, need: KnowledgeNeed) -> tuple[KnowledgeRecord, ...]:
        """Use I8 query paths; index results remain canonical-record backed."""
        found: dict[str, KnowledgeRecord] = {}
        query = need.query.strip()
        exact = index.lookup_record(query)
        if exact is not None:
            found[exact.record_id] = exact
        for record in index.lookup_by_type(need.type):
            found[record.record_id] = record
        for record in index.lookup_by_capability(query):
            found[record.record_id] = record
        for record in index.lookup_by_symbol(query):
            found[record.record_id] = record
        for record in index.lookup_by_api(query):
            found[record.record_id] = record
        for record in index.lexical_search(query):
            found[record.record_id] = record
        return tuple(found.values())

    @staticmethod
    def _match(item: KnowledgeItem, need: KnowledgeNeed, query: str,
               query_tokens: set[str]) -> tuple[RetrievalMatchClass | None, int]:
        metadata = item.metadata
        structured_values = {str(metadata.get("capability", "")).casefold(),
                             str(metadata.get("record_kind", "")).casefold(),
                             item.provenance.source_id.casefold()}
        if query in {item.id.casefold(), str(metadata.get("record_id", "")).casefold(),
                     str(metadata.get("capability", "")).casefold()}:
            return RetrievalMatchClass.EXACT, 3
        if query in structured_values or need.type.value.casefold() == str(metadata.get("record_kind", "")).casefold():
            return RetrievalMatchClass.STRUCTURED, 2
        content_tokens = set(_LEXICAL_TOKEN.findall(_content_text(item)))
        overlap = len(query_tokens & content_tokens)
        return (RetrievalMatchClass.LEXICAL, overlap) if overlap else (None, 0)

    @staticmethod
    def _match_priority(match_class: RetrievalMatchClass) -> int:
        return {RetrievalMatchClass.EXACT: 3, RetrievalMatchClass.STRUCTURED: 2,
                RetrievalMatchClass.LEXICAL: 1}[match_class]

    @staticmethod
    def _find_conflicts(candidates: Sequence[KnowledgeRetrievalCandidate]) -> tuple[KnowledgeRetrievalConflict, ...]:
        groups: dict[str, list[KnowledgeRetrievalCandidate]] = {}
        for candidate in candidates:
            content = candidate.item.content
            key = str(candidate.item.metadata.get("capability") or "")
            if not key and isinstance(content, Mapping):
                key = str(content.get("qualified_name") or content.get("symbol") or "")
            if key:
                groups.setdefault(key.casefold(), []).append(candidate)
        conflicts: list[KnowledgeRetrievalConflict] = []
        for key, group in groups.items():
            fingerprints = {_stable_json(candidate.item.content) for candidate in group}
            if len(fingerprints) > 1:
                conflicts.append(KnowledgeRetrievalConflict(
                    key=key, candidate_ids=tuple(sorted(candidate.record_id for candidate in group)),
                    provenance=tuple(candidate.provenance for candidate in group),
                    reason="materially contradictory compatible records; no merge",
                ))
        return tuple(conflicts)
