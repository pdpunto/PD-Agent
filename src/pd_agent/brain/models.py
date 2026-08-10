"""Brain domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
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


class KnowledgeType(StrEnum):
    """Supported knowledge categories for v0.3 L1."""

    SYMBOL = "SYMBOL"
    API = "API"
    MAPPING = "MAPPING"
    BUILD = "BUILD"
    CONCEPT = "CONCEPT"
    MIGRATION = "MIGRATION"


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
