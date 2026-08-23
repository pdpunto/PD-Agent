"""Public validation contract derived from benchmark acceptance metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Mapping

from .models import BenchmarkAcceptanceSpec


PUBLIC_VALIDATION_SCHEMA_VERSION = 1
_REGISTRY_OBSERVATION = "REGISTRY_ENTRY_PRESENT"
_JSON_POINTER_EQUALS = "json_pointer_equals"
_JSON_POINTER_PRESENT = "json_pointer_present"


def _text(value: Any, *, field_name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return [_json_ready(item) for item in sorted(value, key=repr)]
    return value


def _relative_path(value: Any, *, field_name: str) -> str:
    path = _text(value, field_name=field_name).replace("\\", "/")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{field_name} must be a relative repository path")
    return parsed.as_posix()


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicRegistryObservation:
    """User-facing registry fact, without an implementation path."""

    registry_kind: str
    identifier: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_kind", _text(self.registry_kind, field_name="registry_kind"))
        object.__setattr__(self, "identifier", _text(self.identifier, field_name="identifier"))

    def to_dict(self) -> dict[str, Any]:
        return {"registry_kind": self.registry_kind, "identifier": self.identifier}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PublicRegistryObservation":
        return cls(registry_kind=str(data["registry_kind"]), identifier=str(data["identifier"]))


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicJsonPointerAssertion:
    """Public JSON pointer presence or equality requirement."""

    path: str
    kind: str
    value: Any = None

    def __post_init__(self) -> None:
        path = _text(self.path, field_name="path")
        if not path.startswith("/"):
            raise ValueError("JSON pointer path must start with '/'")
        kind = _text(self.kind, field_name="kind")
        if kind not in {_JSON_POINTER_EQUALS, _JSON_POINTER_PRESENT}:
            raise ValueError(f"unsupported public JSON assertion kind: {kind}")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "value", _json_ready(self.value))

    def to_dict(self) -> dict[str, Any]:
        data = {"kind": self.kind, "path": self.path}
        if self.kind == _JSON_POINTER_EQUALS:
            data["value"] = self.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PublicJsonPointerAssertion":
        return cls(
            kind=str(data["kind"]),
            path=str(data["path"]),
            value=data.get("value"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicResourceRequirement:
    """Public resource path and observable assertions."""

    path: str
    resource_type: str = "json"
    assertions: tuple[PublicJsonPointerAssertion, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _relative_path(self.path, field_name="path"))
        resource_type = _text(self.resource_type, field_name="resource_type").casefold()
        if resource_type not in {"json", "text"}:
            raise ValueError(f"unsupported public resource type: {resource_type}")
        object.__setattr__(self, "resource_type", resource_type)
        object.__setattr__(self, "assertions", tuple(self.assertions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "resource_type": self.resource_type,
            "assertions": [assertion.to_dict() for assertion in self.assertions],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PublicResourceRequirement":
        return cls(
            path=str(data["path"]),
            resource_type=str(data.get("resource_type", "json")),
            assertions=tuple(
                PublicJsonPointerAssertion.from_dict(item) for item in data.get("assertions", [])
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicPreservationRequirements:
    """Only user-facing preservation facts, never exact solution layout."""

    mod_id: str | None = None
    preserve_entrypoints: bool = False
    preserve_unrelated_sources: bool = False

    def __post_init__(self) -> None:
        if self.mod_id is not None:
            object.__setattr__(self, "mod_id", _text(self.mod_id, field_name="mod_id"))

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.mod_id is not None:
            data["mod_id"] = self.mod_id
        if self.preserve_entrypoints:
            data["preserve_entrypoints"] = True
        if self.preserve_unrelated_sources:
            data["preserve_unrelated_sources"] = True
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PublicPreservationRequirements":
        return cls(
            mod_id=data.get("mod_id"),
            preserve_entrypoints=bool(data.get("preserve_entrypoints", False)),
            preserve_unrelated_sources=bool(data.get("preserve_unrelated_sources", False)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicValidationContract:
    """Stable public subset of a task acceptance contract."""

    schema_version: int = PUBLIC_VALIDATION_SCHEMA_VERSION
    registry_observations: tuple[PublicRegistryObservation, ...] = ()
    required_minecraft_observations: tuple[PublicRegistryObservation, ...] = ()
    required_resources: tuple[PublicResourceRequirement, ...] = ()
    preservation: PublicPreservationRequirements = field(
        default_factory=PublicPreservationRequirements
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "registry_observations": [item.to_dict() for item in self.registry_observations],
            "required_minecraft_observations": [
                item.to_dict() for item in self.required_minecraft_observations
            ],
            "required_resources": [item.to_dict() for item in self.required_resources],
            "preservation": self.preservation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PublicValidationContract":
        version = int(data.get("schema_version", -1))
        if version != PUBLIC_VALIDATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported public validation schema_version: {version}")
        return cls(
            registry_observations=tuple(
                PublicRegistryObservation.from_dict(item)
                for item in data.get("registry_observations", [])
            ),
            required_minecraft_observations=tuple(
                PublicRegistryObservation.from_dict(item)
                for item in data.get("required_minecraft_observations", [])
            ),
            required_resources=tuple(
                PublicResourceRequirement.from_dict(item)
                for item in data.get("required_resources", [])
            ),
            preservation=PublicPreservationRequirements.from_dict(
                dict(data.get("preservation", {}))
            ),
        )


def _registry_observation(raw: Mapping[str, Any], *, field_name: str) -> PublicRegistryObservation:
    observation_type = _text(raw.get("observation_type", ""), field_name=f"{field_name}.observation_type")
    if observation_type != _REGISTRY_OBSERVATION:
        raise ValueError(f"unsupported public observation type: {observation_type}")
    params = raw.get("observation_params")
    if not isinstance(params, Mapping):
        raise ValueError(f"{field_name}.observation_params must be an object")
    return PublicRegistryObservation(
        registry_kind=str(params.get("registry_kind", "")),
        identifier=str(params.get("identifier", "")),
    )


def _resource(raw: Mapping[str, Any], *, index: int) -> PublicResourceRequirement:
    assertions = raw.get("assertions", [])
    if not isinstance(assertions, (list, tuple)):
        raise ValueError(f"required_resources[{index}].assertions must be a sequence")
    public_assertions = []
    for assertion_index, raw_assertion in enumerate(assertions):
        if not isinstance(raw_assertion, Mapping):
            raise ValueError(
                f"required_resources[{index}].assertions[{assertion_index}] must be an object"
            )
        public_assertions.append(
            PublicJsonPointerAssertion(
                kind=str(raw_assertion.get("kind", "")),
                path=str(raw_assertion.get("path", "")),
                value=raw_assertion.get("value"),
            )
        )
    return PublicResourceRequirement(
        path=str(raw.get("path", "")),
        resource_type=str(raw.get("type", "json")),
        assertions=tuple(public_assertions),
    )


def build_public_validation_contract(
    acceptance: BenchmarkAcceptanceSpec,
) -> PublicValidationContract:
    """Project acceptance metadata into public observable requirements."""

    if not isinstance(acceptance, BenchmarkAcceptanceSpec):
        raise TypeError("acceptance must be BenchmarkAcceptanceSpec")
    spec = acceptance.spec
    if not isinstance(spec, Mapping):
        raise ValueError("acceptance spec must be an object")

    registry_observations = (_registry_observation(spec, field_name="observation"),)
    raw_required = spec.get("required_minecraft_observations", [])
    if not isinstance(raw_required, (list, tuple)):
        raise ValueError("required_minecraft_observations must be a sequence")
    required_observations = tuple(
        _registry_observation(item, field_name=f"required_minecraft_observations[{index}]")
        for index, item in enumerate(raw_required)
        if isinstance(item, Mapping)
    )
    if len(required_observations) != len(raw_required):
        raise ValueError("required_minecraft_observations entries must be objects")

    raw_resources = spec.get("required_resources", [])
    if not isinstance(raw_resources, (list, tuple)):
        raise ValueError("required_resources must be a sequence")
    resources = tuple(
        _resource(item, index=index)
        for index, item in enumerate(raw_resources)
        if isinstance(item, Mapping)
    )
    if len(resources) != len(raw_resources):
        raise ValueError("required_resources entries must be objects")

    raw_preservation = spec.get("preservation_invariants", {})
    if not isinstance(raw_preservation, Mapping):
        raise ValueError("preservation_invariants must be an object")
    return PublicValidationContract(
        registry_observations=registry_observations,
        required_minecraft_observations=required_observations,
        required_resources=resources,
        preservation=PublicPreservationRequirements(
            mod_id=raw_preservation.get("mod_id"),
            preserve_entrypoints="entrypoints" in raw_preservation,
            preserve_unrelated_sources=bool(raw_preservation.get("preserve_unrelated_sources", False)),
        ),
    )
