"""Pure declarative capability primitives for v0.10 M1."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Mapping


CAPABILITY_SCHEMA_VERSION = 1
MAX_CAPABILITY_DEPTH = 8
MAX_CAPABILITY_NODES = 256
MAX_CAPABILITY_STRING_LENGTH = 4096
MAX_CAPABILITY_CONTAINER_LENGTH = 64
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_DECLARATION_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,127}$")
_FORBIDDEN_KEYS = frozenset(
    {"command", "commands", "exec", "executable", "reflection", "shell", "script", "scripts"}
)


class CapabilityModelError(ValueError):
    """Raised when untrusted capability data is malformed or unbounded."""


def _validate_identifier(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise CapabilityModelError(f"{field_name} must be a bounded capability identifier")
    return value


def _validate_error_code(value: Any) -> str:
    if not isinstance(value, str) or not _ERROR_CODE.fullmatch(value):
        raise CapabilityModelError("code must be a bounded planning error code")
    return value


def _validate_declaration_key(value: Any) -> str:
    if not isinstance(value, str) or not _DECLARATION_KEY.fullmatch(value):
        raise CapabilityModelError("declaration_key must be a bounded task-local key")
    return value


def normalize_capability_data(value: Any, *, _depth: int = 0, _nodes: list[int] | None = None) -> Any:
    """Return bounded JSON data with deterministic mapping order.

    Lists remain ordered because declaration order can be semantic; mapping keys
    are sorted by the canonical JSON representation. Python-specific objects,
    executable values and unbounded containers are rejected.
    """
    nodes = _nodes if _nodes is not None else [0]
    if _depth > MAX_CAPABILITY_DEPTH:
        raise CapabilityModelError("capability data exceeds maximum nesting depth")
    nodes[0] += 1
    if nodes[0] > MAX_CAPABILITY_NODES:
        raise CapabilityModelError("capability data exceeds maximum node count")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 2**63 - 1:
            raise CapabilityModelError("integer capability value is out of bounds")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CapabilityModelError("capability numbers must be finite")
        return value
    if isinstance(value, str):
        if len(value) > MAX_CAPABILITY_STRING_LENGTH:
            raise CapabilityModelError("capability string exceeds maximum length")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_CAPABILITY_CONTAINER_LENGTH:
            raise CapabilityModelError("capability mapping exceeds maximum length")
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > MAX_CAPABILITY_STRING_LENGTH:
                raise CapabilityModelError("capability mapping keys must be bounded strings")
            if key in _FORBIDDEN_KEYS:
                raise CapabilityModelError(f"capability data key is not permitted: {key}")
            normalized[key] = normalize_capability_data(item, _depth=_depth + 1, _nodes=nodes)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_CAPABILITY_CONTAINER_LENGTH:
            raise CapabilityModelError("capability sequence exceeds maximum length")
        return [normalize_capability_data(item, _depth=_depth + 1, _nodes=nodes) for item in value]
    raise CapabilityModelError(f"unsupported capability data type: {type(value).__name__}")


def canonical_capability_json(value: Any) -> str:
    """Serialize capability data deterministically and reject non-JSON values."""
    normalized = normalize_capability_data(value)
    try:
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:  # defensive: normalization is the public boundary
        raise CapabilityModelError("capability data is not canonical JSON") from exc


def derive_capability_output_id(instance: "CapabilityInstance", local_output_key: str) -> str:
    """Derive a stable data ID for one declared output of an instance."""
    key = _validate_identifier(local_output_key, field_name="local_output_key")
    payload = {"instance_id": instance.identity, "output_key": key}
    return hashlib.sha256(canonical_capability_json(payload).encode("utf-8")).hexdigest()


def _declaration_tuple(value: Any, *, field_name: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise CapabilityModelError(f"{field_name} must be a sequence")
    return tuple(normalize_capability_data(item) for item in value)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityDefinition:
    """Reusable, executable-free declaration of a capability kind."""

    definition_id: str
    schema_version: int = CAPABILITY_SCHEMA_VERSION
    parameter_schema: Mapping[str, Any] = field(default_factory=dict)
    parameter_defaults: Mapping[str, Any] = field(default_factory=dict)
    prerequisites: tuple[Any, ...] = ()
    requirements: tuple[Any, ...] = ()
    validations: tuple[Any, ...] = ()
    mutation_expectations: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "definition_id", _validate_identifier(self.definition_id, field_name="definition_id"))
        if self.schema_version != CAPABILITY_SCHEMA_VERSION:
            raise CapabilityModelError("unsupported capability schema version")
        for name in ("parameter_schema", "parameter_defaults"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise CapabilityModelError(f"{name} must be a mapping")
            object.__setattr__(self, name, normalize_capability_data(value))
        for name in ("prerequisites", "requirements", "validations", "mutation_expectations"):
            object.__setattr__(self, name, _declaration_tuple(getattr(self, name), field_name=name))

    @property
    def identity(self) -> str:
        return hashlib.sha256(canonical_capability_json(self.to_dict(include_identity=False)).encode("utf-8")).hexdigest()

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        value = {
            "definition_id": self.definition_id,
            "schema_version": self.schema_version,
            "parameter_schema": self.parameter_schema,
            "parameter_defaults": self.parameter_defaults,
            "prerequisites": list(self.prerequisites),
            "requirements": list(self.requirements),
            "validations": list(self.validations),
            "mutation_expectations": list(self.mutation_expectations),
        }
        if include_identity:
            value["identity"] = self.identity
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityInstance:
    """One normalized occurrence of a capability definition."""

    definition_id: str
    definition_schema_version: int = CAPABILITY_SCHEMA_VERSION
    parameters: Mapping[str, Any] = field(default_factory=dict)
    prerequisite_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "definition_id", _validate_identifier(self.definition_id, field_name="definition_id"))
        if self.definition_schema_version != CAPABILITY_SCHEMA_VERSION:
            raise CapabilityModelError("unsupported capability schema version")
        if not isinstance(self.parameters, Mapping):
            raise CapabilityModelError("parameters must be a mapping")
        object.__setattr__(self, "parameters", normalize_capability_data(self.parameters))
        for name in ("prerequisite_refs", "provenance_refs"):
            refs = getattr(self, name)
            if not isinstance(refs, (list, tuple)):
                raise CapabilityModelError(f"{name} must be a sequence")
            normalized = tuple(_validate_identifier(ref, field_name=name) for ref in refs)
            object.__setattr__(self, name, normalized)

    @property
    def identity(self) -> str:
        payload = {
            "definition_id": self.definition_id,
            "definition_schema_version": self.definition_schema_version,
            "parameters": self.parameters,
            "prerequisite_refs": list(self.prerequisite_refs),
        }
        return hashlib.sha256(canonical_capability_json(payload).encode("utf-8")).hexdigest()

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        value = {
            "definition_id": self.definition_id,
            "definition_schema_version": self.definition_schema_version,
            "parameters": self.parameters,
            "prerequisite_refs": list(self.prerequisite_refs),
            "provenance_refs": list(self.provenance_refs),
        }
        if include_identity:
            value["identity"] = self.identity
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class DeclarativeCapabilityReference:
    """Task-local reference resolved by the capability planner."""

    capability_id: str
    declaration_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", _validate_identifier(self.capability_id, field_name="capability_id"))
        object.__setattr__(self, "declaration_key", _validate_declaration_key(self.declaration_key))

    def to_dict(self) -> dict[str, str]:
        return {"capability_id": self.capability_id, "declaration_key": self.declaration_key}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeclarativeCapabilityReference":
        return cls(capability_id=data["capability_id"], declaration_key=data["declaration_key"])


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedCapabilityReference:
    """Authoritative reference containing an instance identity, not the instance."""

    capability_id: str
    declaration_key: str
    instance_identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", _validate_identifier(self.capability_id, field_name="capability_id"))
        object.__setattr__(self, "declaration_key", _validate_declaration_key(self.declaration_key))
        object.__setattr__(self, "instance_identity", _validate_identifier(self.instance_identity, field_name="instance_identity"))

    def to_dict(self) -> dict[str, str]:
        return {
            "capability_id": self.capability_id,
            "declaration_key": self.declaration_key,
            "instance_identity": self.instance_identity,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResolvedCapabilityReference":
        return cls(
            capability_id=data["capability_id"],
            declaration_key=data["declaration_key"],
            instance_identity=data["instance_identity"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityCandidate:
    """Untrusted data candidate; it has no execution authority."""

    definition_id: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    declaration_key: str | None = None
    references: tuple[DeclarativeCapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "definition_id", _validate_identifier(self.definition_id, field_name="definition_id"))
        if not isinstance(self.parameters, Mapping):
            raise CapabilityModelError("parameters must be a mapping")
        object.__setattr__(self, "parameters", normalize_capability_data(self.parameters))
        if self.declaration_key is not None:
            object.__setattr__(self, "declaration_key", _validate_declaration_key(self.declaration_key))
        references = tuple(
            item if isinstance(item, DeclarativeCapabilityReference) else DeclarativeCapabilityReference.from_dict(item)
            for item in self.references
        )
        if len({(item.capability_id, item.declaration_key) for item in references}) != len(references):
            raise CapabilityModelError("references must not contain duplicates")
        object.__setattr__(self, "references", references)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"definition_id": self.definition_id, "parameters": self.parameters}
        if self.declaration_key is not None:
            value["declaration_key"] = self.declaration_key
        if self.references:
            value["references"] = [item.to_dict() for item in self.references]
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanningFailure:
    """Small data-only boundary reserved for the future planner."""

    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _validate_error_code(self.code))
        if not isinstance(self.message, str) or not self.message or len(self.message) > MAX_CAPABILITY_STRING_LENGTH:
            raise CapabilityModelError("planning failure message is invalid")
        if not isinstance(self.details, Mapping):
            raise CapabilityModelError("planning failure details must be a mapping")
        object.__setattr__(self, "details", normalize_capability_data(self.details))

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


__all__ = [
    "CAPABILITY_SCHEMA_VERSION",
    "CapabilityCandidate",
    "CapabilityDefinition",
    "CapabilityInstance",
    "CapabilityModelError",
    "DeclarativeCapabilityReference",
    "PlanningFailure",
    "ResolvedCapabilityReference",
    "canonical_capability_json",
    "derive_capability_output_id",
    "normalize_capability_data",
]
