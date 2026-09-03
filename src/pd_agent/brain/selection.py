"""Platform-aware selection of the existing Brain knowledge sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import CompatibilityStatus, KnowledgeEnvironment
from .retrieval import KnowledgeService, KnowledgeSource


@dataclass(frozen=True, slots=True)
class KnowledgeSourceSelection:
    """Deterministic source selection with explainable compatibility rejects."""

    selected: tuple[KnowledgeSource, ...] = ()
    rejected: tuple[tuple[str, CompatibilityStatus, str], ...] = ()


def select_knowledge_sources_for_environment(
    environment: KnowledgeEnvironment,
    sources: Iterable[KnowledgeSource],
) -> KnowledgeSourceSelection:
    """Select compatible sources without retrieval, I/O, or support resolution."""
    if not isinstance(environment, KnowledgeEnvironment):
        raise TypeError("environment must be KnowledgeEnvironment")
    ordered = tuple(sorted(tuple(sources), key=lambda source: source.source_id))
    source_ids = [source.source_id for source in ordered]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("knowledge source_id values must be unique")

    selected: list[KnowledgeSource] = []
    rejected: list[tuple[str, CompatibilityStatus, str]] = []
    for source in ordered:
        try:
            compatibility = source.compatibility(environment)
        except Exception as exc:
            rejected.append((source.source_id, CompatibilityStatus.UNKNOWN, f"compatibility error: {exc}"))
            continue
        if compatibility is CompatibilityStatus.COMPATIBLE:
            selected.append(source)
        elif compatibility is CompatibilityStatus.UNKNOWN and not getattr(source, "version_sensitive", True):
            selected.append(source)
        elif compatibility is CompatibilityStatus.UNKNOWN:
            rejected.append((source.source_id, compatibility, "version-sensitive source requires known compatibility"))
        else:
            rejected.append((source.source_id, compatibility, "source environment incompatible"))
    return KnowledgeSourceSelection(tuple(selected), tuple(rejected))


def select_knowledge_sources_for_platform(profile: object, sources: Iterable[KnowledgeSource]) -> KnowledgeSourceSelection:
    """Select sources from an already resolved SUPPORTED Fabric profile."""
    from pd_agent.fabric import FabricPlatformProfile, FabricPlatformSupportStatus, knowledge_environment_from_profile

    if not isinstance(profile, FabricPlatformProfile):
        raise TypeError("profile must be FabricPlatformProfile")
    if profile.support_status is not FabricPlatformSupportStatus.SUPPORTED:
        raise ValueError("source selection requires a SUPPORTED platform profile")
    return select_knowledge_sources_for_environment(knowledge_environment_from_profile(profile), sources)


def knowledge_service_for_environment(
    environment: KnowledgeEnvironment,
    sources: Iterable[KnowledgeSource],
) -> tuple[KnowledgeService, KnowledgeSourceSelection]:
    """Reuse one KnowledgeService architecture with a selected source set."""
    selection = select_knowledge_sources_for_environment(environment, sources)
    return KnowledgeService(selection.selected), selection


__all__ = [
    "KnowledgeSourceSelection",
    "knowledge_service_for_environment",
    "select_knowledge_sources_for_environment",
    "select_knowledge_sources_for_platform",
]
