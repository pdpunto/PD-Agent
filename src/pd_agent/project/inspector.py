"""High-level project inspection orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .fabric import FabricInspector
from .git import GitInspector
from .models import ModuleSnapshot, ProjectInspectionStatus, ProjectSnapshot, WrapperSnapshot


@dataclass(frozen=True, slots=True)
class ProjectInspector:
    """Deterministic inspector for Fabric projects."""

    def inspect(self, project_root: Path) -> ProjectSnapshot:
        root = project_root.resolve(strict=True)
        git = GitInspector(root).inspect()
        fabric = FabricInspector().inspect(root)

        status = ProjectInspectionStatus.READY
        issues = list(fabric.issues)
        if not fabric.wrapper_present:
            status = ProjectInspectionStatus.INCOMPATIBLE
            issues.append("Gradle Wrapper absent")
        if any(manifest.errors for manifest in fabric.manifests):
            status = ProjectInspectionStatus.INCOMPATIBLE
        if fabric.target_subproject is None and len(fabric.manifests) > 1:
            status = ProjectInspectionStatus.BLOCKED
            issues.append("ambiguous Fabric subproject selection")

        module_snapshots = tuple(
            sorted(
                (
                    self._module_snapshot(module_root, fabric)
                    for module_root in fabric.module_roots
                ),
                key=lambda item: str(item.path).casefold(),
            )
        )
        relevant_files = self._relevant_files(root, fabric)

        return ProjectSnapshot(
            project_root=root,
            status=status,
            issues=tuple(dict.fromkeys(issues)),
            wrapper=WrapperSnapshot(
                present=fabric.wrapper_present,
                scripts=fabric.wrapper_scripts,
                platform_hint=(
                    "windows"
                    if any(path.suffix == ".bat" for path in fabric.wrapper_scripts)
                    else "posix"
                    if fabric.wrapper_scripts
                    else None
                ),
                error=None if fabric.wrapper_present else "Gradle Wrapper absent",
            ),
            git=git,
            settings_files=fabric.settings_files,
            build_files=fabric.build_files,
            gradle_properties=fabric.gradle_properties,
            version_catalogs=fabric.version_catalogs,
            fabric_manifests=fabric.manifests,
            mixin_configs=fabric.mixins,
            source_roots=fabric.source_roots,
            resource_roots=fabric.resource_roots,
            modules=module_snapshots,
            target_subproject=fabric.target_subproject,
            detected_versions=fabric.detected_versions,
            relevant_files=relevant_files,
            metadata_errors=tuple(
                error for manifest in fabric.manifests for error in manifest.errors
            ),
        )

    def _module_snapshot(self, module_root: Path, fabric) -> ModuleSnapshot:
        manifests = tuple(
            manifest
            for manifest in fabric.manifests
            if self._module_root_for_manifest(manifest.path) == module_root
        )
        build_files = tuple(
            sorted(
                p for p in fabric.build_files if p.parent == module_root or p.parent.parent == module_root
            )
        )
        source_roots = tuple(
            sorted(
                p for p in fabric.source_roots if self._under_root(p, module_root)
            )
        )
        resource_roots = tuple(
            sorted(
                p for p in fabric.resource_roots if self._under_root(p, module_root)
            )
        )
        return ModuleSnapshot(
            path=module_root,
            build_files=build_files,
            fabric_manifests=manifests,
            source_roots=source_roots,
            resource_roots=resource_roots,
        )

    def _relevant_files(self, root: Path, fabric) -> tuple[Path, ...]:
        paths = set(fabric.settings_files)
        paths.update(fabric.build_files)
        paths.update(manifest.path for manifest in fabric.manifests)
        paths.update(mixin.path for mixin in fabric.mixins)
        paths.update(fabric.version_catalogs)
        if fabric.gradle_properties is not None:
            paths.add(fabric.gradle_properties)
        if fabric.wrapper_present:
            paths.update(fabric.wrapper_scripts)
        return tuple(sorted(paths, key=lambda path: str(path).casefold()))

    def _module_root_for_manifest(self, manifest_path: Path) -> Path:
        posix = manifest_path.as_posix()
        if posix.endswith("/src/main/resources/fabric.mod.json") and len(manifest_path.parents) > 3:
            return manifest_path.parents[3]
        return manifest_path.parent

    def _under_root(self, candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True

