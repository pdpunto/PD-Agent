"""Knowledge environment resolver."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from pd_agent.project.fabric import FabricInspectionResult, FabricInspector

from .models import (
    EnvironmentDetectionStatus,
    KnowledgeEnvironment,
    KnowledgeEnvironmentResolution,
)


_CANONICAL_FIELDS = (
    "minecraft_version",
    "loader_version",
    "loom_version",
    "mappings_namespace",
    "mappings_version",
    "fabric_api_version",
    "java_version",
)

_ALIASES: dict[str, tuple[str, ...]] = {
    "minecraft_version": ("minecraft_version", "minecraft"),
    "loader_version": ("loader_version", "loader"),
    "loom_version": ("loom_version", "loom"),
    "mappings_namespace": ("mappings_namespace",),
    "mappings_version": ("mappings_version", "yarn_mappings"),
    "fabric_api_version": ("fabric_api_version", "fabric_api", "fabric_version"),
    "java_version": ("java_version", "java"),
}


@dataclass(frozen=True, slots=True)
class KnowledgeEnvironmentResolver:
    """Build a Brain environment view from a Fabric project."""

    fabric_inspector: FabricInspector = field(default_factory=FabricInspector)

    def resolve(
        self,
        project_root: Path,
        *,
        inspection: FabricInspectionResult | None = None,
        verification_sources: Sequence[Mapping[str, str | None]] = (),
    ) -> KnowledgeEnvironmentResolution:
        root = project_root.resolve(strict=True)
        fabric = inspection or self.fabric_inspector.inspect(root)

        primary_values, evidence = self._primary_values(fabric)
        conflicts = self._conflicts(primary_values, verification_sources)
        self._complete_from_verified_sources(primary_values, evidence, verification_sources, conflicts)
        status = self._status(primary_values, conflicts)

        return KnowledgeEnvironmentResolution(
            status=status,
            environment=KnowledgeEnvironment(
                minecraft_version=primary_values["minecraft_version"],
                loader_version=primary_values["loader_version"],
                loom_version=primary_values["loom_version"],
                mappings_namespace=primary_values["mappings_namespace"],
                mappings_version=primary_values["mappings_version"],
                fabric_api_version=primary_values["fabric_api_version"],
                java_version=primary_values["java_version"],
            ),
            evidence=tuple(evidence),
            conflicts=tuple(conflicts),
        )

    def _primary_values(
        self, fabric: FabricInspectionResult
    ) -> tuple[dict[str, str | None], list[str]]:
        values: dict[str, str | None] = {field: None for field in _CANONICAL_FIELDS}
        evidence: list[str] = []

        for field, detected_key in (
            ("minecraft_version", "minecraft"),
            ("loader_version", "loader"),
            ("loom_version", "loom"),
            ("mappings_version", "mappings"),
            ("fabric_api_version", "fabric_api"),
        ):
            detected = fabric.detected_versions.get(detected_key)
            if detected is not None:
                values[field] = detected.value
                evidence.append(f"{field}={detected.value} ({detected.source})")

        values["mappings_namespace"] = self._detect_mappings_namespace(fabric)
        if values["mappings_namespace"] is not None:
            evidence.append(f"mappings_namespace={values['mappings_namespace']}")

        return values, evidence

    def _complete_from_verified_sources(
        self,
        values: dict[str, str | None],
        evidence: list[str],
        verification_sources: Sequence[Mapping[str, str | None]],
        conflicts: list[str],
    ) -> None:
        """Fill undetectable fields from an already-authoritative claim."""

        for field in _CANONICAL_FIELDS:
            candidates = {
                normalized[field]
                for source in verification_sources
                for normalized in (self._normalize_claims(source),)
                if normalized[field] is not None
            }
            if values[field] is not None:
                continue
            if len(candidates) == 1:
                value = next(iter(candidates))
                values[field] = value
                evidence.append(f"{field}={value} (verified source)")
            elif len(candidates) > 1:
                conflicts.append(f"verified sources disagree on {field}: {sorted(candidates)!r}")

    def _detect_mappings_namespace(self, fabric: FabricInspectionResult) -> str | None:
        pattern = re.compile(
            r'mappings\s*(?:\(\s*|\s+)["\']net\.fabricmc:([A-Za-z0-9_.-]+):',
            re.MULTILINE,
        )
        for build_file in fabric.build_files:
            text = build_file.read_text(encoding="utf-8")
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None

    def _conflicts(
        self,
        primary_values: Mapping[str, str | None],
        verification_sources: Sequence[Mapping[str, str | None]],
    ) -> list[str]:
        conflicts: list[str] = []
        for source_index, source in enumerate(verification_sources, start=1):
            normalized = self._normalize_claims(source)
            for field in _CANONICAL_FIELDS:
                primary = primary_values[field]
                candidate = normalized.get(field)
                if primary is not None and candidate is not None and primary != candidate:
                    conflicts.append(
                        f"source[{source_index}] {field}: {primary!r} != {candidate!r}"
                    )
        return conflicts

    def _normalize_claims(self, claims: Mapping[str, str | None]) -> dict[str, str | None]:
        normalized: dict[str, str | None] = {field: None for field in _CANONICAL_FIELDS}
        for canonical, aliases in _ALIASES.items():
            for alias in aliases:
                if alias in claims:
                    value = claims[alias]
                    normalized[canonical] = value if value else None
                    break
        return normalized

    def _status(
        self,
        primary_values: Mapping[str, str | None],
        conflicts: Sequence[str],
    ) -> EnvironmentDetectionStatus:
        if conflicts:
            return EnvironmentDetectionStatus.CONFLICT
        if primary_values["minecraft_version"] is None:
            return EnvironmentDetectionStatus.UNKNOWN
        return EnvironmentDetectionStatus.DETECTED
