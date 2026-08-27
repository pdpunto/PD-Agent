from __future__ import annotations

from pathlib import Path

import pytest

from pd_agent.brain import (
    CompatibilityStatus,
    EnvironmentDetectionStatus,
    KnowledgeEnvironment,
    KnowledgeEnvironmentResolver,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeType,
    SourceAuthority,
)
from pd_agent.project.fabric import FabricInspector
from tests.fixtures.fabric_projects import make_simple_fabric_project


ROOT = Path(__file__).resolve().parents[2]
L11_FIXTURE = ROOT / "tests" / "fixtures" / "l11_fabric_fixture"


def _make_unknown_environment_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    (root / "settings.gradle.kts").write_text('rootProject.name = "unknown"\n', encoding="utf-8", newline="\n")
    (root / "build.gradle.kts").write_text(
        """
plugins {
    id("fabric-loom") version "1.13.3"
}

repositories {
    mavenCentral()
    maven("https://maven.fabricmc.net/")
}
""".strip()
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "src" / "main" / "resources").mkdir(parents=True, exist_ok=True)
    (root / "src" / "main" / "resources" / "fabric.mod.json").write_text(
        """
{
  "schemaVersion": 1,
  "id": "unknown",
  "version": "1.0.0",
  "environment": "*"
}
""".strip()
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return root


def test_resolver_detects_l11_fixture_environment() -> None:
    resolution = KnowledgeEnvironmentResolver().resolve(L11_FIXTURE)

    assert resolution.status == EnvironmentDetectionStatus.DETECTED
    assert resolution.environment.minecraft_version == "1.21.11"
    assert resolution.environment.loader_version == "0.19.3"
    assert resolution.environment.loom_version == "1.13.3"
    assert resolution.environment.mappings_namespace == "yarn"
    assert resolution.environment.mappings_version == "1.21.11+build.6"
    assert resolution.environment.fabric_api_version is None
    assert resolution.environment.java_version is None
    assert any(item.startswith("minecraft_version=1.21.11") for item in resolution.evidence)


def test_resolver_completes_missing_fields_from_verified_environment() -> None:
    resolution = KnowledgeEnvironmentResolver().resolve(
        L11_FIXTURE,
        verification_sources=(
            {
                "minecraft_version": "1.21.11",
                "loader_version": "0.19.3",
                "loom_version": "1.13.3",
                "mappings_namespace": "yarn",
                "mappings_version": "1.21.11+build.6",
                "fabric_api_version": "0.141.6+1.21.11",
                "java_version": "21",
            },
        ),
    )

    assert resolution.status == EnvironmentDetectionStatus.DETECTED
    assert resolution.environment.java_version == "21"
    assert resolution.environment.fabric_api_version == "0.141.6+1.21.11"
    assert any(item == "java_version=21 (verified source)" for item in resolution.evidence)


def test_resolver_reports_unknown_when_minecraft_version_is_missing(tmp_path: Path) -> None:
    root = _make_unknown_environment_project(tmp_path / "unknown")

    resolution = KnowledgeEnvironmentResolver().resolve(root)

    assert resolution.status == EnvironmentDetectionStatus.UNKNOWN
    assert resolution.environment.minecraft_version is None
    assert resolution.environment.loader_version is None
    assert resolution.environment.loom_version is None
    assert resolution.environment.mappings_namespace is None
    assert resolution.environment.mappings_version is None
    assert resolution.environment.fabric_api_version is None


def test_resolver_reports_conflict_explicitly() -> None:
    resolution = KnowledgeEnvironmentResolver().resolve(
        L11_FIXTURE,
        verification_sources=(
            {"minecraft_version": "1.20.1"},
        ),
    )

    assert resolution.status == EnvironmentDetectionStatus.CONFLICT
    assert any("minecraft_version" in conflict for conflict in resolution.conflicts)


def test_resolver_detects_fabric_api_when_declared(tmp_path: Path) -> None:
    root = make_simple_fabric_project(tmp_path / "fabric-api")
    resolution = KnowledgeEnvironmentResolver().resolve(root)

    assert resolution.status == EnvironmentDetectionStatus.DETECTED
    assert resolution.environment.fabric_api_version == "0.92.1+1.20.1"


def test_knowledge_need_validation_and_serialization() -> None:
    environment = KnowledgeEnvironment(minecraft_version="1.21.11")
    need = KnowledgeNeed(
        id="l1-symbol",
        type=KnowledgeType.SYMBOL,
        query="Resolve the registry name for a vanilla block",
        environment=environment,
        hints=["server-side", "version-sensitive"],
    )

    assert need.hints == ("server-side", "version-sensitive")
    assert need.to_dict()["type"] == "SYMBOL"
    assert need.to_dict()["environment"]["minecraft_version"] == "1.21.11"

    with pytest.raises(ValueError):
        KnowledgeNeed(
            id="",
            type=KnowledgeType.SYMBOL,
            query="q",
            environment=environment,
        )

    with pytest.raises(ValueError):
        KnowledgeNeed(
            id="need-1",
            type=KnowledgeType.SYMBOL,
            query="",
            environment=environment,
        )


def test_compatibility_and_environment_enums_are_stable() -> None:
    assert {item.value for item in CompatibilityStatus} == {
        "COMPATIBLE",
        "INCOMPATIBLE",
        "UNKNOWN",
    }
    assert {
        item.value for item in KnowledgeType
    } >= {
        "SYMBOL",
        "API",
        "CONCEPT",
        "PATTERN",
        "EXAMPLE",
        "VERSION_CHANGE",
        "CAPABILITY",
        "DIAGNOSTIC",
    }
    assert {
        item.value for item in KnowledgeType
    } >= {
        "MAPPING",
        "BUILD",
        "MIGRATION",
    }
    assert EnvironmentDetectionStatus.DETECTED.value == "DETECTED"


def test_legacy_knowledge_types_migrate_without_rewriting_values() -> None:
    assert KnowledgeType.migrate_legacy("MAPPING") == KnowledgeType.SYMBOL
    assert KnowledgeType.migrate_legacy("MAPPING", meaning="version_change") == KnowledgeType.VERSION_CHANGE
    assert KnowledgeType.migrate_legacy("BUILD") == KnowledgeType.API
    assert KnowledgeType.migrate_legacy("BUILD", meaning="pattern") == KnowledgeType.PATTERN
    assert KnowledgeType.migrate_legacy("BUILD", meaning="diagnostic") == KnowledgeType.DIAGNOSTIC
    assert KnowledgeType.migrate_legacy("MIGRATION") == KnowledgeType.VERSION_CHANGE


def test_knowledge_need_version_sensitivity_round_trip() -> None:
    need = KnowledgeNeed(
        id="concept-1",
        type=KnowledgeType.CONCEPT,
        query="what is a registry",
        environment=KnowledgeEnvironment(),
        version_sensitive=False,
    )

    restored = KnowledgeNeed.from_dict(need.to_dict())

    assert restored == need
    assert restored.version_sensitive is False


def test_knowledge_item_version_sensitivity_round_trip() -> None:
    item = KnowledgeItem(
        id="concept-item",
        content={"text": "registry"},
        environment=KnowledgeEnvironment(),
        authority=SourceAuthority.OFFICIAL_DOCUMENTATION,
        provenance=KnowledgeProvenance(
            source_id="docs",
            source_kind="concept",
            locator="local://concept",
        ),
        version_sensitive=False,
    )

    restored = KnowledgeItem.from_dict(item.to_dict())

    assert restored == item
    assert restored.version_sensitive is False


def test_fabric_inspector_regression_on_l11_fixture() -> None:
    inspection = FabricInspector().inspect(L11_FIXTURE)

    assert inspection.wrapper_present is True
    assert inspection.detected_versions["minecraft"].value == "1.21.11"
    assert inspection.detected_versions["loader"].value == "0.19.3"
    assert inspection.detected_versions["loom"].value == "1.13.3"
    assert inspection.detected_versions["mappings"].value == "1.21.11+build.6"
    assert inspection.target_subproject is not None
