"""Project inspection models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class ProjectInspectionStatus(StrEnum):
    """Outcome of project inspection."""

    READY = "READY"
    BLOCKED = "BLOCKED"
    INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True, slots=True)
class DetectedValue:
    """Static value with provenance."""

    value: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source}


@dataclass(frozen=True, slots=True)
class GitDiffSnapshot:
    """Observed git diff output."""

    text: str
    truncated: bool = False
    line_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "truncated": self.truncated,
            "line_count": self.line_count,
        }


@dataclass(frozen=True, slots=True)
class GitBaseline:
    """Read-only git baseline."""

    present: bool
    repo_root: Path | None = None
    head: str | None = None
    branch: str | None = None
    status_porcelain: tuple[str, ...] = ()
    diff: GitDiffSnapshot | None = None
    cached_diff: GitDiffSnapshot | None = None
    working_tree_clean: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "repo_root": str(self.repo_root) if self.repo_root is not None else None,
            "head": self.head,
            "branch": self.branch,
            "status_porcelain": list(self.status_porcelain),
            "diff": self.diff.to_dict() if self.diff is not None else None,
            "cached_diff": self.cached_diff.to_dict()
            if self.cached_diff is not None
            else None,
            "working_tree_clean": self.working_tree_clean,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class WrapperSnapshot:
    """Gradle wrapper state."""

    present: bool
    scripts: tuple[Path, ...] = ()
    platform_hint: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "scripts": [str(path) for path in self.scripts],
            "platform_hint": self.platform_hint,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class FabricDependencyMap:
    """Fabric dependency buckets."""

    depends: Mapping[str, Any] = field(default_factory=dict)
    recommends: Mapping[str, Any] = field(default_factory=dict)
    suggests: Mapping[str, Any] = field(default_factory=dict)
    conflicts: Mapping[str, Any] = field(default_factory=dict)
    breaks: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "depends": dict(self.depends),
            "recommends": dict(self.recommends),
            "suggests": dict(self.suggests),
            "conflicts": dict(self.conflicts),
            "breaks": dict(self.breaks),
        }


@dataclass(frozen=True, slots=True)
class FabricManifest:
    """Static `fabric.mod.json` view."""

    path: Path
    mod_id: str | None
    version: str | None
    environment: str | None
    entrypoints: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    dependencies: FabricDependencyMap = field(default_factory=FabricDependencyMap)
    mixins: tuple[str, ...] = ()
    source_root: Path | None = None
    resource_root: Path | None = None
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "mod_id": self.mod_id,
            "version": self.version,
            "environment": self.environment,
            "entrypoints": {key: list(value) for key, value in self.entrypoints.items()},
            "dependencies": self.dependencies.to_dict(),
            "mixins": list(self.mixins),
            "source_root": str(self.source_root) if self.source_root is not None else None,
            "resource_root": str(self.resource_root)
            if self.resource_root is not None
            else None,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class MixinConfig:
    """Static mixin config view."""

    path: Path
    package: str | None
    required: bool | None
    compatibility_level: str | None
    mixins: tuple[str, ...] = ()
    client: tuple[str, ...] = ()
    server: tuple[str, ...] = ()
    default_require: int | None = None
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "package": self.package,
            "required": self.required,
            "compatibility_level": self.compatibility_level,
            "mixins": list(self.mixins),
            "client": list(self.client),
            "server": list(self.server),
            "default_require": self.default_require,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class ModuleSnapshot:
    """Observed module boundary."""

    path: Path
    build_files: tuple[Path, ...] = ()
    fabric_manifests: tuple[FabricManifest, ...] = ()
    source_roots: tuple[Path, ...] = ()
    resource_roots: tuple[Path, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "build_files": [str(path) for path in self.build_files],
            "fabric_manifests": [manifest.to_dict() for manifest in self.fabric_manifests],
            "source_roots": [str(path) for path in self.source_roots],
            "resource_roots": [str(path) for path in self.resource_roots],
        }


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    """Deterministic project inspection result."""

    project_root: Path
    inspected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: ProjectInspectionStatus = ProjectInspectionStatus.READY
    issues: tuple[str, ...] = ()
    wrapper: WrapperSnapshot = field(default_factory=lambda: WrapperSnapshot(False))
    git: GitBaseline = field(default_factory=lambda: GitBaseline(False))
    settings_files: tuple[Path, ...] = ()
    build_files: tuple[Path, ...] = ()
    gradle_properties: Path | None = None
    version_catalogs: tuple[Path, ...] = ()
    fabric_manifests: tuple[FabricManifest, ...] = ()
    mixin_configs: tuple[MixinConfig, ...] = ()
    source_roots: tuple[Path, ...] = ()
    resource_roots: tuple[Path, ...] = ()
    modules: tuple[ModuleSnapshot, ...] = ()
    target_subproject: Path | None = None
    detected_versions: Mapping[str, DetectedValue] = field(default_factory=dict)
    relevant_files: tuple[Path, ...] = ()
    metadata_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "inspected_at": self.inspected_at.isoformat(),
            "status": self.status.value,
            "issues": list(self.issues),
            "wrapper": self.wrapper.to_dict(),
            "git": self.git.to_dict(),
            "settings_files": [str(path) for path in self.settings_files],
            "build_files": [str(path) for path in self.build_files],
            "gradle_properties": str(self.gradle_properties)
            if self.gradle_properties is not None
            else None,
            "version_catalogs": [str(path) for path in self.version_catalogs],
            "fabric_manifests": [manifest.to_dict() for manifest in self.fabric_manifests],
            "mixin_configs": [mixin.to_dict() for mixin in self.mixin_configs],
            "source_roots": [str(path) for path in self.source_roots],
            "resource_roots": [str(path) for path in self.resource_roots],
            "modules": [module.to_dict() for module in self.modules],
            "target_subproject": str(self.target_subproject)
            if self.target_subproject is not None
            else None,
            "detected_versions": {
                key: value.to_dict() for key, value in self.detected_versions.items()
            },
            "relevant_files": [str(path) for path in self.relevant_files],
            "metadata_errors": list(self.metadata_errors),
        }

