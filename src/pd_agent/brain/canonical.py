"""Canonical v0.7 knowledge records and pack manifests."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import math
from typing import Any, Mapping

from .models import KnowledgeEnvironment, KnowledgeProvenance, KnowledgeType, SourceAuthority


class KnowledgePolicy(StrEnum):
    """Distribution policy carried by canonical knowledge metadata."""

    REDISTRIBUTABLE = "REDISTRIBUTABLE"
    LOCALLY_MATERIALIZABLE = "LOCALLY_MATERIALIZABLE"
    FETCH_CACHE_REFERENCE_ONLY = "FETCH_CACHE_REFERENCE_ONLY"


class KnowledgePackState(StrEnum):
    """Representable pack states; lifecycle transitions belong to I3."""

    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
    FROZEN = "FROZEN"
    SUPERSEDED = "SUPERSEDED"


_NORMATIVE_TYPES = frozenset(
    {
        KnowledgeType.SYMBOL,
        KnowledgeType.API,
        KnowledgeType.CONCEPT,
        KnowledgeType.PATTERN,
        KnowledgeType.EXAMPLE,
        KnowledgeType.VERSION_CHANGE,
        KnowledgeType.CAPABILITY,
        KnowledgeType.DIAGNOSTIC,
    }
)


def _json_safe(value: Any, *, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} has a non-string key")
            result[key] = _json_safe(child, path=f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(child, path=f"{path}[{index}]") for index, child in enumerate(value)]
    raise TypeError(f"{path} is not JSON-compatible: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data deterministically as UTF-8 JSON text."""
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def normalize_logical_path(value: str) -> str:
    """Normalize separators for logical path metadata without touching URLs."""
    if "://" in value:
        return value
    return value.replace("\\", "/")


def _ordered(values: tuple[Any, ...] | list[Any]) -> list[Any]:
    return sorted((_json_safe(value) for value in values), key=canonical_json)


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class KnowledgeRecord:
    """Immutable canonical unit for a v0.7 knowledge pack."""

    record_id: str
    kind: KnowledgeType
    content: Any
    environment: KnowledgeEnvironment
    provenance: KnowledgeProvenance
    authority: SourceAuthority
    version_sensitive: bool = True
    capability: str | None = None
    related_symbols: tuple[str, ...] = ()
    relations: tuple[Mapping[str, Any], ...] = ()
    license_policy: KnowledgePolicy = KnowledgePolicy.LOCALLY_MATERIALIZABLE
    integrity: Mapping[str, Any] = field(default_factory=dict)
    source_revision: str | None = None

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id must not be empty")
        if not isinstance(self.kind, KnowledgeType) or self.kind not in _NORMATIVE_TYPES:
            raise ValueError("KnowledgeRecord kind must be a normative v0.7 type")
        if not isinstance(self.environment, KnowledgeEnvironment):
            raise TypeError("environment must be a KnowledgeEnvironment")
        _json_safe(self.content, path="$.content")
        _json_safe(self.relations, path="$.relations")
        _json_safe(self.integrity, path="$.integrity")
        if not isinstance(self.license_policy, KnowledgePolicy):
            raise TypeError("license_policy must be a KnowledgePolicy")

    def _payload(self) -> dict[str, Any]:
        provenance = self.provenance.to_dict()
        provenance.pop("locator", None)
        return {
            "schema_version": "v0.7",
            "record_id": self.record_id,
            "kind": self.kind.value,
            "content": _json_safe(self.content),
            "environment": self.environment.to_dict(),
            "version_sensitive": self.version_sensitive,
            "capability": self.capability,
            "related_symbols": sorted(self.related_symbols),
            "relations": _ordered(list(self.relations)),
            "provenance": provenance,
            "authority": self.authority.value,
            "source_revision": self.source_revision,
            "license_policy": self.license_policy.value,
            "integrity": _json_safe(self.integrity),
        }

    def identity(self) -> str:
        return _sha256(self._payload())

    def to_dict(self) -> dict[str, Any]:
        data = self._payload()
        data["record_identity"] = self.identity()
        data["provenance"] = self.provenance.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeRecord":
        record = cls(
            record_id=str(data["record_id"]),
            kind=KnowledgeType(str(data["kind"])),
            content=data["content"],
            environment=KnowledgeEnvironment.from_dict(dict(data["environment"])),
            provenance=KnowledgeProvenance.from_dict(dict(data["provenance"])),
            authority=SourceAuthority(str(data["authority"])),
            version_sensitive=bool(data.get("version_sensitive", True)),
            capability=data.get("capability"),
            related_symbols=tuple(str(item) for item in data.get("related_symbols", [])),
            relations=tuple(dict(item) for item in data.get("relations", [])),
            license_policy=KnowledgePolicy(str(data.get("license_policy", KnowledgePolicy.LOCALLY_MATERIALIZABLE))),
            integrity=dict(data.get("integrity", {})),
            source_revision=data.get("source_revision"),
        )
        declared = data.get("record_identity")
        if declared is not None and declared != record.identity():
            raise ValueError("record identity mismatch")
        return record


@dataclass(frozen=True, slots=True)
class KnowledgePackManifest:
    """Canonical manifest for a reproducible collection of records."""

    environment: KnowledgeEnvironment
    source_set: tuple[Mapping[str, Any], ...]
    record_inventory: tuple[Mapping[str, Any], ...]
    schema_version: str = "v0.7"
    state: KnowledgePackState = KnowledgePackState.DRAFT
    generated_metadata: Mapping[str, Any] = field(default_factory=dict)
    license_policy: KnowledgePolicy = KnowledgePolicy.LOCALLY_MATERIALIZABLE
    integrity: Mapping[str, Any] = field(default_factory=dict)
    derived_index_metadata: Mapping[str, Any] = field(default_factory=dict)
    pack_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != "v0.7":
            raise ValueError("unsupported KnowledgePack schema_version")
        if not isinstance(self.environment, KnowledgeEnvironment):
            raise TypeError("environment must be a KnowledgeEnvironment")
        for name, value in (("source_set", self.source_set), ("record_inventory", self.record_inventory),
                            ("generated_metadata", self.generated_metadata), ("integrity", self.integrity),
                            ("derived_index_metadata", self.derived_index_metadata)):
            _json_safe(value, path=f"$.{name}")
        if not isinstance(self.state, KnowledgePackState):
            raise TypeError("state must be a KnowledgePackState")
        if not isinstance(self.license_policy, KnowledgePolicy):
            raise TypeError("license_policy must be a KnowledgePolicy")
        calculated = self.identity()
        if self.pack_id is not None and self.pack_id != calculated:
            raise ValueError("pack_id does not match canonical manifest identity")
        object.__setattr__(self, "pack_id", calculated)

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "environment": self.environment.to_dict(),
            "source_set": _ordered(list(self.source_set)),
            "record_inventory": _ordered(list(self.record_inventory)),
            "license_policy": self.license_policy.value,
        }

    def identity(self) -> str:
        return _sha256(self._identity_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._identity_payload(),
            "pack_id": self.pack_id,
            "state": self.state.value,
            "generated_metadata": _json_safe(self.generated_metadata),
            "integrity": _json_safe(self.integrity),
            "derived_index_metadata": _json_safe(self.derived_index_metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgePackManifest":
        return cls(
            environment=KnowledgeEnvironment.from_dict(dict(data["environment"])),
            source_set=tuple(dict(item) for item in data.get("source_set", [])),
            record_inventory=tuple(dict(item) for item in data.get("record_inventory", [])),
            schema_version=str(data.get("schema_version", "v0.7")),
            state=KnowledgePackState(str(data.get("state", KnowledgePackState.DRAFT))),
            generated_metadata=dict(data.get("generated_metadata", {})),
            license_policy=KnowledgePolicy(str(data.get("license_policy", KnowledgePolicy.LOCALLY_MATERIALIZABLE))),
            integrity=dict(data.get("integrity", {})),
            derived_index_metadata=dict(data.get("derived_index_metadata", {})),
            pack_id=data.get("pack_id"),
        )
