"""Frozen multi-source knowledge pack materialization and runtime source."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .canonical import KnowledgePack, KnowledgePackState, KnowledgePackStore, KnowledgeRecord
from .models import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeRetrievalStatus,
    KnowledgeSourceResult,
)


FROZEN_PACK_REVISION = "v0.7-i16-1"
EXPECTED_FROZEN_SOURCE_IDS = frozenset({
    "net.fabricmc:yarn",
    "net.fabricmc.fabric-api:fabric-api",
    "fabric-docs:concept-pattern",
})
_TOKEN = re.compile(r"[A-Za-z0-9_:.+-]+")


def _environment_matches(expected: KnowledgeEnvironment, actual: KnowledgeEnvironment) -> bool:
    return all(
        getattr(expected, field) is None or getattr(expected, field) == getattr(actual, field)
        for field in (
            "minecraft_version", "loader_version", "loom_version", "mappings_namespace",
            "mappings_version", "fabric_api_version", "java_version",
        )
    )


def compose_frozen_knowledge_pack(
    packs: Sequence[KnowledgePack], *, environment: KnowledgeEnvironment
) -> KnowledgePack:
    """Compose exactly the approved three source families into one frozen pack."""

    if len(packs) != 3:
        raise ValueError("I16 frozen pack requires exactly three source packs")
    if any(pack.manifest.state not in {KnowledgePackState.VERIFIED, KnowledgePackState.FROZEN} for pack in packs):
        raise ValueError("all source packs must be verified or frozen before composition")
    source_ids = {str(source.get("source_id")) for pack in packs for source in pack.manifest.source_set}
    if source_ids != EXPECTED_FROZEN_SOURCE_IDS:
        raise ValueError("frozen pack source set must contain Yarn, Fabric API and Concept/Pattern")
    records = tuple(record for pack in packs for record in pack.records)
    if any(not _environment_matches(environment, record.environment) for record in records):
        raise ValueError("frozen pack record environment mismatch")
    if len({_record_source_id(record) for record in records}) != 3:
        raise ValueError("frozen pack records must contain all three source families")
    if len({record.record_id for record in records}) != len(records):
        raise ValueError("frozen pack contains duplicate record ids")
    inventory = tuple({"record_id": record.record_id, "record_identity": record.identity()} for record in records)
    manifest = packs[0].manifest.__class__(
        environment=environment,
        source_set=tuple(source for pack in packs for source in pack.manifest.source_set),
        record_inventory=inventory,
        generated_metadata={"composition_revision": FROZEN_PACK_REVISION},
    )
    return KnowledgePack(manifest, records).transition_to(KnowledgePackState.VERIFIED).freeze()


def materialize_frozen_knowledge_pack(
    sources: Sequence[Any], *, environment: KnowledgeEnvironment, target: str | Path | None = None
) -> KnowledgePack:
    """Materialize, verify, freeze and optionally persist approved source packs."""

    pack = compose_frozen_knowledge_pack(
        tuple(source.materialize_pack(environment) for source in sources), environment=environment
    )
    if target is not None:
        KnowledgePackStore.write(pack, target)
    return pack


def load_frozen_knowledge_pack(path: str | Path, *, expected_pack_id: str | None = None) -> KnowledgePack:
    pack = KnowledgePackStore.read(path)
    if pack.manifest.state != KnowledgePackState.FROZEN:
        raise ValueError("I16 runtime requires a FROZEN knowledge pack")
    if expected_pack_id is not None and pack.manifest.pack_id != expected_pack_id:
        raise ValueError("frozen knowledge pack identity mismatch")
    if {str(source.get("source_id")) for source in pack.manifest.source_set} != EXPECTED_FROZEN_SOURCE_IDS:
        raise ValueError("frozen knowledge pack source set is incomplete")
    return pack


@dataclass(frozen=True, slots=True)
class FrozenKnowledgePackSource:
    """KnowledgeService adapter backed only by a verified frozen pack."""

    pack: KnowledgePack
    source_id: str = "pd-agent:frozen-i16-pack"
    source_kind: str = "frozen-knowledge-pack"
    artifact_version: str = FROZEN_PACK_REVISION

    def __post_init__(self) -> None:
        self.pack.assert_servable()

    @property
    def artifact_checksum(self) -> str:
        return self.pack.manifest.pack_id or ""

    def supports(self, need: KnowledgeNeed) -> bool:
        return any(self._record_matches_need(record, need) for record in self.pack.records)

    def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
        return CompatibilityStatus.COMPATIBLE if _environment_matches(self.pack.manifest.environment, environment) else CompatibilityStatus.INCOMPATIBLE

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeSourceResult:
        if self.compatibility(need.environment) != CompatibilityStatus.COMPATIBLE:
            return KnowledgeSourceResult(KnowledgeRetrievalStatus.VERSION_MISMATCH, self.source_id, self.source_kind, need, error="frozen pack environment mismatch")
        candidates = [record for record in self.pack.records if self._record_matches_need(record, need)]
        if not candidates:
            return KnowledgeSourceResult(KnowledgeRetrievalStatus.UNSUPPORTED_NEED, self.source_id, self.source_kind, need, error="frozen pack has no compatible source family")
        terms = {term.casefold() for term in _TOKEN.findall(need.query)}
        candidates.sort(key=lambda record: (-len(terms & self._record_terms(record)), record.record_id))
        items = tuple(self._item(record, need) for record in candidates[:10])
        return KnowledgeSourceResult(KnowledgeRetrievalStatus.SUCCESS, self.source_id, self.source_kind, need, items=items, provenance=tuple(item.provenance for item in items))

    @staticmethod
    def _record_terms(record: KnowledgeRecord) -> set[str]:
        return {term.casefold() for term in _TOKEN.findall(str(record.content))}

    @staticmethod
    def _record_matches_need(record: KnowledgeRecord, need: KnowledgeNeed) -> bool:
        if need.type.value in {"CONCEPT", "PATTERN"}:
            return record.kind.value == need.type.value
        if need.type.value in {"MAPPING", "SYMBOL", "API"}:
            return record.kind.value in {"SYMBOL", "API", "VERSION_CHANGE"}
        return record.kind.value == need.type.value

    def _item(self, record: KnowledgeRecord, need: KnowledgeNeed) -> KnowledgeItem:
        metadata = {
            "record_identity": record.identity(),
            "pack_id": self.pack.manifest.pack_id,
            "source_family": record.provenance.source_id,
        }
        return KnowledgeItem(record.record_id, record.content, need.environment, record.authority, record.provenance, metadata, record.version_sensitive)


def _record_source_id(record: KnowledgeRecord) -> str:
    return record.provenance.source_id
