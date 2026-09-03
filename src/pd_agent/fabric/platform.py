"""Declarative Fabric platform profiles and support resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from pd_agent.brain.models import KnowledgeEnvironment
    from pd_agent.core import FabricEnvironmentConstraints


PLATFORM_SCHEMA_VERSION = 1
_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,127}$")
_TEXT = re.compile(r"^\S(?:.{0,4094}\S)?$")
_FORBIDDEN = re.compile(r"(?i)(?:api[_ -]?key|secret|password|token|bearer|command|executable|shell|script)")
_MANDATORY_SUPPORTED_EVIDENCE = frozenset(
    {
        "PROFILE_DEFINITION",
        "INSPECTION_RESOLUTION",
        "CONTRACT_WIRING",
        "BRAIN_COMPATIBILITY",
        "OFFLINE_BUILD",
    }
)


class FabricPlatformModelError(ValueError):
    """Raised when declarative platform data is invalid."""


class FabricPlatformEvidenceKind(StrEnum):
    PROFILE_DEFINITION = "PROFILE_DEFINITION"
    INSPECTION_RESOLUTION = "INSPECTION_RESOLUTION"
    CONTRACT_WIRING = "CONTRACT_WIRING"
    BRAIN_COMPATIBILITY = "BRAIN_COMPATIBILITY"
    BOOTSTRAP = "BOOTSTRAP"
    IMPORT = "IMPORT"
    OFFLINE_BUILD = "OFFLINE_BUILD"


class FabricMappingFamily(StrEnum):
    UNOBFUSCATED = "UNOBFUSCATED"
    OBFUSCATED_REMAPPED = "OBFUSCATED_REMAPPED"


class FabricPlatformSupportStatus(StrEnum):
    TARGET = "TARGET"
    SUPPORTED = "SUPPORTED"
    RETIRED = "RETIRED"


class FabricPlatformResolutionStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _TEXT.fullmatch(value):
        raise FabricPlatformModelError(f"{field_name} must be a non-empty bounded string")
    if _FORBIDDEN.search(value):
        raise FabricPlatformModelError(f"{field_name} contains prohibited content")
    return value


def _id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise FabricPlatformModelError(f"{field_name} must be a bounded identifier")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricPlatformEvidence:
    """Stable, non-executable evidence reference for a platform claim."""

    evidence_id: str
    kind: FabricPlatformEvidenceKind
    reference: str
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _id(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "kind", FabricPlatformEvidenceKind(str(self.kind)))
        reference = _text(self.reference, "reference")
        if Path(reference).is_absolute() or "\\" in reference:
            raise FabricPlatformModelError("evidence reference must not be an absolute machine path")
        if not isinstance(self.required, bool):
            raise FabricPlatformModelError("required must be boolean")
        object.__setattr__(self, "reference", reference)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind.value,
            "reference": self.reference,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricPlatformEvidence":
        return cls(
            evidence_id=data["evidence_id"],
            kind=data["kind"],
            reference=data["reference"],
            required=data.get("required", True),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricPlatformProfile:
    """Immutable declarative description of one concrete Fabric platform."""

    platform_id: str
    minecraft_version: str
    loader_version: str
    fabric_api_version: str
    loom_version: str
    java_version: str
    mapping_family: FabricMappingFamily
    mappings_namespace: str | None = None
    mappings_version: str | None = None
    support_status: FabricPlatformSupportStatus = FabricPlatformSupportStatus.TARGET
    evidence: tuple[FabricPlatformEvidence, ...] = ()
    schema_version: int = PLATFORM_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PLATFORM_SCHEMA_VERSION:
            raise FabricPlatformModelError("unsupported platform schema version")
        object.__setattr__(self, "platform_id", _id(self.platform_id, "platform_id"))
        for name in ("minecraft_version", "loader_version", "fabric_api_version", "loom_version", "java_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "mapping_family", FabricMappingFamily(str(self.mapping_family)))
        object.__setattr__(self, "support_status", FabricPlatformSupportStatus(str(self.support_status)))
        namespace = _optional_text(self.mappings_namespace, "mappings_namespace")
        version = _optional_text(self.mappings_version, "mappings_version")
        if self.mapping_family is FabricMappingFamily.UNOBFUSCATED and (namespace is not None or version is not None):
            raise FabricPlatformModelError("UNOBFUSCATED profiles must not declare mappings")
        if self.mapping_family is FabricMappingFamily.OBFUSCATED_REMAPPED and (namespace is None or version is None):
            raise FabricPlatformModelError("OBFUSCATED_REMAPPED profiles require mappings")
        object.__setattr__(self, "mappings_namespace", namespace)
        object.__setattr__(self, "mappings_version", version)
        values = tuple(item if isinstance(item, FabricPlatformEvidence) else FabricPlatformEvidence.from_dict(item) for item in self.evidence)
        if len({item.evidence_id for item in values}) != len(values):
            raise FabricPlatformModelError("evidence IDs must be unique")
        values = tuple(sorted(values, key=lambda item: item.evidence_id))
        object.__setattr__(self, "evidence", values)
        if self.support_status is FabricPlatformSupportStatus.SUPPORTED and not self.evidence_gate_passes:
            raise FabricPlatformModelError("SUPPORTED profile lacks mandatory evidence")

    @property
    def evidence_gate_passes(self) -> bool:
        kinds = {item.kind.value for item in self.evidence if item.required}
        return _MANDATORY_SUPPORTED_EVIDENCE.issubset(kinds)

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "platform_id": self.platform_id,
            "minecraft_version": self.minecraft_version,
            "loader_version": self.loader_version,
            "fabric_api_version": self.fabric_api_version,
            "loom_version": self.loom_version,
            "java_version": self.java_version,
            "mapping_family": self.mapping_family.value,
            "mappings_namespace": self.mappings_namespace,
            "mappings_version": self.mappings_version,
            "support_status": self.support_status.value,
            "evidence": [item.to_dict() for item in self.evidence],
        }
        if include_identity:
            payload["platform_identity"] = self.identity
        return payload

    @property
    def identity(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict(include_identity=False)).encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricPlatformProfile":
        profile = cls(**{key: data[key] for key in (
            "platform_id", "minecraft_version", "loader_version", "fabric_api_version",
            "loom_version", "java_version", "mapping_family", "mappings_namespace",
            "mappings_version", "support_status", "evidence", "schema_version",
        ) if key in data})
        declared = data.get("platform_identity")
        if declared is not None and declared != profile.identity:
            raise FabricPlatformModelError("platform identity mismatch")
        return profile


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricPlatformObservation:
    """Normalized facts supplied by an observer; never parses a workspace."""

    minecraft_version: str | None = None
    loader_version: str | None = None
    fabric_api_version: str | None = None
    loom_version: str | None = None
    java_version: str | None = None
    mappings_namespace: str | None = None
    mappings_version: str | None = None
    mapping_family: FabricMappingFamily | None = None
    missing_facts: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("minecraft_version", "loader_version", "fabric_api_version", "loom_version", "java_version", "mappings_namespace", "mappings_version"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        if self.mapping_family is not None:
            object.__setattr__(self, "mapping_family", FabricMappingFamily(str(self.mapping_family)))
        for name in ("missing_facts", "conflicts", "issues"):
            values = tuple(_text(item, name) for item in getattr(self, name))
            object.__setattr__(self, name, tuple(sorted(set(values))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "minecraft_version": self.minecraft_version,
            "loader_version": self.loader_version,
            "fabric_api_version": self.fabric_api_version,
            "loom_version": self.loom_version,
            "java_version": self.java_version,
            "mappings_namespace": self.mappings_namespace,
            "mappings_version": self.mappings_version,
            "mapping_family": self.mapping_family.value if self.mapping_family else None,
            "missing_facts": list(self.missing_facts),
            "conflicts": list(self.conflicts),
            "issues": list(self.issues),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricPlatformObservation":
        return cls(**{key: data.get(key) for key in (
            "minecraft_version", "loader_version", "fabric_api_version", "loom_version",
            "java_version", "mappings_namespace", "mappings_version", "mapping_family",
            "missing_facts", "conflicts", "issues",
        ) if key in data})


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricPlatformResolution:
    """Immutable data-only result of support resolution."""

    status: FabricPlatformResolutionStatus
    observation: FabricPlatformObservation
    selected_profile: FabricPlatformProfile | None = None
    reason_code: str = ""
    conflicts: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", FabricPlatformResolutionStatus(str(self.status)))
        if self.status is FabricPlatformResolutionStatus.SUPPORTED and (
            self.selected_profile is None
            or self.selected_profile.support_status is not FabricPlatformSupportStatus.SUPPORTED
            or not self.selected_profile.evidence_gate_passes
        ):
            raise FabricPlatformModelError("SUPPORTED resolution requires one evidence-valid SUPPORTED profile")
        if self.status is not FabricPlatformResolutionStatus.SUPPORTED and self.selected_profile is not None:
            raise FabricPlatformModelError("non-supported resolution cannot select an executable profile")
        reason_code = self.reason_code or "UNSPECIFIED"
        if not isinstance(reason_code, str) or not _CODE.fullmatch(reason_code):
            raise FabricPlatformModelError("reason_code must be a stable uppercase code")
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "conflicts", tuple(sorted(set(self.conflicts))))
        object.__setattr__(self, "evidence_refs", tuple(sorted(set(self.evidence_refs))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "observation": self.observation.to_dict(),
            "selected_profile": self.selected_profile.to_dict() if self.selected_profile else None,
            "reason_code": self.reason_code,
            "conflicts": list(self.conflicts),
            "evidence_refs": list(self.evidence_refs),
        }


class FabricSupportRegistry:
    """Immutable local registry for declarative platform support profiles."""

    __slots__ = ("_profiles", "_sealed")

    def __init__(self, profiles: tuple[FabricPlatformProfile, ...] | list[FabricPlatformProfile] = ()) -> None:
        values = tuple(profiles)
        if not all(isinstance(profile, FabricPlatformProfile) for profile in values):
            raise FabricPlatformModelError("registry accepts FabricPlatformProfile values only")
        ids = [profile.platform_id for profile in values]
        if len(set(ids)) != len(ids):
            raise FabricPlatformModelError("duplicate platform_id")
        object.__setattr__(self, "_profiles", tuple(sorted(values, key=lambda profile: profile.platform_id)))
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("FabricSupportRegistry is immutable")
        object.__setattr__(self, name, value)

    def get(self, platform_id: str) -> FabricPlatformProfile:
        for profile in self._profiles:
            if profile.platform_id == platform_id:
                return profile
        raise KeyError(platform_id)

    def list_profiles(self) -> tuple[FabricPlatformProfile, ...]:
        return self._profiles

    def snapshot(self) -> Mapping[str, FabricPlatformProfile]:
        return MappingProxyType({profile.platform_id: profile for profile in self._profiles})

    def resolve(self, observation: FabricPlatformObservation) -> FabricPlatformResolution:
        if not isinstance(observation, FabricPlatformObservation):
            raise FabricPlatformModelError("resolve requires normalized FabricPlatformObservation")
        if observation.conflicts:
            return FabricPlatformResolution(
                status=FabricPlatformResolutionStatus.CONFLICT,
                observation=observation,
                reason_code="OBSERVATION_CONFLICT",
                conflicts=observation.conflicts,
            )
        matches = tuple(profile for profile in self._profiles if self._matches_observed(profile, observation))
        incomplete = tuple(profile for profile in matches if self._missing_profile_facts(profile, observation))
        complete = tuple(profile for profile in matches if profile not in incomplete)
        if incomplete and not complete:
            return FabricPlatformResolution(
                status=FabricPlatformResolutionStatus.UNKNOWN,
                observation=observation,
                reason_code="REQUIRED_FACT_MISSING",
            )
        supported = tuple(profile for profile in complete if profile.support_status is FabricPlatformSupportStatus.SUPPORTED and profile.evidence_gate_passes)
        if len(supported) > 1:
            return FabricPlatformResolution(
                status=FabricPlatformResolutionStatus.CONFLICT,
                observation=observation,
                reason_code="MULTIPLE_SUPPORTED_PROFILES",
                conflicts=tuple(profile.platform_id for profile in supported),
            )
        if len(supported) == 1:
            return FabricPlatformResolution(
                status=FabricPlatformResolutionStatus.SUPPORTED,
                observation=observation,
                selected_profile=supported[0],
                reason_code="SUPPORTED_PROFILE_MATCH",
                evidence_refs=tuple(item.reference for item in supported[0].evidence if item.required),
            )
        if incomplete:
            return FabricPlatformResolution(status=FabricPlatformResolutionStatus.UNKNOWN, observation=observation, reason_code="REQUIRED_FACT_MISSING")
        return FabricPlatformResolution(status=FabricPlatformResolutionStatus.UNSUPPORTED, observation=observation, reason_code="NO_SUPPORTED_PROFILE")

    @staticmethod
    def _matches_observed(profile: FabricPlatformProfile, observation: FabricPlatformObservation) -> bool:
        for name in ("minecraft_version", "loader_version", "fabric_api_version", "loom_version", "java_version", "mappings_namespace", "mappings_version"):
            observed = getattr(observation, name)
            expected = getattr(profile, name)
            if observed is not None and observed != expected:
                return False
        return observation.mapping_family is None or observation.mapping_family is profile.mapping_family

    @staticmethod
    def _missing_profile_facts(profile: FabricPlatformProfile, observation: FabricPlatformObservation) -> tuple[str, ...]:
        # Java and mapping-family metadata can be profile/evidence requirements
        # even when the workspace inspector cannot observe them independently.
        required = ["minecraft_version", "loader_version", "loom_version"]
        if profile.mapping_family is FabricMappingFamily.UNOBFUSCATED:
            required.extend(("java_version", "mapping_family"))
        if profile.mapping_family is FabricMappingFamily.OBFUSCATED_REMAPPED:
            required.append("mappings_version")
        return tuple(name for name in required if name in observation.missing_facts or getattr(observation, name) is None)


def platform_observation_from_inspection(inspection: Any) -> FabricPlatformObservation:
    """Normalize one real Fabric inspection without inspecting the workspace again."""
    required_attributes = ("detected_versions", "issues")
    if not all(hasattr(inspection, name) for name in required_attributes):
        raise FabricPlatformModelError("inspection result is required")
    detected = inspection.detected_versions

    def value(*keys: str) -> str | None:
        for key in keys:
            item = detected.get(key)
            if item is not None:
                return item.value
        return None

    versions = {
        "minecraft_version": value("minecraft", "minecraft_version"),
        "loader_version": value("loader", "loader_version", "fabric_loader_version"),
        "fabric_api_version": value("fabric_api", "fabric_api_version"),
        "loom_version": value("loom"),
        "mappings_version": value("mappings", "yarn_version"),
    }
    java_version = value("java", "java_version")
    mapping_family_value = value("mapping_family")
    mapping_namespace = value("mappings_namespace")
    mapping_family = FabricMappingFamily(mapping_family_value) if mapping_family_value else None
    if mapping_family is FabricMappingFamily.UNOBFUSCATED:
        versions["mappings_version"] = None
        mapping_namespace = None
    missing = tuple(
        name for name, item in versions.items()
        if item is None and not (
            mapping_family is FabricMappingFamily.UNOBFUSCATED
            and name == "mappings_version"
        )
    )
    if java_version is None:
        missing += ("java_version",)
    if mapping_family is None:
        missing += ("mapping_family",)
    elif mapping_family is FabricMappingFamily.OBFUSCATED_REMAPPED and mapping_namespace is None:
        missing += ("mappings_namespace",)
    issues = tuple(str(item) for item in inspection.issues)
    material_tokens = ("ambiguous", "conflict", "contradict")
    conflicts = tuple(sorted(set(item for item in issues if any(token in item.casefold() for token in material_tokens))))
    return FabricPlatformObservation(
        **versions,
        java_version=java_version,
        mappings_namespace=mapping_namespace,
        mapping_family=mapping_family,
        missing_facts=missing,
        conflicts=conflicts,
        issues=issues,
    )


def fabric_environment_constraints_from_profile(profile: FabricPlatformProfile) -> FabricEnvironmentConstraints:
    """Adapt a resolved profile to the existing task environment contract."""
    if not isinstance(profile, FabricPlatformProfile):
        raise FabricPlatformModelError("profile must be FabricPlatformProfile")
    from pd_agent.core import FabricEnvironmentConstraints

    return FabricEnvironmentConstraints(
        minecraft_version=profile.minecraft_version,
        loader_version=profile.loader_version,
        fabric_api_version=profile.fabric_api_version,
        yarn_version=profile.mappings_version,
        java_version=profile.java_version,
        platform="fabric",
        extra={
            "loom_version": profile.loom_version,
            "mapping_family": profile.mapping_family.value,
            "mappings_namespace": profile.mappings_namespace,
            "platform_id": profile.platform_id,
        },
    )


def knowledge_environment_from_constraints(constraints: FabricEnvironmentConstraints) -> KnowledgeEnvironment:
    """Adapt existing contract constraints to the sole Brain environment model."""
    from pd_agent.core import FabricEnvironmentConstraints

    if not isinstance(constraints, FabricEnvironmentConstraints):
        raise FabricPlatformModelError("constraints must be FabricEnvironmentConstraints")
    from pd_agent.brain.models import KnowledgeEnvironment

    return KnowledgeEnvironment(
        minecraft_version=constraints.minecraft_version,
        loader_version=constraints.loader_version,
        loom_version=constraints.extra.get("loom_version"),
        mappings_namespace=constraints.extra.get("mappings_namespace"),
        mappings_version=constraints.yarn_version,
        fabric_api_version=constraints.fabric_api_version,
        java_version=constraints.java_version,
    )


def knowledge_environment_from_profile(profile: FabricPlatformProfile) -> KnowledgeEnvironment:
    """Adapt a profile to Brain without resolving support or inspecting files."""
    return knowledge_environment_from_constraints(fabric_environment_constraints_from_profile(profile))


def load_platform_profiles(path: Path) -> tuple[FabricPlatformProfile, ...]:
    """Load and validate a source-controlled JSON profile declaration."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FabricPlatformModelError("platform profile document is unreadable or malformed") from exc
    if not isinstance(data, Mapping) or data.get("schema_version") != PLATFORM_SCHEMA_VERSION or not isinstance(data.get("profiles"), list):
        raise FabricPlatformModelError("invalid platform profile document schema")
    try:
        return tuple(FabricPlatformProfile.from_dict(item) for item in data["profiles"])
    except (KeyError, TypeError) as exc:
        raise FabricPlatformModelError("invalid platform profile declaration") from exc


def load_platform_registry(path: Path) -> FabricSupportRegistry:
    return FabricSupportRegistry(load_platform_profiles(path))


__all__ = [
    "FabricMappingFamily",
    "FabricPlatformEvidence",
    "FabricPlatformEvidenceKind",
    "FabricPlatformModelError",
    "FabricPlatformObservation",
    "FabricPlatformProfile",
    "FabricPlatformResolution",
    "FabricPlatformResolutionStatus",
    "FabricPlatformSupportStatus",
    "FabricSupportRegistry",
    "PLATFORM_SCHEMA_VERSION",
    "load_platform_profiles",
    "load_platform_registry",
    "platform_observation_from_inspection",
    "fabric_environment_constraints_from_profile",
    "knowledge_environment_from_constraints",
    "knowledge_environment_from_profile",
]
