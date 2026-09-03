import json

import pytest

from pd_agent.fabric import (
    FabricMappingFamily,
    FabricPlatformEvidence,
    FabricPlatformEvidenceKind,
    FabricPlatformModelError,
    FabricPlatformObservation,
    FabricPlatformProfile,
    FabricPlatformResolutionStatus,
    FabricPlatformSupportStatus,
    FabricSupportRegistry,
    load_platform_registry,
)


EVIDENCE = tuple(
    FabricPlatformEvidence(evidence_id=name.lower(), kind=name, reference=f"docs/{name.lower()}.md")
    for name in (
        "PROFILE_DEFINITION",
        "INSPECTION_RESOLUTION",
        "CONTRACT_WIRING",
        "BRAIN_COMPATIBILITY",
        "OFFLINE_BUILD",
    )
)


def _profile(
    platform_id: str = "fabric-legacy",
    *,
    family: FabricMappingFamily = FabricMappingFamily.OBFUSCATED_REMAPPED,
    status: FabricPlatformSupportStatus = FabricPlatformSupportStatus.SUPPORTED,
    evidence=EVIDENCE,
    **overrides,
) -> FabricPlatformProfile:
    values = {
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
        "evidence": evidence,
    }
    values.update(overrides)
    return FabricPlatformProfile(**values)


def _observation(**overrides) -> FabricPlatformObservation:
    values = {
        "minecraft_version": "1.21.11",
        "loader_version": "0.19.3",
        "fabric_api_version": "0.141.6+1.21.11",
        "loom_version": "1.13.3",
        "java_version": "21",
        "mappings_namespace": "yarn",
        "mappings_version": "1.21.11+build.6",
        "mapping_family": FabricMappingFamily.OBFUSCATED_REMAPPED,
    }
    values.update(overrides)
    return FabricPlatformObservation(**values)


def test_legacy_profile_is_valid_and_identity_is_stable() -> None:
    profile = _profile()
    assert profile.identity == _profile().identity
    assert profile.to_dict()["platform_identity"] == profile.identity
    assert tuple(item.evidence_id for item in profile.evidence) == tuple(sorted(item.evidence_id for item in EVIDENCE))
    with pytest.raises(AttributeError):
        profile.platform_id = "changed"


def test_modern_target_has_no_yarn() -> None:
    profile = _profile(
        platform_id="fabric-modern-target",
        family=FabricMappingFamily.UNOBFUSCATED,
        status=FabricPlatformSupportStatus.TARGET,
        minecraft_version="26.1.2",
        loader_version="loader-pending",
        fabric_api_version="api-pending",
        loom_version="loom-pending",
    )
    assert profile.mappings_namespace is None
    assert profile.mappings_version is None


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"platform_id": ""},
        {"mapping_family": "INVALID"},
        {"mapping_family": FabricMappingFamily.UNOBFUSCATED, "mappings_namespace": "yarn", "mappings_version": "1"},
        {"mappings_namespace": None, "mappings_version": None},
    ],
)
def test_profile_invariants_fail_closed(changes) -> None:
    if changes == {"mappings_namespace": None, "mappings_version": None}:
        changes = {"mapping_family": FabricMappingFamily.OBFUSCATED_REMAPPED, **changes}
    with pytest.raises((FabricPlatformModelError, ValueError)):
        _profile(**changes)


def test_duplicate_evidence_ids_are_rejected() -> None:
    duplicate = (EVIDENCE[0], EVIDENCE[0])
    with pytest.raises(FabricPlatformModelError, match="evidence IDs"):
        _profile(evidence=duplicate)


def test_supported_profile_requires_evidence_gate() -> None:
    with pytest.raises(FabricPlatformModelError, match="mandatory evidence"):
        _profile(evidence=EVIDENCE[:-1])
    target = _profile(status=FabricPlatformSupportStatus.TARGET, evidence=())
    retired = _profile(status=FabricPlatformSupportStatus.RETIRED, evidence=())
    assert target.support_status is FabricPlatformSupportStatus.TARGET
    assert retired.support_status is FabricPlatformSupportStatus.RETIRED


def test_registry_is_sorted_immutable_and_rejects_duplicates() -> None:
    registry = FabricSupportRegistry((_profile("z"), _profile("a")))
    assert tuple(item.platform_id for item in registry.list_profiles()) == ("a", "z")
    assert registry.get("a").platform_id == "a"
    with pytest.raises(TypeError):
        registry.snapshot()["x"] = _profile("x")
    with pytest.raises(AttributeError):
        registry._profiles = ()
    with pytest.raises(FabricPlatformModelError, match="duplicate"):
        FabricSupportRegistry((_profile(), _profile()))


def test_resolution_supported_requires_exact_match() -> None:
    result = FabricSupportRegistry((_profile(),)).resolve(_observation())
    assert result.status is FabricPlatformResolutionStatus.SUPPORTED
    assert result.selected_profile.platform_id == "fabric-legacy"
    changed = FabricSupportRegistry((_profile(),)).resolve(_observation(loader_version="other"))
    assert changed.status is FabricPlatformResolutionStatus.UNSUPPORTED


def test_target_and_retired_are_not_executable() -> None:
    for status in (FabricPlatformSupportStatus.TARGET, FabricPlatformSupportStatus.RETIRED):
        result = FabricSupportRegistry((_profile(status=status, evidence=()),)).resolve(_observation())
        assert result.status is FabricPlatformResolutionStatus.UNSUPPORTED
        assert result.selected_profile is None


def test_missing_facts_are_unknown_and_conflicts_are_conflict() -> None:
    registry = FabricSupportRegistry((_profile(),))
    unknown = registry.resolve(_observation(java_version=None, missing_facts=("java_version",)))
    assert unknown.status is FabricPlatformResolutionStatus.UNKNOWN
    conflict = registry.resolve(_observation(conflicts=("minecraft_version",)))
    assert conflict.status is FabricPlatformResolutionStatus.CONFLICT
    assert conflict.selected_profile is None


def test_observation_and_resolution_are_serializable() -> None:
    observation = _observation()
    restored_observation = FabricPlatformObservation.from_dict(observation.to_dict())
    assert restored_observation == observation
    result = FabricSupportRegistry((_profile(),)).resolve(observation)
    payload = result.to_dict()
    assert payload["status"] == "SUPPORTED"
    assert payload["selected_profile"]["platform_id"] == "fabric-legacy"


def test_evidence_rejects_absolute_paths_and_forbidden_content() -> None:
    with pytest.raises(FabricPlatformModelError):
        FabricPlatformEvidence(evidence_id="x", kind="PROFILE_DEFINITION", reference="C:/secret.txt")
    with pytest.raises(FabricPlatformModelError):
        FabricPlatformEvidence(evidence_id="x", kind="PROFILE_DEFINITION", reference="docs/command.md")


def test_multiple_supported_matches_are_conflict() -> None:
    result = FabricSupportRegistry((_profile("a"), _profile("b"))).resolve(_observation())
    assert result.status is FabricPlatformResolutionStatus.CONFLICT


def test_declarative_registry_loads_current_legacy_profile() -> None:
    registry = load_platform_registry(__import__("pathlib").Path("src/pd_agent/fabric/data/platform_profiles.json"))
    assert [profile.platform_id for profile in registry.list_profiles()] == ["fabric-minecraft-1.21.11"]
    assert registry.list_profiles()[0].support_status is FabricPlatformSupportStatus.SUPPORTED


def test_declarative_loader_rejects_bad_schema_and_identity(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": 2, "profiles": []}), encoding="utf-8")
    with pytest.raises(FabricPlatformModelError):
        load_platform_registry(bad)
    profile = _profile().to_dict()
    profile["platform_identity"] = "0" * 64
    bad.write_text(json.dumps({"schema_version": 1, "profiles": [profile]}), encoding="utf-8")
    with pytest.raises(FabricPlatformModelError, match="identity"):
        load_platform_registry(bad)
