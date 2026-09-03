from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_agent.bootstrap import FabricBootstrap, FabricBootstrapError
from pd_agent.fabric import (
    FabricMappingFamily,
    FabricPlatformEvidence,
    FabricPlatformProfile,
    FabricPlatformSupportStatus,
    FabricProjectTemplate,
    FabricProjectTemplateError,
    load_platform_registry,
    load_project_templates,
    platform_observation_from_inspection,
)
from pd_agent.project.fabric import FabricInspector


EVIDENCE = tuple(
    FabricPlatformEvidence(evidence_id=kind.casefold(), kind=kind, reference=f"docs/{kind.casefold()}.md")
    for kind in ("PROFILE_DEFINITION", "INSPECTION_RESOLUTION", "CONTRACT_WIRING", "BRAIN_COMPATIBILITY", "OFFLINE_BUILD")
)


def _profile(
    *,
    platform_id: str = "fabric-legacy",
    family: FabricMappingFamily = FabricMappingFamily.OBFUSCATED_REMAPPED,
    status: FabricPlatformSupportStatus = FabricPlatformSupportStatus.SUPPORTED,
    **overrides: object,
) -> FabricPlatformProfile:
    values: dict[str, object] = {
        "platform_id": platform_id,
        "minecraft_version": "1.21.11",
        "loader_version": "0.19.3",
        "fabric_api_version": "0.141.6+1.21.11",
        "loom_version": "1.13.3",
        "java_version": "21",
        "mapping_family": family,
        "mappings_namespace": "yarn" if family is FabricMappingFamily.OBFUSCATED_REMAPPED else None,
        "mappings_version": "1.21.11+build.6" if family is FabricMappingFamily.OBFUSCATED_REMAPPED else None,
        "support_status": status,
        "evidence": EVIDENCE,
    }
    values.update(overrides)
    return FabricPlatformProfile(**values)


def _template(*platform_ids: str, **overrides: object) -> FabricProjectTemplate:
    values: dict[str, object] = {
        "template_id": "fabric-template",
        "template_revision": "1",
        "platform_ids": platform_ids or ("fabric-legacy",),
        "evidence": ("docs/template.md",),
    }
    values.update(overrides)
    return FabricProjectTemplate(**values)


def test_template_is_immutable_and_deterministic() -> None:
    template = _template("fabric-legacy", "fabric-modern")
    assert template.to_dict() == FabricProjectTemplate.from_dict(template.to_dict()).to_dict()
    with pytest.raises((AttributeError, TypeError)):
        template.template_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "values",
    [
        {"template_id": "", "template_revision": "1", "platform_ids": ("fabric",)},
        {"template_id": "fabric", "template_revision": "", "platform_ids": ("fabric",)},
        {"template_id": "fabric", "template_revision": "1", "platform_ids": ()},
        {"template_id": "fabric", "template_revision": "1", "platform_ids": ("fabric", "fabric")},
        {"template_id": "fabric", "template_revision": "1", "platform_ids": ("fabric",), "seed_identity": "bad"},
        {"template_id": "fabric", "template_revision": "1", "platform_ids": ("fabric",), "evidence": ("C:/secret",)},
    ],
)
def test_invalid_template_data_fails_closed(values: dict[str, object]) -> None:
    with pytest.raises(FabricProjectTemplateError):
        FabricProjectTemplate(**values)


def test_template_loader_validates_schema_duplicates_and_malformed_json(tmp_path: Path) -> None:
    valid = tmp_path / "templates.json"
    valid.write_text(json.dumps({"schema_version": 1, "templates": [_template().to_dict()]}), encoding="utf-8")
    assert load_project_templates(valid)[0] == _template()

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(json.dumps({"schema_version": 1, "templates": [_template().to_dict(), _template().to_dict()]}), encoding="utf-8")
    with pytest.raises(FabricProjectTemplateError, match="duplicate"):
        load_project_templates(duplicate)

    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(FabricProjectTemplateError):
        load_project_templates(malformed)


def test_source_controlled_legacy_template_is_available() -> None:
    path = Path("src/pd_agent/fabric/data/project_templates.json")
    templates = load_project_templates(path)
    assert templates[0].template_id == "fabric-legacy-default"
    assert templates[0].platform_ids == ("fabric-minecraft-1.21.11",)


def test_explicit_legacy_profile_controls_bootstrap_and_round_trips(tmp_path: Path) -> None:
    profile = load_platform_registry(Path("src/pd_agent/fabric/data/platform_profiles.json")).list_profiles()[0]
    template = load_project_templates(Path("src/pd_agent/fabric/data/project_templates.json"))[0]
    result = FabricBootstrap().create(
        tmp_path / "project",
        mod_id="examplemod",
        package="com.example.examplemod",
        platform_profile=profile,
        project_template=template,
    )
    properties = (result.workspace / "gradle.properties").read_text(encoding="utf-8")
    build = (result.workspace / "build.gradle.kts").read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    inspection = FabricInspector().inspect(result.workspace)
    resolution = load_platform_registry(Path("src/pd_agent/fabric/data/platform_profiles.json")).resolve(
        platform_observation_from_inspection(inspection)
    )

    assert "minecraft_version=1.21.11" in properties
    assert "loader_version=0.19.3" in properties
    assert "fabric_api_version=0.141.6+1.21.11" in properties
    assert "mappings_version=1.21.11+build.6" in properties
    assert 'id("fabric-loom") version "1.13.3"' in build
    assert "JavaLanguageVersion.of(21)" in build
    assert 'mappings("net.fabricmc:yarn:${property("mappings_version")}:v2")' in build
    assert manifest["platform_id"] == profile.platform_id
    assert manifest["platform_identity"] == profile.identity
    assert manifest["template_id"] == template.template_id
    assert manifest["template_revision"] == template.template_revision
    assert result.project_fingerprint == manifest["project_fingerprint"]
    assert resolution.status.value == "SUPPORTED"
    assert resolution.selected_profile == profile


def test_profile_template_mismatch_and_pairing_fail_closed(tmp_path: Path) -> None:
    profile = _profile(platform_id="fabric-a")
    with pytest.raises(FabricBootstrapError, match="together"):
        FabricBootstrap().create(tmp_path / "missing", mod_id="mod", package="com.example.mod", platform_profile=profile)
    with pytest.raises(FabricBootstrapError, match="mismatch"):
        FabricBootstrap().create(
            tmp_path / "wrong",
            mod_id="mod",
            package="com.example.mod",
            platform_profile=profile,
            project_template=_template("fabric-b"),
        )


def test_explicit_profile_wins_over_pinned_compatibility_adapter(tmp_path: Path) -> None:
    profile = _profile(
        platform_id="fabric-custom",
        minecraft_version="1.22.1",
        loader_version="0.22.0",
        fabric_api_version="0.200.0+1.22.1",
        loom_version="1.14.0",
        mappings_version="1.22.1+build.1",
    )
    result = FabricBootstrap().create(
        tmp_path / "project",
        mod_id="custom",
        package="com.example.custom",
        platform_profile=profile,
        project_template=_template("fabric-custom"),
    )
    properties = (result.workspace / "gradle.properties").read_text(encoding="utf-8")
    assert "minecraft_version=1.22.1" in properties
    assert "minecraft_version=1.21.11" not in properties
    assert result.platform_id == "fabric-custom"


def test_modern_target_uses_unobfuscated_rendering_without_yarn(tmp_path: Path) -> None:
    profile = _profile(
        platform_id="fabric-modern-target",
        family=FabricMappingFamily.UNOBFUSCATED,
        status=FabricPlatformSupportStatus.TARGET,
        minecraft_version="26.1.2",
        loader_version="0.20.0",
        fabric_api_version="0.200.0+26.1.2",
        loom_version="1.15.0",
    )
    result = FabricBootstrap().create(
        tmp_path / "modern",
        mod_id="modernmod",
        package="com.example.modern",
        platform_profile=profile,
        project_template=_template("fabric-modern-target"),
    )
    properties = (result.workspace / "gradle.properties").read_text(encoding="utf-8")
    build = (result.workspace / "build.gradle.kts").read_text(encoding="utf-8")
    assert "mappings_version=" not in properties
    assert "net.fabricmc:yarn" not in build
    assert result.platform_id == profile.platform_id
    assert profile.support_status is FabricPlatformSupportStatus.TARGET


def test_template_seed_identity_is_provenance_constraint(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "stable.bin").write_bytes(b"seed")
    from pd_agent.core import portable_seed_identity

    identity = portable_seed_identity(seed)
    profile = _profile()
    template = _template("fabric-legacy", seed_identity=identity)
    result = FabricBootstrap().create(
        tmp_path / "project",
        mod_id="mod",
        package="com.example.mod",
        seed_root=seed,
        expected_seed_identity=identity,
        platform_profile=profile,
        project_template=template,
    )
    assert result.seed_identity == identity
    with pytest.raises(FabricBootstrapError, match="template seed"):
        FabricBootstrap().create(
            tmp_path / "bad",
            mod_id="bad",
            package="com.example.bad",
            platform_profile=profile,
            project_template=_template("fabric-legacy", seed_identity="0" * 64),
        )
