"""Deterministic knowledge retrieval and cache for Minecraft Brain L2."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
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
