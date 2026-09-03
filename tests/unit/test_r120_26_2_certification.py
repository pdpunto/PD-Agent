from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from pd_agent.brain import (
    FabricApiKnowledgeSource,
    FabricConceptPatternKnowledgeSource,
    FrozenKnowledgePackSource,
    KnowledgeEnvironment,
    KnowledgeNeed,
    KnowledgeService,
    KnowledgeType,
    YarnKnowledgeSource,
    materialize_frozen_knowledge_pack,
    select_knowledge_sources_for_environment,
)
from pd_agent.fabric import (
    FabricMappingFamily,
    FabricPlatformResolutionStatus,
    load_platform_registry,
    platform_observation_from_inspection,
)
from pd_agent.project.fabric import FabricInspector


MODERN = KnowledgeEnvironment(
    minecraft_version="26.2",
    loader_version="0.19.3",
    loom_version="1.17-SNAPSHOT",
    fabric_api_version="0.158.0+26.2",
    java_version="25",
)
LEGACY = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    loom_version="1.13.3",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
    java_version="21",
)


def _api_artifact() -> bytes:
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("net/fabricmc/fabric/api/registry/v1/Registry.class", b"class")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("META-INF/jars/fabric-api-base.jar", nested.getvalue())
    return outer.getvalue()


def _yarn_artifact() -> bytes:
    return b"tiny\t2\t0\tofficial\tintermediary\tnamed\nc\tExample\texample\tExample\n"


def _workspace(root: Path) -> Path:
    (root / "src/main/java").mkdir(parents=True)
    (root / "src/main/resources").mkdir(parents=True)
    (root / "src/main/resources/fabric.mod.json").write_text(
        json.dumps({"id": "modernfixture", "entrypoints": {"main": ["Main"]}}),
        encoding="utf-8",
    )
    (root / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
    (root / "gradle.properties").write_text(
        "minecraft_version=26.2\nloader_version=0.19.3\n"
        "fabric_api_version=0.158.0+26.2\nloom_version=1.17-SNAPSHOT\n",
        encoding="utf-8",
    )
    (root / "build.gradle.kts").write_text(
        'plugins { id("net.fabricmc.fabric-loom") version "1.17-SNAPSHOT" }\n'
        'java { toolchain { languageVersion.set(JavaLanguageVersion.of(25)) } }\n',
        encoding="utf-8",
    )
    return root


def test_modern_inspection_observes_project_java_and_unobfuscated_family(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JAVA_HOME", "C:/unrelated-process-java")
    inspection = FabricInspector().inspect(_workspace(tmp_path / "modern"))
    assert inspection.detected_versions["java"].value == "25"
    assert inspection.detected_versions["mapping_family"].value == "UNOBFUSCATED"
    observation = platform_observation_from_inspection(inspection)
    assert observation.mapping_family is FabricMappingFamily.UNOBFUSCATED
    assert observation.mappings_namespace is None
    assert observation.mappings_version is None

    registry_path = Path("src/pd_agent/fabric/data/platform_profiles.json")
    resolution = load_platform_registry(registry_path).resolve(observation)
    assert resolution.status is FabricPlatformResolutionStatus.SUPPORTED
    assert resolution.selected_profile is not None
    assert resolution.selected_profile.platform_id == "fabric-minecraft-26.2"


def test_legacy_inspection_keeps_java_and_yarn_facts() -> None:
    inspection = FabricInspector().inspect(Path("tests/fixtures/l11_fabric_fixture"))
    assert inspection.detected_versions["java"].value == "21"
    assert inspection.detected_versions["mappings"].value == "1.21.11+build.6"
    assert inspection.detected_versions["mapping_family"].value == "OBFUSCATED_REMAPPED"


def test_modern_brain_selects_modern_sources_and_rejects_legacy_sources() -> None:
    modern_api = FabricApiKnowledgeSource(
        version="0.158.0+26.2", minecraft_version="26.2", loader_version="0.19.3",
        artifact_bytes=_api_artifact(),
    )
    modern_concepts = FabricConceptPatternKnowledgeSource(environment=MODERN)
    legacy_yarn = YarnKnowledgeSource(artifact_bytes=_yarn_artifact())
    legacy_api = FabricApiKnowledgeSource(artifact_bytes=_api_artifact())
    legacy_concepts = FabricConceptPatternKnowledgeSource()
    legacy_pack = FrozenKnowledgePackSource(
        materialize_frozen_knowledge_pack(
            (legacy_yarn, legacy_api, legacy_concepts), environment=LEGACY
        )
    )

    sources = (modern_api, modern_concepts, legacy_yarn, legacy_pack)
    selection = select_knowledge_sources_for_environment(MODERN, sources)
    assert [source.source_id for source in selection.selected] == [
        "fabric-docs:concept-pattern", "net.fabricmc.fabric-api:fabric-api"
    ]
    rejected = {source_id for source_id, _, _ in selection.rejected}
    assert {"net.fabricmc:yarn", "pd-agent:frozen-i16-pack"}.issubset(rejected)
    assert all(status.value == "INCOMPATIBLE" for source_id, status, _ in selection.rejected)
    assert select_knowledge_sources_for_environment(MODERN, (legacy_api,)).selected == ()
    assert select_knowledge_sources_for_environment(MODERN, (legacy_api,)).rejected[0][1].value == "INCOMPATIBLE"

    need = KnowledgeNeed("modern", KnowledgeType.CONCEPT, "registry block", MODERN)
    result = KnowledgeService(selection.selected).resolve(need, offline=True)
    assert result.status.value == "SUCCESS"
    assert result.items


def test_modern_repair_environment_is_not_replaced_by_legacy_default() -> None:
    source = FabricConceptPatternKnowledgeSource(environment=MODERN)
    need = KnowledgeNeed("repair", KnowledgeType.PATTERN, "block registration", MODERN)
    assert source.compatibility(need.environment).value == "COMPATIBLE"
    assert source.compatibility(LEGACY).value == "INCOMPATIBLE"
