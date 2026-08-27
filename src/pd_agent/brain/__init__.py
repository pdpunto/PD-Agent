"""Minecraft Brain domain and environment detection."""

from __future__ import annotations

from .models import (
    CompatibilityStatus,
    EnvironmentDetectionStatus,
    KnowledgeEnvironment,
    KnowledgeEnvironmentResolution,
    KnowledgeNeed,
    KnowledgeItem,
    KnowledgeProvenance,
    KnowledgeRetrievalResult,
    KnowledgeRetrievalStatus,
    KnowledgeSourceResult,
    KnowledgeType,
    SourceAuthority,
)
from .retrieval import FileKnowledgeCache, KnowledgeService, KnowledgeSource, MinecraftBrain
from .resolver import KnowledgeEnvironmentResolver
from .yarn import YarnKnowledgeSource
from .fabric_api import FabricApiKnowledgeSource
from .concepts import CuratedConcept, FabricConceptPatternKnowledgeSource
from .indexes import INDEX_SCHEMA_VERSION, KnowledgeIndexError, KnowledgeIndexMetadata, KnowledgePackIndex
from .canonical import (
    KnowledgePack,
    KnowledgePackIntegrityError,
    KnowledgePackManifest,
    KnowledgePackState,
    KnowledgePackStore,
    KnowledgePackVerification,
    KnowledgePolicy,
    KnowledgeRecord,
    normalize_logical_path,
)

__all__ = [
    "CompatibilityStatus",
    "FileKnowledgeCache",
    "EnvironmentDetectionStatus",
    "KnowledgeEnvironment",
    "KnowledgeEnvironmentResolution",
    "KnowledgeEnvironmentResolver",
    "KnowledgeNeed",
    "KnowledgeItem",
    "KnowledgeProvenance",
    "KnowledgeRetrievalResult",
    "KnowledgeRetrievalStatus",
    "KnowledgeSource",
    "KnowledgeService",
    "KnowledgeSourceResult",
    "KnowledgeType",
    "MinecraftBrain",
    "SourceAuthority",
    "YarnKnowledgeSource",
    "FabricApiKnowledgeSource",
    "CuratedConcept",
    "FabricConceptPatternKnowledgeSource",
    "INDEX_SCHEMA_VERSION",
    "KnowledgeIndexError",
    "KnowledgeIndexMetadata",
    "KnowledgePackIndex",
    "KnowledgePackManifest",
    "KnowledgePack",
    "KnowledgePackIntegrityError",
    "KnowledgePackState",
    "KnowledgePackStore",
    "KnowledgePackVerification",
    "KnowledgePolicy",
    "KnowledgeRecord",
    "normalize_logical_path",
]
