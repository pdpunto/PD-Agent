"""Minecraft test harness contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


_MOD_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROFILE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_SAFE_PARAMETER_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_UNSAFE_PARAMETER_KEYS = {
    "arbitrary_command",
    "code",
    "command",
    "executable",
    "file",
    "nbt",
    "path",
    "reflection",
    "script",
    "world_root",
}
_ITEM_COMPONENT_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*:[a-z0-9/._-]+$")
_CONTROLLED_HOPPER_POS = (8, 64, 8)


def _controlled_position(selector: Mapping[str, Any], *, kind: str, selector_kind: str) -> None:
    if not isinstance(selector, Mapping) or set(selector) != {"kind", "fixture", "pos"}:
        raise ValueError(f"{kind} selector must declare kind, fixture and pos")
    if selector.get("kind") != selector_kind or selector.get("fixture") != "hopper":
        raise ValueError(f"{kind} selector must target the controlled hopper fixture")
    position = selector.get("pos")
    if position != list(_CONTROLLED_HOPPER_POS) and position != _CONTROLLED_HOPPER_POS:
        raise ValueError(f"{kind} selector position is outside the authorized fixture")


def validate_block_entity_profile(
    selector: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    """Validate the closed vanilla hopper BlockEntity profile used by I3."""

    _controlled_position(selector, kind="BLOCK_ENTITY_STATE", selector_kind="harness_block_entity")
    if not isinstance(parameters, Mapping):
        raise ValueError("BLOCK_ENTITY_STATE parameters must be an object")
    allowed = {"block_entity_id", "mutation"}
    unknown = set(parameters) - allowed
    if unknown:
        raise ValueError(f"BLOCK_ENTITY_STATE parameters contain unknown fields: {sorted(unknown)!r}")
    block_entity_id = parameters.get("block_entity_id", "minecraft:hopper")
    if block_entity_id != "minecraft:hopper":
        raise ValueError("BLOCK_ENTITY_STATE only supports minecraft:hopper")
    if not isinstance(parameters.get("mutation", True), bool):
        raise ValueError("BLOCK_ENTITY_STATE mutation must be boolean")


def validate_inventory_profile(
    selector: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    """Validate the fixed five-slot hopper inventory profile used by I3."""

    _controlled_position(selector, kind="INVENTORY_STATE", selector_kind="harness_inventory")
    if not isinstance(parameters, Mapping):
        raise ValueError("INVENTORY_STATE parameters must be an object")
    allowed = {"slot", "item_id", "count", "mutation"}
    unknown = set(parameters) - allowed
    if unknown:
        raise ValueError(f"INVENTORY_STATE parameters contain unknown fields: {sorted(unknown)!r}")
    slot = parameters.get("slot", 0)
    if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot < 5:
        raise ValueError("INVENTORY_STATE slot must be an integer from 0 through 4")
    if parameters.get("item_id", "minecraft:diamond") != "minecraft:diamond":
        raise ValueError("INVENTORY_STATE only supports minecraft:diamond")
    count = parameters.get("count", 5)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 64:
        raise ValueError("INVENTORY_STATE count must be an integer from 1 through 64")
    if not isinstance(parameters.get("mutation", True), bool):
        raise ValueError("INVENTORY_STATE mutation must be boolean")


def validate_item_component_profile(
    selector: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    """Validate the closed controlled-stack profile used by I2."""

    if not isinstance(selector, Mapping) or set(selector) != {"kind", "item_id"}:
        raise ValueError("ITEM_COMPONENT_STATE selector must declare kind and item_id")
    if selector.get("kind") != "harness_stack":
        raise ValueError("ITEM_COMPONENT_STATE selector kind must be harness_stack")
    item_id = selector.get("item_id")
    if not isinstance(item_id, str) or not _ITEM_COMPONENT_ID_RE.fullmatch(item_id):
        raise ValueError("ITEM_COMPONENT_STATE item_id must be a namespaced identifier")

    if not isinstance(parameters, Mapping):
        raise ValueError("ITEM_COMPONENT_STATE parameters must be an object")
    allowed = {"component_id", "round_trip"}
    unknown = set(parameters) - allowed
    if unknown:
        raise ValueError(f"ITEM_COMPONENT_STATE parameters contain unknown fields: {sorted(unknown)!r}")
    component_id = parameters.get("component_id")
    if not isinstance(component_id, str) or not _ITEM_COMPONENT_ID_RE.fullmatch(component_id):
        raise ValueError("ITEM_COMPONENT_STATE component_id must be a namespaced identifier")
    round_trip = parameters.get("round_trip", False)
    if not isinstance(round_trip, bool):
        raise ValueError("ITEM_COMPONENT_STATE round_trip must be boolean")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _closed_json(value: Any, *, field_name: str, reject_unsafe_keys: bool = True) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not _SAFE_PARAMETER_KEY_RE.fullmatch(key):
                raise ValueError(f"{field_name} contains an invalid key")
            if reject_unsafe_keys and key.casefold() in _UNSAFE_PARAMETER_KEYS:
                raise ValueError(f"{field_name} contains a prohibited key: {key}")
            result[key] = _closed_json(
                item,
                field_name=f"{field_name}.{key}",
                reject_unsafe_keys=reject_unsafe_keys,
            )
        return result
    if isinstance(value, (tuple, list)):
        return [
            _closed_json(
                item,
                field_name=field_name,
                reject_unsafe_keys=reject_unsafe_keys,
            )
            for item in value
        ]
    raise ValueError(f"{field_name} must contain JSON-compatible values")


def _identity(name: str, value: object) -> str:
    text = _non_empty_text(name, value)
    if not _IDENTITY_RE.fullmatch(text):
        raise ValueError(f"invalid {name}: {text!r}")
    return text


def _optional_identity(name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _identity(name, value)


def _profile(value: object) -> str:
    text = _non_empty_text("profile", value).casefold()
    if not _PROFILE_RE.fullmatch(text):
        raise ValueError(f"invalid profile: {text!r}")
    return text


def _strict_mapping(data: Mapping[str, Any], *, model: str, allowed: set[str]) -> None:
    if not isinstance(data, Mapping):
        raise ValueError(f"{model} must be an object")
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"{model} contains unknown fields: {sorted(unknown)!r}")


def _non_empty_text(name: str, value: object) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{name} cannot be empty")
    return text


def _normalize_path(value: Path | str) -> Path:
    path = Path(value).expanduser()
    if not str(path):
        raise ValueError("target_jar cannot be empty")
    return path


def _normalize_runtime_mod_jar(value: Path | str) -> Path:
    path = Path(value).expanduser()
    if not str(path):
        raise ValueError("runtime_mod_jars cannot contain empty paths")
    return path


def _validate_mod_id(value: object) -> str:
    mod_id = _non_empty_text("target_mod_id", value)
    if not _MOD_ID_RE.fullmatch(mod_id):
        raise ValueError(f"invalid target_mod_id: {mod_id!r}")
    return mod_id


class MinecraftObservationType(StrEnum):
    """Supported runtime observation contracts."""

    LEGACY_BLOCK_STATE = "LEGACY_BLOCK_STATE"
    REGISTRY_ENTRY_PRESENT = "REGISTRY_ENTRY_PRESENT"
    ITEM_COMPONENT_STATE = "ITEM_COMPONENT_STATE"
    BLOCK_ENTITY_STATE = "BLOCK_ENTITY_STATE"
    INVENTORY_STATE = "INVENTORY_STATE"
    TAG_MEMBERSHIP = "TAG_MEMBERSHIP"
    RECIPE_MATCH = "RECIPE_MATCH"
    LOOT_RESULT = "LOOT_RESULT"


class MinecraftObservationStatus(StrEnum):
    """Closed status set for an observation result."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"


class MinecraftEvidenceKind(StrEnum):
    """Evidence categories available to later runtime contracts."""

    OBSERVATION = "observation"
    ACTION = "action"
    PHASE = "phase"
    PROCESS = "process"
    WORLD = "world"
    SCENARIO = "scenario"


@dataclass(frozen=True, slots=True)
class MinecraftEvidenceReference:
    """Immutable reference to a persisted evidence payload."""

    kind: MinecraftEvidenceKind
    ref: str
    phase: str | None = None
    process_id: str | None = None
    world_id: str | None = None
    scenario_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", MinecraftEvidenceKind(str(self.kind)))
        ref = _non_empty_text("evidence ref", self.ref)
        if Path(ref).is_absolute() or ".." in Path(ref).parts:
            raise ValueError("evidence ref must be relative and confined")
        object.__setattr__(self, "ref", ref.replace("\\", "/"))
        object.__setattr__(self, "phase", _optional_identity("phase", self.phase))
        object.__setattr__(self, "process_id", _optional_identity("process_id", self.process_id))
        object.__setattr__(self, "world_id", _optional_identity("world_id", self.world_id))
        object.__setattr__(self, "scenario_id", _optional_identity("scenario_id", self.scenario_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ref": self.ref,
            "phase": self.phase,
            "process_id": self.process_id,
            "world_id": self.world_id,
            "scenario_id": self.scenario_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftEvidenceReference":
        _strict_mapping(
            data,
            model="MinecraftEvidenceReference",
            allowed={"kind", "ref", "phase", "process_id", "world_id", "scenario_id"},
        )
        required = {"kind", "ref"} - set(data)
        if required:
            raise ValueError(f"MinecraftEvidenceReference missing fields: {sorted(required)!r}")
        return cls(
            kind=MinecraftEvidenceKind(str(data["kind"])),
            ref=str(data["ref"]),
            phase=data.get("phase"),
            process_id=data.get("process_id"),
            world_id=data.get("world_id"),
            scenario_id=data.get("scenario_id"),
        )


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    """Closed provider-neutral request envelope for future observations."""

    observation_id: str
    observation_type: MinecraftObservationType
    profile: str
    selector: Mapping[str, Any]
    expected: Any
    parameters: Mapping[str, Any] = field(default_factory=dict)
    phase: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _identity("observation_id", self.observation_id))
        object.__setattr__(self, "observation_type", MinecraftObservationType(str(self.observation_type)))
        object.__setattr__(self, "profile", _profile(self.profile))
        selector = _closed_json(self.selector, field_name="selector")
        if not isinstance(selector, dict) or not selector:
            raise ValueError("selector must be a non-empty object")
        object.__setattr__(self, "selector", selector)
        parameters = _closed_json(self.parameters, field_name="parameters")
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(
            self,
            "expected",
            _closed_json(self.expected, field_name="expected", reject_unsafe_keys=False),
        )
        object.__setattr__(self, "phase", _optional_identity("phase", self.phase))
        metadata = _closed_json(self.metadata, field_name="metadata")
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        object.__setattr__(self, "metadata", metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "observation_type": self.observation_type.value,
            "profile": self.profile,
            "selector": dict(self.selector),
            "parameters": dict(self.parameters),
            "expected": self.expected,
            "phase": self.phase,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservationRequest":
        allowed = {"observation_id", "observation_type", "profile", "selector", "parameters", "expected", "phase", "metadata"}
        _strict_mapping(data, model="ObservationRequest", allowed=allowed)
        required = {"observation_id", "observation_type", "profile", "selector", "expected"} - set(data)
        if required:
            raise ValueError(f"ObservationRequest missing fields: {sorted(required)!r}")
        return cls(
            observation_id=str(data["observation_id"]),
            observation_type=MinecraftObservationType(str(data["observation_type"])),
            profile=str(data["profile"]),
            selector=dict(data["selector"]),
            parameters=dict(data.get("parameters", {})),
            expected=data["expected"],
            phase=data.get("phase"),
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True, slots=True)
class ObservationResult:
    """Closed provider-neutral result envelope for future observations."""

    observation_id: str
    observation_type: MinecraftObservationType
    status: MinecraftObservationStatus
    expected: Any
    actual: Any = None
    phase: str | None = None
    evidence_refs: tuple[MinecraftEvidenceReference, ...] = ()
    error: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _identity("observation_id", self.observation_id))
        object.__setattr__(self, "observation_type", MinecraftObservationType(str(self.observation_type)))
        object.__setattr__(self, "status", MinecraftObservationStatus(str(self.status)))
        object.__setattr__(
            self,
            "expected",
            _closed_json(self.expected, field_name="expected", reject_unsafe_keys=False),
        )
        object.__setattr__(
            self,
            "actual",
            _closed_json(self.actual, field_name="actual", reject_unsafe_keys=False),
        )
        object.__setattr__(self, "phase", _optional_identity("phase", self.phase))
        refs = tuple(
            item if isinstance(item, MinecraftEvidenceReference) else MinecraftEvidenceReference.from_dict(item)
            for item in self.evidence_refs
        )
        object.__setattr__(self, "evidence_refs", refs)
        if self.error is not None:
            error = _closed_json(self.error, field_name="error", reject_unsafe_keys=False)
            if not isinstance(error, dict) or not error:
                raise ValueError("error must be a non-empty object")
            object.__setattr__(self, "error", error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "observation_type": self.observation_type.value,
            "status": self.status.value,
            "expected": self.expected,
            "actual": self.actual,
            "phase": self.phase,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservationResult":
        allowed = {"observation_id", "observation_type", "status", "expected", "actual", "phase", "evidence_refs", "error"}
        _strict_mapping(data, model="ObservationResult", allowed=allowed)
        required = {"observation_id", "observation_type", "status", "expected"} - set(data)
        if required:
            raise ValueError(f"ObservationResult missing fields: {sorted(required)!r}")
        return cls(
            observation_id=str(data["observation_id"]),
            observation_type=MinecraftObservationType(str(data["observation_type"])),
            status=MinecraftObservationStatus(str(data["status"])),
            expected=data["expected"],
            actual=data.get("actual"),
            phase=data.get("phase"),
            evidence_refs=tuple(MinecraftEvidenceReference.from_dict(item) for item in data.get("evidence_refs", [])),
            error=dict(data["error"]) if data.get("error") is not None else None,
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


MinecraftObservationRequest = ObservationRequest
MinecraftObservationResult = ObservationResult


@dataclass(frozen=True, slots=True)
class MinecraftTestSpec:
    """Minimum Minecraft runtime test specification."""

    target_jar: Path
    target_mod_id: str
    minecraft_version: str
    loader_version: str
    test_id: str
    timeout_seconds: int
    observation_type: MinecraftObservationType = MinecraftObservationType.LEGACY_BLOCK_STATE
    observation_params: Mapping[str, Any] = field(default_factory=dict)
    expect_neighbor_update: bool = False
    runtime_mod_jars: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_jar", _normalize_path(self.target_jar))
        runtime_mod_jars = tuple(_normalize_runtime_mod_jar(path) for path in self.runtime_mod_jars)
        runtime_mod_jar_strings = [path.as_posix() for path in runtime_mod_jars]
        if len(runtime_mod_jar_strings) != len(set(runtime_mod_jar_strings)):
            raise ValueError("runtime_mod_jars must not contain duplicates")
        target_jar_string = self.target_jar.as_posix()
        if target_jar_string in runtime_mod_jar_strings:
            raise ValueError("target_jar cannot be listed as a runtime dependency")
        object.__setattr__(
            self,
            "runtime_mod_jars",
            tuple(sorted(runtime_mod_jars, key=lambda path: path.as_posix().casefold())),
        )
        object.__setattr__(self, "target_mod_id", _validate_mod_id(self.target_mod_id))
        object.__setattr__(self, "minecraft_version", _non_empty_text("minecraft_version", self.minecraft_version))
        object.__setattr__(self, "loader_version", _non_empty_text("loader_version", self.loader_version))
        object.__setattr__(self, "test_id", _non_empty_text("test_id", self.test_id))
        object.__setattr__(self, "observation_type", MinecraftObservationType(str(self.observation_type)))
        object.__setattr__(self, "observation_params", dict(self.observation_params))
        timeout_seconds = int(self.timeout_seconds)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        object.__setattr__(self, "timeout_seconds", timeout_seconds)
        object.__setattr__(self, "expect_neighbor_update", bool(self.expect_neighbor_update))

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_jar": self.target_jar.as_posix(),
            "runtime_mod_jars": [path.as_posix() for path in self.runtime_mod_jars],
            "target_mod_id": self.target_mod_id,
            "minecraft_version": self.minecraft_version,
            "loader_version": self.loader_version,
            "test_id": self.test_id,
            "observation_type": self.observation_type.value,
            "observation_params": _json_ready(dict(self.observation_params)),
            "timeout_seconds": self.timeout_seconds,
            "expect_neighbor_update": self.expect_neighbor_update,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftTestSpec":
        return cls(
            target_jar=Path(data["target_jar"]),
            runtime_mod_jars=tuple(Path(path) for path in data.get("runtime_mod_jars", [])),
            target_mod_id=str(data["target_mod_id"]),
            minecraft_version=str(data["minecraft_version"]),
            loader_version=str(data["loader_version"]),
            test_id=str(data["test_id"]),
            observation_type=MinecraftObservationType(
                str(data.get("observation_type", MinecraftObservationType.LEGACY_BLOCK_STATE.value))
            ),
            observation_params=dict(data.get("observation_params", {})),
            timeout_seconds=int(data["timeout_seconds"]),
            expect_neighbor_update=bool(data.get("expect_neighbor_update", False)),
        )


class MinecraftTestStatus(StrEnum):
    """Minecraft runtime outcome."""

    PASS = "PASS"
    FAIL = "FAIL"
    CRASH = "CRASH"
    TIMEOUT = "TIMEOUT"
    INFRA_ERROR = "INFRA_ERROR"

    def is_terminal(self) -> bool:
        return True

    @property
    def is_pass(self) -> bool:
        return self is MinecraftTestStatus.PASS


@dataclass(frozen=True, slots=True)
class MinecraftEvidencePaths:
    """Canonical evidence layout for Minecraft runs."""

    root: Path

    @classmethod
    def for_run(cls, evidence_root: Path, run_id: str, *, create: bool = True) -> "MinecraftEvidencePaths":
        root = (Path(evidence_root) / run_id).resolve(strict=False)
        paths = cls(root=root)
        if create:
            paths.ensure_dirs()
        return paths

    def ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.crash_reports_dir.mkdir(parents=True, exist_ok=True)

    @property
    def spec_json(self) -> Path:
        return self.root / "spec.json"

    @property
    def target_json(self) -> Path:
        return self.root / "target.json"

    @property
    def harness_result_json(self) -> Path:
        return self.root / "harness-result.json"

    @property
    def result_json(self) -> Path:
        return self.root / "result.json"

    @property
    def stdout_log(self) -> Path:
        return self.root / "stdout.log"

    @property
    def stderr_log(self) -> Path:
        return self.root / "stderr.log"

    @property
    def latest_log(self) -> Path:
        return self.root / "latest.log"

    @property
    def crash_reports_dir(self) -> Path:
        return self.root / "crash-reports"

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root.as_posix(),
            "spec_json": self.spec_json.as_posix(),
            "target_json": self.target_json.as_posix(),
            "harness_result_json": self.harness_result_json.as_posix(),
            "result_json": self.result_json.as_posix(),
            "stdout_log": self.stdout_log.as_posix(),
            "stderr_log": self.stderr_log.as_posix(),
            "latest_log": self.latest_log.as_posix(),
            "crash_reports_dir": self.crash_reports_dir.as_posix(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftEvidencePaths":
        return cls(root=Path(data["root"]))


@dataclass(frozen=True, slots=True)
class MinecraftTargetMetadata:
    """Hash and identity metadata for the target JAR."""

    path: Path
    size_bytes: int
    sha256: str
    mod_id: str
    minecraft_version: str
    loader_version: str
    java_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path.as_posix(),
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "mod_id": self.mod_id,
            "minecraft_version": self.minecraft_version,
            "loader_version": self.loader_version,
            "java_version": self.java_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftTargetMetadata":
        return cls(
            path=Path(data["path"]),
            size_bytes=int(data["size_bytes"]),
            sha256=str(data["sha256"]),
            mod_id=str(data["mod_id"]),
            minecraft_version=str(data["minecraft_version"]),
            loader_version=str(data["loader_version"]),
            java_version=data.get("java_version"),
        )


@dataclass(frozen=True, slots=True)
class MinecraftLaunchPlan:
    """Controlled launch abstraction for later Minecraft execution."""

    run_id: str
    run_dir: Path
    spec_path: Path
    target_path: Path
    evidence_paths: MinecraftEvidencePaths
    system_properties: tuple[tuple[str, str], ...] = ()
    jvm_args: tuple[str, ...] = ()
    program_args: tuple[str, ...] = ()
    java_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": self.run_dir.as_posix(),
            "spec_path": self.spec_path.as_posix(),
            "target_path": self.target_path.as_posix(),
            "evidence_paths": self.evidence_paths.to_dict(),
            "system_properties": [
                {"name": name, "value": value} for name, value in self.system_properties
            ],
            "jvm_args": list(self.jvm_args),
            "program_args": list(self.program_args),
            "java_version": self.java_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftLaunchPlan":
        return cls(
            run_id=str(data["run_id"]),
            run_dir=Path(data["run_dir"]),
            spec_path=Path(data["spec_path"]),
            target_path=Path(data["target_path"]),
            evidence_paths=MinecraftEvidencePaths.from_dict(data["evidence_paths"]),
            system_properties=tuple(
                (str(item["name"]), str(item["value"]))
                for item in data.get("system_properties", [])
            ),
            jvm_args=tuple(str(item) for item in data.get("jvm_args", [])),
            program_args=tuple(str(item) for item in data.get("program_args", [])),
            java_version=data.get("java_version"),
        )


@dataclass(frozen=True, slots=True)
class MinecraftProcessEvidence:
    """Process evidence for a Minecraft runtime attempt."""

    command_display: str
    cwd: Path
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    exit_code: int
    timed_out: bool
    stdout_log: Path | None = None
    stderr_log: Path | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_display": self.command_display,
            "cwd": self.cwd.as_posix(),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "stdout_log": self.stdout_log.as_posix() if self.stdout_log is not None else None,
            "stderr_log": self.stderr_log.as_posix() if self.stderr_log is not None else None,
            "metadata": _json_ready(dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftProcessEvidence":
        return cls(
            command_display=str(data["command_display"]),
            cwd=Path(data["cwd"]),
            started_at=datetime.fromisoformat(str(data["started_at"])),
            finished_at=datetime.fromisoformat(str(data["finished_at"])),
            duration_seconds=float(data["duration_seconds"]),
            exit_code=int(data["exit_code"]),
            timed_out=bool(data["timed_out"]),
            stdout_log=Path(data["stdout_log"]) if data.get("stdout_log") is not None else None,
            stderr_log=Path(data["stderr_log"]) if data.get("stderr_log") is not None else None,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class MinecraftRuntimeEvidence:
    """Harness/runtime evidence for a Minecraft attempt."""

    harness_result_path: Path | None = None
    latest_log_path: Path | None = None
    crash_reports_dir: Path | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness_result_path": (
                self.harness_result_path.as_posix() if self.harness_result_path is not None else None
            ),
            "latest_log_path": (
                self.latest_log_path.as_posix() if self.latest_log_path is not None else None
            ),
            "crash_reports_dir": (
                self.crash_reports_dir.as_posix() if self.crash_reports_dir is not None else None
            ),
            "metadata": _json_ready(dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftRuntimeEvidence":
        return cls(
            harness_result_path=(
                Path(data["harness_result_path"])
                if data.get("harness_result_path") is not None
                else None
            ),
            latest_log_path=(
                Path(data["latest_log_path"])
                if data.get("latest_log_path") is not None
                else None
            ),
            crash_reports_dir=(
                Path(data["crash_reports_dir"])
                if data.get("crash_reports_dir") is not None
                else None
            ),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class MinecraftTestResult:
    """Machine-readable Minecraft test result."""

    run_id: str
    status: MinecraftTestStatus
    reason: str
    spec: MinecraftTestSpec
    target: MinecraftTargetMetadata
    evidence_paths: MinecraftEvidencePaths
    launch_plan: MinecraftLaunchPlan | None = None
    process_evidence: MinecraftProcessEvidence | None = None
    runtime_evidence: MinecraftRuntimeEvidence | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    target_failure_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is MinecraftTestStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "reason": self.reason,
            "target_failure_reason": self.target_failure_reason,
            "spec": self.spec.to_dict(),
            "target": self.target.to_dict(),
            "evidence_paths": self.evidence_paths.to_dict(),
            "launch_plan": self.launch_plan.to_dict() if self.launch_plan else None,
            "process_evidence": (
                self.process_evidence.to_dict() if self.process_evidence else None
            ),
            "runtime_evidence": (
                self.runtime_evidence.to_dict() if self.runtime_evidence else None
            ),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "metadata": _json_ready(dict(self.metadata)),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftTestResult":
        return cls(
            run_id=str(data["run_id"]),
            status=MinecraftTestStatus(str(data["status"])),
            reason=str(data["reason"]),
            spec=MinecraftTestSpec.from_dict(data["spec"]),
            target=MinecraftTargetMetadata.from_dict(data["target"]),
            evidence_paths=MinecraftEvidencePaths.from_dict(data["evidence_paths"]),
            launch_plan=(
                MinecraftLaunchPlan.from_dict(data["launch_plan"])
                if data.get("launch_plan") is not None
                else None
            ),
            process_evidence=(
                MinecraftProcessEvidence.from_dict(data["process_evidence"])
                if data.get("process_evidence") is not None
                else None
            ),
            runtime_evidence=(
                MinecraftRuntimeEvidence.from_dict(data["runtime_evidence"])
                if data.get("runtime_evidence") is not None
                else None
            ),
            started_at=(
                datetime.fromisoformat(str(data["started_at"]))
                if data.get("started_at") is not None
                else None
            ),
            finished_at=(
                datetime.fromisoformat(str(data["finished_at"]))
                if data.get("finished_at") is not None
                else None
            ),
            duration_seconds=(
                float(data["duration_seconds"])
                if data.get("duration_seconds") is not None
                else None
            ),
            target_failure_reason=(
                str(data["target_failure_reason"])
                if data.get("target_failure_reason") is not None
                else None
            ),
            metadata=dict(data.get("metadata", {})),
        )
