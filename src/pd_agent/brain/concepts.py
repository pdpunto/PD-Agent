"""Curated Fabric concept and pattern source for the v0.7 Brain."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from .canonical import KnowledgePack, KnowledgePackManifest, KnowledgePolicy, KnowledgeRecord, canonical_json
from .models import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeRetrievalStatus,
    KnowledgeSourceResult,
    KnowledgeType,
    SourceAuthority,
)


_TARGET_ENVIRONMENT = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
)


@dataclass(frozen=True, slots=True)
class CuratedConcept:
    key: str
    kind: KnowledgeType
    title: str
    capability: str
    summary: str
    workflow: tuple[str, ...]
    api_relations: tuple[str, ...]
    locator: str


_CATALOG: tuple[CuratedConcept, ...] = (
    CuratedConcept("registry.item", KnowledgeType.CONCEPT, "Item registry", "registries", "Registries provide stable identifiers for game objects and must be populated during mod initialization.", ("declare the identifier", "register the object in the appropriate registry", "use the registered identifier in data and runtime code"), ("fabric.registry",), "https://fabricmc.net/wiki/tutorial:registry"),
    CuratedConcept("registry.block", KnowledgeType.PATTERN, "Block registration", "blocks", "A block and its item representation are registered as related but distinct game objects.", ("create the block settings", "register the block", "register a block item when it should be obtainable as an item"), ("fabric.registry",), "https://fabricmc.net/wiki/tutorial:block"),
    CuratedConcept("data_component.state", KnowledgeType.CONCEPT, "Data component state", "data_components", "Data components attach typed, persistent state to item stacks without relying on ad-hoc NBT conventions.", ("define the component type", "register the component", "read and update it through the item stack component API"), ("fabric.item",), "https://docs.fabricmc.net/develop/items/custom-data-components"),
    CuratedConcept("block_entity.persistence", KnowledgeType.PATTERN, "Block entity persistence", "block_entities", "A block entity owns state associated with a block position and participates in the world save lifecycle.", ("create the block entity type", "read and write its persistent state", "mark changed state so the world can save it"), ("fabric.block_entity",), "https://docs.fabricmc.net/develop/blocks/block-entities"),
    CuratedConcept("inventory.container", KnowledgeType.PATTERN, "Inventory container", "inventories", "An inventory exposes bounded slot operations and should keep its mutation and serialization rules together.", ("define slot capacity", "validate insert and extract operations", "serialize the inventory state with its owning object"), ("fabric.transfer",), "https://docs.fabricmc.net/develop/items/transfer-api"),
    CuratedConcept("persistence.world", KnowledgeType.CONCEPT, "World persistence", "persistence", "Persistent world state is tied to the world lifecycle and must be restored before the first observation that depends on it.", ("choose a stable state key", "save at the lifecycle boundary", "restore before serving dependent behavior"), ("fabric.lifecycle",), "https://docs.fabricmc.net/develop/events"),
    CuratedConcept("command.registration", KnowledgeType.PATTERN, "Command registration", "commands", "Commands are registered through the command registration callback and should validate arguments before changing state.", ("register during command registration", "parse and validate arguments", "perform a bounded server-side action"), ("fabric.command",), "https://docs.fabricmc.net/develop/commands/basics"),
    CuratedConcept("event.callback", KnowledgeType.CONCEPT, "Event callback", "events", "Events provide typed lifecycle or interaction callbacks; handlers should remain bounded and respect the callback contract.", ("select the lifecycle event", "register a callback", "perform only the documented side effect"), ("fabric.events",), "https://docs.fabricmc.net/develop/events"),
    CuratedConcept("tag.membership", KnowledgeType.PATTERN, "Tag membership", "tags", "Tags are data-driven groups of registry entries and should be consumed through the tag API rather than copied lists.", ("define the tag resource", "add identifiers to the tag", "query membership through the registry tag"), ("fabric.tags",), "https://docs.fabricmc.net/develop/items/tags"),
    CuratedConcept("recipe.data_driven", KnowledgeType.CONCEPT, "Data-driven recipe", "recipes", "Recipes are data resources interpreted by the recipe manager, keeping content definitions separate from Java registration.", ("define the recipe resource", "use valid ingredient and result identifiers", "let the recipe manager load the resource"), ("fabric.recipe",), "https://docs.fabricmc.net/develop/items/recipes"),
    CuratedConcept("loot.data_driven", KnowledgeType.CONCEPT, "Data-driven loot", "loot", "Loot tables describe deterministic result generation from a context and seed, rather than hard-coding a drop in the caller.", ("define the loot table resource", "provide the correct loot context", "generate results through the loot table API"), ("fabric.loot",), "https://docs.fabricmc.net/develop/blocks/loot-tables"),
)


class FabricConceptPatternKnowledgeSource:
    """Small official-reference catalog with pinned, conservative provenance."""

    source_id = "fabric-docs:concept-pattern"
    source_kind = "fabric-official-reference"
    artifact_version = "1.21.11-curated-1"
    artifact_coordinate = "fabric-docs:1.21.11-curated-1"
    artifact_url = "https://docs.fabricmc.net/"

    def __init__(self, *, catalog: tuple[CuratedConcept, ...] = _CATALOG) -> None:
        self.catalog = tuple(catalog)
        self.artifact_checksum = hashlib.sha256(
            canonical_json([asdict(item) for item in self.catalog]).encode("utf-8")
        ).hexdigest()
        self._records: tuple[KnowledgeRecord, ...] | None = None

    def supports(self, need: KnowledgeNeed) -> bool:
        return need.type in {KnowledgeType.CONCEPT, KnowledgeType.PATTERN}

    def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
        if environment.minecraft_version is None or environment.fabric_api_version is None or environment.loader_version is None:
            return CompatibilityStatus.UNKNOWN
        if environment.minecraft_version != _TARGET_ENVIRONMENT.minecraft_version:
            return CompatibilityStatus.INCOMPATIBLE
        if environment.fabric_api_version != _TARGET_ENVIRONMENT.fabric_api_version or environment.loader_version != _TARGET_ENVIRONMENT.loader_version:
            return CompatibilityStatus.INCOMPATIBLE
        if environment.mappings_namespace is None or environment.mappings_version is None:
            return CompatibilityStatus.UNKNOWN
        if environment.mappings_namespace != _TARGET_ENVIRONMENT.mappings_namespace or environment.mappings_version != _TARGET_ENVIRONMENT.mappings_version:
            return CompatibilityStatus.INCOMPATIBLE
        return CompatibilityStatus.COMPATIBLE

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeSourceResult:
        if not self.supports(need):
            return self._result(need, KnowledgeRetrievalStatus.UNSUPPORTED_NEED, "unsupported concept source need")
        compatibility = self.compatibility(need.environment)
        if compatibility != CompatibilityStatus.COMPATIBLE:
            status = KnowledgeRetrievalStatus.VERSION_MISMATCH if compatibility == CompatibilityStatus.INCOMPATIBLE else KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE
            return self._result(need, status, f"concept source environment is {compatibility.value}")
        records = self.materialize_records(need.environment)
        terms = tuple(term.casefold() for term in need.query.split() if term)
        matches = tuple(record for record in records if all(term in canonical_json(record.content).casefold() for term in terms))
        if not matches:
            return self._result(need, KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE, "no curated concept or pattern matched")
        provenance = self._provenance()
        items = tuple(KnowledgeItem(record.record_id, record.content, need.environment, record.authority, provenance, {"record_identity": record.identity(), "capability": record.content["capability"]}) for record in matches)
        return KnowledgeSourceResult(KnowledgeRetrievalStatus.SUCCESS, self.source_id, self.source_kind, need, items=items, provenance=(provenance,))

    def materialize_records(self, environment: KnowledgeEnvironment | None = None) -> tuple[KnowledgeRecord, ...]:
        target = environment or _TARGET_ENVIRONMENT
        if self.compatibility(target) != CompatibilityStatus.COMPATIBLE:
            raise ValueError("concept materialization requires compatible environment")
        if self._records is not None:
            return self._records
        provenance = self._provenance()
        records = []
        for item in self.catalog:
            content = {
                "key": item.key, "title": item.title, "capability": item.capability,
                "summary": item.summary, "workflow": list(item.workflow),
                "related_api": list(item.api_relations), "source_revision": self.artifact_version,
            }
            content_checksum = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
            record_id = "fabric-concept:" + hashlib.sha256(canonical_json({"catalog": self.artifact_checksum, "key": item.key}).encode("utf-8")).hexdigest()
            records.append(KnowledgeRecord(record_id, item.kind, content, target, provenance, SourceAuthority.OFFICIAL_DOCUMENTATION, True, item.capability, item.api_relations, (), KnowledgePolicy.FETCH_CACHE_REFERENCE_ONLY, {"algorithm": "sha256", "value": content_checksum}, self.artifact_version))
        if not records:
            raise ValueError("curated concept catalog is empty")
        self._records = tuple(records)
        return self._records

    def materialize_pack(self, environment: KnowledgeEnvironment | None = None) -> KnowledgePack:
        target = environment or _TARGET_ENVIRONMENT
        records = self.materialize_records(target)
        inventory = tuple({"record_id": record.record_id, "record_identity": record.identity()} for record in records)
        manifest = KnowledgePackManifest(target, ({"source_id": self.source_id, "source_kind": self.source_kind, "revision": self.artifact_version, "locator": self.artifact_url, "checksum_algorithm": "sha256", "checksum": self.artifact_checksum, "authority": SourceAuthority.OFFICIAL_DOCUMENTATION.value, "license_policy": KnowledgePolicy.FETCH_CACHE_REFERENCE_ONLY.value},), inventory, license_policy=KnowledgePolicy.FETCH_CACHE_REFERENCE_ONLY)
        return KnowledgePack(manifest, records)

    def _provenance(self) -> KnowledgeProvenance:
        return KnowledgeProvenance(self.source_id, self.source_kind, self.artifact_url, self.artifact_version, self.artifact_version, None, "sha256", self.artifact_checksum, "Fabric documentation license; reference-only")

    def _result(self, need: KnowledgeNeed, status: KnowledgeRetrievalStatus, error: str) -> KnowledgeSourceResult:
        return KnowledgeSourceResult(status, self.source_id, self.source_kind, need, error=error)
