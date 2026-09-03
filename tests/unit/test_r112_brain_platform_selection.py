from __future__ import annotations

import io
from dataclasses import dataclass
import zipfile

import pytest

from pd_agent.brain import (
    CompatibilityStatus,
    FabricApiKnowledgeSource,
    FabricConceptPatternKnowledgeSource,
    FrozenKnowledgePackSource,
    KnowledgeEnvironment,
    KnowledgeNeed,
    KnowledgeService,
    KnowledgeSourceSelection,
    KnowledgeType,
    YarnKnowledgeSource,
    knowledge_service_for_environment,
    materialize_frozen_knowledge_pack,
    select_knowledge_sources_for_environment,
    select_knowledge_sources_for_platform,
)
from pd_agent.fabric import (
    FabricMappingFamily,
    FabricPlatformEvidence,
    FabricPlatformProfile,
    FabricPlatformSupportStatus,
)
from pd_agent.brain.retrieval import _query_hash


LEGACY = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    loom_version="1.13.3",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
    java_version="21",
)
MODERN = KnowledgeEnvironment(
    minecraft_version="26.1.2",
    loader_version="0.20.0",
    loom_version="1.15.0",
    java_version="21",
)


def _fabric_api_artifact() -> bytes:
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("net/fabricmc/fabric/api/registry/v1/Registry.class", b"class")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/jars/fabric-api-base.jar", nested.getvalue())
        archive.writestr("fabric.mod.json", b"{}")
    return outer.getvalue()


def _yarn_artifact() -> bytes:
    return (
        "tiny\t2\t0\tofficial\tintermediary\tnamed\n"
        "c\tExample\texample\tExample\n"
    ).encode()


def _legacy_sources() -> tuple[object, ...]:
    yarn = YarnKnowledgeSource(artifact_bytes=_yarn_artifact())
    fabric_api = FabricApiKnowledgeSource(artifact_bytes=_fabric_api_artifact())
    concepts = FabricConceptPatternKnowledgeSource()
    pack = materialize_frozen_knowledge_pack((yarn, fabric_api, concepts), environment=LEGACY)
    return yarn, fabric_api, concepts, FrozenKnowledgePackSource(pack)


def test_legacy_platform_selection_accepts_all_compatible_source_families() -> None:
    sources = _legacy_sources()
    selection = select_knowledge_sources_for_environment(LEGACY, sources)
    assert isinstance(selection, KnowledgeSourceSelection)
    assert [source.source_id for source in selection.selected] == sorted(source.source_id for source in sources)
    assert selection.rejected == ()
    service, service_selection = knowledge_service_for_environment(LEGACY, sources)
    assert isinstance(service, KnowledgeService)
    assert service_selection == selection
    assert [source.source_id for source in service.sources] == [source.source_id for source in selection.selected]


def test_modern_environment_rejects_all_legacy_version_sensitive_sources() -> None:
    sources = _legacy_sources()
    selection = select_knowledge_sources_for_environment(MODERN, sources)
    assert selection.selected == ()
    assert {source_id for source_id, _, _ in selection.rejected} == {
        "net.fabricmc:yarn",
        "net.fabricmc.fabric-api:fabric-api",
        "fabric-docs:concept-pattern",
        "pd-agent:frozen-i16-pack",
    }
    assert all(status is not CompatibilityStatus.COMPATIBLE for _, status, _ in selection.rejected)


def test_unknown_version_sensitive_source_is_rejected_but_explicit_generic_source_is_kept() -> None:
    @dataclass
    class Source:
        source_id: str
        version_sensitive: bool = True
        source_kind: str = "test"
        artifact_version: str = "1"

        def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
            return CompatibilityStatus.UNKNOWN

    selection = select_knowledge_sources_for_environment(
        MODERN,
        (Source("generic", version_sensitive=False), Source("unknown")),
    )
    assert [source.source_id for source in selection.selected] == ["generic"]
    assert selection.rejected == (("unknown", CompatibilityStatus.UNKNOWN, "version-sensitive source requires known compatibility"),)


def test_profile_selection_requires_supported_status_and_uses_the_profile_environment() -> None:
    evidence = tuple(
        FabricPlatformEvidence(evidence_id=kind.casefold(), kind=kind, reference=f"docs/{kind.casefold()}.md")
        for kind in ("PROFILE_DEFINITION", "INSPECTION_RESOLUTION", "CONTRACT_WIRING", "BRAIN_COMPATIBILITY", "OFFLINE_BUILD")
    )
    profile = FabricPlatformProfile(
        platform_id="fabric-legacy",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        fabric_api_version="0.141.6+1.21.11",
        loom_version="1.13.3",
        java_version="21",
        mapping_family=FabricMappingFamily.OBFUSCATED_REMAPPED,
        mappings_namespace="yarn",
        mappings_version="1.21.11+build.6",
        support_status=FabricPlatformSupportStatus.SUPPORTED,
        evidence=evidence,
    )
    selected = select_knowledge_sources_for_platform(profile, _legacy_sources())
    assert len(selected.selected) == 4
    target = __import__("dataclasses").replace(profile, support_status=FabricPlatformSupportStatus.TARGET)
    with pytest.raises(ValueError, match="SUPPORTED"):
        select_knowledge_sources_for_platform(target, ())


def test_environment_changes_do_not_share_the_existing_cache_identity() -> None:
    need = KnowledgeNeed("cache", KnowledgeType.SYMBOL, "Example", LEGACY)
    modern_need = __import__("dataclasses").replace(need, environment=MODERN)
    assert _query_hash(need) != _query_hash(modern_need)
