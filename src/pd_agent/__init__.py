"""PD Agent foundation package."""

from __future__ import annotations

__version__ = "0.1.0"

from .cli import main
from .artifacts import ArtifactClassification, ArtifactValidator
from .context import ContextBundle, ContextItem, ContextManager, ContextRequest, ExternalContextSource, ProjectContextSource, RunContextSource
from .config import AppConfig, load_config
from .build import GradleBuildRunner
from .brain import (
    CompatibilityStatus,
    EnvironmentDetectionStatus,
    KnowledgeEnvironment,
    KnowledgeEnvironmentResolution,
    KnowledgeEnvironmentResolver,
    KnowledgeNeed,
    KnowledgeType,
)
from .minecraft import (
    MinecraftEvidencePaths,
    MinecraftLaunchPlan,
    MinecraftProcessEvidence,
    MinecraftRuntimeEvidence,
    MinecraftTargetMetadata,
    MinecraftTestError,
    MinecraftTestResult,
    MinecraftTestRunner,
    MinecraftTestSpec,
    MinecraftTestStatus,
    MinecraftTestValidationError,
    UnsupportedMinecraftEnvironmentError,
)
from .logging import configure_logging
from .project import ProjectInspector, ProjectInspectionStatus, ProjectSnapshot
from .runtime import AgentRuntime, RunController
from .core import ProviderContinuation

__all__ = [
    "__version__",
    "AppConfig",
    "ArtifactClassification",
    "ArtifactValidator",
    "ContextBundle",
    "ContextItem",
    "ContextManager",
    "ContextRequest",
    "CompatibilityStatus",
    "ExternalContextSource",
    "EnvironmentDetectionStatus",
    "GradleBuildRunner",
    "KnowledgeEnvironment",
    "KnowledgeEnvironmentResolution",
    "KnowledgeEnvironmentResolver",
    "KnowledgeNeed",
    "KnowledgeType",
    "MinecraftEvidencePaths",
    "MinecraftLaunchPlan",
    "MinecraftProcessEvidence",
    "MinecraftRuntimeEvidence",
    "MinecraftTargetMetadata",
    "MinecraftTestError",
    "MinecraftTestResult",
    "MinecraftTestRunner",
    "MinecraftTestSpec",
    "MinecraftTestStatus",
    "MinecraftTestValidationError",
    "UnsupportedMinecraftEnvironmentError",
    "ProjectInspector",
    "ProjectInspectionStatus",
    "ProjectSnapshot",
    "AgentRuntime",
    "ProjectContextSource",
    "ProviderContinuation",
    "configure_logging",
    "load_config",
    "main",
    "RunController",
    "RunContextSource",
]
