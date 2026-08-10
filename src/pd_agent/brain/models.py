"""Brain domain models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class EnvironmentDetectionStatus(StrEnum):
    """Outcome of environment detection."""

    DETECTED = "DETECTED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


class CompatibilityStatus(StrEnum):
    """Compatibility of a knowledge item against a need/environment."""

    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


class SourceAuthority(StrEnum):
    """Knowledge authority tiers."""

    AUTHORITATIVE_ARTIFACT = "AUTHORITATIVE_ARTIFACT"
    AUTHORITATIVE_SOURCE = "AUTHORITATIVE_SOURCE"
    OFFICIAL_DOCUMENTATION = "OFFICIAL_DOCUMENTATION"
    SECONDARY = "SECONDARY"


class KnowledgeType(StrEnum):
    """Supported knowledge categories for v0.3 L1."""

    SYMBOL = "SYMBOL"
    API = "API"
    MAPPING = "MAPPING"
    BUILD = "BUILD"
    CONCEPT = "CONCEPT"
    MIGRATION = "MIGRATION"


class KnowledgeRetrievalStatus(StrEnum):
    """Outcome of a knowledge retrieval attempt."""

    SUCCESS = "SUCCESS"
    UNSUPPORTED_NEED = "UNSUPPORTED_NEED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_ERROR = "SOURCE_ERROR"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    CACHE_ERROR = "CACHE_ERROR"
    OFFLINE_MISS = "OFFLINE_MISS"
    NO_COMPATIBLE_KNOWLEDGE = "NO_COMPATIBLE_KNOWLEDGE"


def _json_ready(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_ready(value.to_dict())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class KnowledgeEnvironment:
    """Versioned Minecraft/Fabric environment."""

    minecraft_version: str | None = None
    loader_version: str | None = None
    loom_version: str | None = None
    mappings_namespace: str | None = None
    mappings_version: str | None = None
    fabric_api_version: str | None = None
    java_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "minecraft_version": self.minecraft_version,
            "loader_version": self.loader_version,
            "loom_version": self.loom_version,
            "mappings_namespace": self.mappings_namespace,
            "mappings_version": self.mappings_version,
            "fabric_api_version": self.fabric_api_version,
            "java_version": self.java_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeEnvironment":
        return cls(
            minecraft_version=data.get("minecraft_version"),
            loader_version=data.get("loader_version"),
            loom_version=data.get("loom_version"),
            mappings_namespace=data.get("mappings_namespace"),
            mappings_version=data.get("mappings_version"),
            fabric_api_version=data.get("fabric_api_version"),
            java_version=data.get("java_version"),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeNeed:
    """Concrete knowledge request."""

    id: str
    type: KnowledgeType
    query: str
    environment: KnowledgeEnvironment
    hints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.type, KnowledgeType):
            raise TypeError("type must be a KnowledgeType")
        if not isinstance(self.environment, KnowledgeEnvironment):
            raise TypeError("environment must be a KnowledgeEnvironment")
        if not self.id or not self.id.strip():
            raise ValueError("id must not be empty")
        if not self.query or not self.query.strip():
            raise ValueError("query must not be empty")
        if not isinstance(self.hints, tuple):
            object.__setattr__(self, "hints", tuple(self.hints))
        if any(not isinstance(item, str) for item in self.hints):
            raise TypeError("hints must contain strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "query": self.query,
            "environment": self.environment.to_dict(),
            "hints": list(self.hints),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeNeed":
        return cls(
            id=str(data["id"]),
            type=KnowledgeType(str(data["type"])),
            query=str(data["query"]),
            environment=KnowledgeEnvironment.from_dict(dict(data["environment"])),
            hints=tuple(str(item) for item in data.get("hints", [])),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeEnvironmentResolution:
    """Resolved environment plus detection evidence."""

    status: EnvironmentDetectionStatus
    environment: KnowledgeEnvironment
    evidence: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "environment": self.environment.to_dict(),
            "evidence": list(self.evidence),
            "conflicts": list(self.conflicts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeEnvironmentResolution":
        return cls(
            status=EnvironmentDetectionStatus(str(data["status"])),
            environment=KnowledgeEnvironment.from_dict(dict(data["environment"])),
            evidence=tuple(str(item) for item in data.get("evidence", [])),
            conflicts=tuple(str(item) for item in data.get("conflicts", [])),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeProvenance:
    """Source provenance for knowledge retrieval."""

    source_id: str
    source_kind: str
    locator: str
    artifact_or_document_version: str | None = None
    revision: str | None = None
    retrieved_at: datetime | None = None
    checksum_algorithm: str | None = None
    checksum: str | None = None
    license_id_or_policy: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not self.source_kind.strip():
            raise ValueError("source_kind must not be empty")
        if not self.locator.strip():
            raise ValueError("locator must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "locator": self.locator,
            "artifact_or_document_version": self.artifact_or_document_version,
            "revision": self.revision,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "checksum_algorithm": self.checksum_algorithm,
            "checksum": self.checksum,
            "license_id_or_policy": self.license_id_or_policy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeProvenance":
        retrieved_at = data.get("retrieved_at")
        return cls(
            source_id=str(data["source_id"]),
            source_kind=str(data["source_kind"]),
            locator=str(data["locator"]),
            artifact_or_document_version=data.get("artifact_or_document_version"),
            revision=data.get("revision"),
            retrieved_at=datetime.fromisoformat(retrieved_at) if retrieved_at else None,
            checksum_algorithm=data.get("checksum_algorithm"),
            checksum=data.get("checksum"),
            license_id_or_policy=data.get("license_id_or_policy"),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    """Single retrieved fragment of knowledge."""

    id: str
    content: Any
    environment: KnowledgeEnvironment
    authority: SourceAuthority
    provenance: KnowledgeProvenance
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": _json_ready(self.content),
            "environment": self.environment.to_dict(),
            "authority": self.authority.value,
            "provenance": self.provenance.to_dict(),
            "metadata": _json_ready(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeItem":
        return cls(
            id=str(data["id"]),
            content=data.get("content"),
            environment=KnowledgeEnvironment.from_dict(dict(data["environment"])),
            authority=SourceAuthority(str(data["authority"])),
            provenance=KnowledgeProvenance.from_dict(dict(data["provenance"])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeSourceResult:
    """Result returned by a source adapter."""

    status: KnowledgeRetrievalStatus
    source_id: str
    source_kind: str
    need: KnowledgeNeed
    items: tuple[KnowledgeItem, ...] = ()
    provenance: tuple[KnowledgeProvenance, ...] = ()
    error: str | None = None
    cache_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "need": self.need.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "provenance": [item.to_dict() for item in self.provenance],
            "error": self.error,
            "cache_key": self.cache_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeSourceResult":
        return cls(
            status=KnowledgeRetrievalStatus(str(data["status"])),
            source_id=str(data["source_id"]),
            source_kind=str(data["source_kind"]),
            need=KnowledgeNeed.from_dict(dict(data["need"])),
            items=tuple(KnowledgeItem.from_dict(item) for item in data.get("items", [])),
            provenance=tuple(
                KnowledgeProvenance.from_dict(item) for item in data.get("provenance", [])
            ),
            error=data.get("error"),
            cache_key=data.get("cache_key"),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalResult:
    """Final retrieval result returned by the Brain."""

    status: KnowledgeRetrievalStatus
    need: KnowledgeNeed
    items: tuple[KnowledgeItem, ...] = ()
    source_results: tuple[KnowledgeSourceResult, ...] = ()
    cache_hit: bool = False
    offline: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "need": self.need.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "source_results": [item.to_dict() for item in self.source_results],
            "cache_hit": self.cache_hit,
            "offline": self.offline,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeRetrievalResult":
        return cls(
            status=KnowledgeRetrievalStatus(str(data["status"])),
            need=KnowledgeNeed.from_dict(dict(data["need"])),
            items=tuple(KnowledgeItem.from_dict(item) for item in data.get("items", [])),
            source_results=tuple(
                KnowledgeSourceResult.from_dict(item)
                for item in data.get("source_results", [])
            ),
            cache_hit=bool(data.get("cache_hit", False)),
            offline=bool(data.get("offline", False)),
            error=data.get("error"),
        )
