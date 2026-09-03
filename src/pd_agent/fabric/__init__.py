"""Normal product orchestration for Fabric workspaces."""

from .orchestration import FabricNormalOrchestrator, FabricOrchestrationResult, FabricOrchestrationStatus, NormalFabricOrchestrator
from .platform import (
    FabricMappingFamily,
    FabricPlatformEvidence,
    FabricPlatformEvidenceKind,
    FabricPlatformModelError,
    FabricPlatformObservation,
    FabricPlatformProfile,
    FabricPlatformResolution,
    FabricPlatformResolutionStatus,
    FabricPlatformSupportStatus,
    FabricSupportRegistry,
    load_platform_profiles,
    load_platform_registry,
)

__all__ = [
    "FabricNormalOrchestrator", "FabricOrchestrationResult", "FabricOrchestrationStatus", "NormalFabricOrchestrator",
    "FabricMappingFamily", "FabricPlatformEvidence", "FabricPlatformEvidenceKind", "FabricPlatformModelError",
    "FabricPlatformObservation", "FabricPlatformProfile", "FabricPlatformResolution", "FabricPlatformResolutionStatus",
    "FabricPlatformSupportStatus", "FabricSupportRegistry", "load_platform_profiles", "load_platform_registry",
]
