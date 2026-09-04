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
from .retrieval import (
    FileKnowledgeCache,
    KnowledgeRetrievalCandidate,
    KnowledgeDegradedMode,
    KnowledgeRetrievalConflict,
    KnowledgeRetrievalEngine,
    KnowledgeService,
    KnowledgeSource,
    RankedKnowledgeRetrievalResult,
    RetrievalConflictStatus,
    RetrievalMatchClass,
    MinecraftBrain,
)
from .resolver import KnowledgeEnvironmentResolver
from .yarn import YarnKnowledgeSource
from .fabric_api import FabricApiKnowledgeSource
from .concepts import CuratedConcept, FabricConceptPatternKnowledgeSource
from .vertical_a import FabricVerticalAKnowledgeSource
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
from .precode import FirstEditTracker, PreCodeDerivation, PreCodeKnowledgeNeedDeriver, PreCodePhase
from .semantic_repair import SemanticRepairDerivation, SemanticRepairKnowledgeNeedDeriver
from .orchestration import BrainOrchestrationResult, BrainTrigger, FabricBrainOrchestrator
from .selection import (
    KnowledgeSourceSelection,
    knowledge_service_for_environment,
    select_knowledge_sources_for_environment,
    select_knowledge_sources_for_platform,
)
from .frozen import (
    EXPECTED_FROZEN_SOURCE_IDS,
    FROZEN_PACK_REVISION,
    FrozenKnowledgePackSource,
    compose_frozen_knowledge_pack,
    load_frozen_knowledge_pack,
    materialize_frozen_knowledge_pack,
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
    "KnowledgeRetrievalCandidate",
    "KnowledgeDegradedMode",
    "KnowledgeRetrievalConflict",
    "KnowledgeRetrievalEngine",
    "RankedKnowledgeRetrievalResult",
    "RetrievalConflictStatus",
    "RetrievalMatchClass",
    "KnowledgeSourceResult",
    "KnowledgeType",
    "MinecraftBrain",
    "SourceAuthority",
    "YarnKnowledgeSource",
    "FabricApiKnowledgeSource",
    "CuratedConcept",
    "FabricConceptPatternKnowledgeSource",
    "FabricVerticalAKnowledgeSource",
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
    "FirstEditTracker",
    "PreCodeDerivation",
    "PreCodeKnowledgeNeedDeriver",
    "PreCodePhase",
    "SemanticRepairDerivation",
    "SemanticRepairKnowledgeNeedDeriver",
    "BrainOrchestrationResult",
    "BrainTrigger",
    "FabricBrainOrchestrator",
    "KnowledgeSourceSelection",
    "knowledge_service_for_environment",
    "select_knowledge_sources_for_environment",
    "select_knowledge_sources_for_platform",
    "FROZEN_PACK_REVISION",
    "EXPECTED_FROZEN_SOURCE_IDS",
    "FrozenKnowledgePackSource",
    "compose_frozen_knowledge_pack",
    "load_frozen_knowledge_pack",
    "materialize_frozen_knowledge_pack",
]
