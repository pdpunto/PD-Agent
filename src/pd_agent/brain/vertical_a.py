"""Bounded, version-aware knowledge for the M3 Vertical A composition."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .canonical import canonical_json
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


_SUPPORTED_ENVIRONMENTS = (
    KnowledgeEnvironment(
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        loom_version="1.13.3",
        mappings_namespace="yarn",
        mappings_version="1.21.11+build.6",
        fabric_api_version="0.141.6+1.21.11",
        java_version="21",
    ),
    KnowledgeEnvironment(
        minecraft_version="26.2",
        loader_version="0.19.3",
        loom_version="1.17-SNAPSHOT",
        fabric_api_version="0.158.0+26.2",
        java_version="25",
    ),
)

_DOMAINS: tuple[tuple[str, str, KnowledgeType, str], ...] = (
    ("vertical_a_composition", "composition", KnowledgeType.CAPABILITY, "Block, BlockItem, minimal assets and recipe form one bounded composition."),
    ("block_registration", "block", KnowledgeType.API, "A block uses a stable namespace and identifier and is registered during initialization."),
    ("block_item", "block item", KnowledgeType.PATTERN, "A BlockItem is a distinct item registry entry associated with the intended Block."),
    ("blockstate_asset", "blockstate", KnowledgeType.PATTERN, "A blockstate resource maps the block identifier to a bounded block model reference."),
    ("block_model_asset", "block model", KnowledgeType.PATTERN, "A block model uses a bounded parent or texture reference for the block resource."),
    ("item_model_asset", "item model", KnowledgeType.PATTERN, "An item model references the associated BlockItem resource using the platform-valid form."),
    ("texture_reference", "texture", KnowledgeType.PATTERN, "REUSE, DERIVE and GENERATE are bounded asset strategies; REUSE needs a valid reference."),
    ("recipe_resource", "recipe", KnowledgeType.CONCEPT, "A recipe is a bounded data resource with namespace, ingredients, result and positive count."),
)


@dataclass(slots=True)
class FabricVerticalAKnowledgeSource:
    """Serve only generic Vertical A facts for explicitly supported environments."""

    source_id: str = "pd-agent:vertical-a-knowledge"
    source_kind: str = "m3-vertical-a-reference"
    artifact_version: str = "m3-vertical-a-1"
    artifact_url: str = "local://pd-agent/m3/vertical-a"
    artifact_checksum: str = field(init=False)

    def __post_init__(self) -> None:
        self.artifact_checksum = hashlib.sha256(canonical_json(_DOMAINS).encode("utf-8")).hexdigest()

    @property
    def version_sensitive(self) -> bool:
        return True

    def supports(self, need: KnowledgeNeed) -> bool:
        return need.type in {KnowledgeType.API, KnowledgeType.PATTERN, KnowledgeType.CONCEPT, KnowledgeType.CAPABILITY}

    def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
        return CompatibilityStatus.COMPATIBLE if environment in _SUPPORTED_ENVIRONMENTS else CompatibilityStatus.INCOMPATIBLE

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeSourceResult:
        if not self.supports(need):
            return self._result(need, KnowledgeRetrievalStatus.UNSUPPORTED_NEED, "unsupported Vertical A need type")
        if self.compatibility(need.environment) is not CompatibilityStatus.COMPATIBLE:
            return self._result(need, KnowledgeRetrievalStatus.VERSION_MISMATCH, "Vertical A environment is incompatible")
        domain = next((item for item in _DOMAINS if item[0] == need.query.casefold()), None)
        if domain is None:
            return self._result(need, KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE, "no Vertical A domain matched")
        key, subject, kind, summary = domain
        content: dict[str, Any] = {
            "domain": key,
            "subject": subject,
            "kind": kind.value,
            "summary": summary,
            "platform": need.environment.minecraft_version,
            "mappings_namespace": need.environment.mappings_namespace,
            "version_sensitive": True,
        }
        provenance = KnowledgeProvenance(
            source_id=self.source_id,
            source_kind=self.source_kind,
            locator=self.artifact_url,
            artifact_or_document_version=self.artifact_version,
            revision=self.artifact_version,
            checksum_algorithm="sha256",
            checksum=self.artifact_checksum,
            license_id_or_policy="project-bounded-reference",
            retrieved_at=datetime.now(timezone.utc),
        )
        item = KnowledgeItem(
            id=f"vertical-a:{key}",
            content=content,
            environment=need.environment,
            authority=SourceAuthority.AUTHORITATIVE_SOURCE,
            provenance=provenance,
            metadata={"record_identity": hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest(), "capability": "vertical_a"},
            version_sensitive=True,
        )
        return KnowledgeSourceResult(
            status=KnowledgeRetrievalStatus.SUCCESS,
            source_id=self.source_id,
            source_kind=self.source_kind,
            need=need,
            items=(item,),
            provenance=(provenance,),
        )

    def _result(self, need: KnowledgeNeed, status: KnowledgeRetrievalStatus, error: str) -> KnowledgeSourceResult:
        return KnowledgeSourceResult(status, self.source_id, self.source_kind, need, error=error)


__all__ = ["FabricVerticalAKnowledgeSource"]
