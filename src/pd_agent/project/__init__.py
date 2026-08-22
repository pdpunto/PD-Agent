"""Deterministic project inspection for PD Agent v0.1."""

from __future__ import annotations

from .git import GitBaseline, GitInspector
from .inspector import ProjectInspector
from .models import (
    DetectedValue,
    FabricDependencyMap,
    FabricManifest,
    GitDiffSnapshot,
    MixinConfig,
    ModuleSnapshot,
    ProjectInspectionStatus,
    ProjectSnapshot,
    WrapperSnapshot,
)
from .mutation_paths import MutationPathResolutionError, resolve_logical_resource_path

__all__ = [
    "DetectedValue",
    "FabricDependencyMap",
    "FabricManifest",
    "GitBaseline",
    "GitDiffSnapshot",
    "GitInspector",
    "MixinConfig",
    "ModuleSnapshot",
    "ProjectInspectionStatus",
    "ProjectInspector",
    "ProjectSnapshot",
    "WrapperSnapshot",
    "MutationPathResolutionError",
    "resolve_logical_resource_path",
]
