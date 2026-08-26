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
_I4_TAG_ID = "pdagentl11_harness:i4_controlled_members"
_I4_TAG_MEMBERS = {"minecraft:diamond", "minecraft:gold_ingot", "minecraft:stone"}
_I5_RECIPE_ID = "pdagentl11_harness:i5_marble_lantern"
_I5_INPUT_ITEM = "minecraft:diamond"
_I5_OUTPUT_ITEM = "minecraft:gold_ingot"
_I6_LOOT_TABLE_ID = "pdagentl11_harness:i6_fixed_drop"
_LOOT_ITEM_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*:[a-z0-9/._-]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WORLD_ROOT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,255}$")
_WORLD_FINGERPRINT_KEYS = {"level_name", "world_uuid", "seed", "dimension"}


def validate_recipe_match_profile(
    selector: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    """Validate the single bounded crafting recipe profile used by I5."""

    if not isinstance(selector, Mapping) or set(selector) != {"kind", "recipe_id"}:
        raise ValueError("RECIPE_MATCH selector must declare kind and recipe_id")
    if selector.get("kind") != "crafting_recipe" or selector.get("recipe_id") != _I5_RECIPE_ID:
        raise ValueError("RECIPE_MATCH only supports the controlled I5 recipe")
    if not isinstance(parameters, Mapping) or set(parameters) != {"input_item_id", "input_count", "expected_output_item_id", "expected_output_count"}:
        raise ValueError("RECIPE_MATCH parameters contain unsupported fields")
    if parameters["input_item_id"] != _I5_INPUT_ITEM:
        raise ValueError("RECIPE_MATCH only supports the controlled I5 input")
    if isinstance(parameters["input_count"], bool) or parameters["input_count"] != 1:
        raise ValueError("RECIPE_MATCH input_count must be one")
    if parameters["expected_output_item_id"] != _I5_OUTPUT_ITEM:
        raise ValueError("RECIPE_MATCH only supports the controlled I5 output")
    if isinstance(parameters["expected_output_count"], bool) or parameters["expected_output_count"] != 1:
        raise ValueError("RECIPE_MATCH expected_output_count must be one")


def validate_loot_result_profile(
    selector: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    """Validate the single deterministic generic loot profile used by I6."""

    if not isinstance(selector, Mapping) or set(selector) != {"kind", "loot_table_id"}:
        raise ValueError("LOOT_RESULT selector must declare kind and loot_table_id")
    if selector.get("kind") != "loot_table" or selector.get("loot_table_id") != _I6_LOOT_TABLE_ID:
        raise ValueError("LOOT_RESULT only supports the controlled I6 loot table")
    allowed = {"context_profile", "seed", "expected_item_id", "expected_count"}
    if not isinstance(parameters, Mapping) or set(parameters) != allowed:
        raise ValueError("LOOT_RESULT parameters contain unsupported fields")
    if parameters["context_profile"] != "generic":
        raise ValueError("LOOT_RESULT only supports the generic context profile")
    if isinstance(parameters["seed"], bool) or not isinstance(parameters["seed"], int):
        raise ValueError("LOOT_RESULT seed must be an integer")
    item_id = parameters["expected_item_id"]
    if not isinstance(item_id, str) or not _LOOT_ITEM_ID_RE.fullmatch(item_id):
        raise ValueError("LOOT_RESULT expected_item_id must be a namespaced identifier")
    count = parameters["expected_count"]
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 64:
        raise ValueError("LOOT_RESULT expected_count must be an integer from 0 through 64")


def validate_tag_membership_profile(
    selector: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    """Validate the closed item-tag profile used by I4."""

    if not isinstance(selector, Mapping) or set(selector) != {"registry_kind", "tag_id", "member_id"}:
        raise ValueError("TAG_MEMBERSHIP selector must declare registry_kind, tag_id and member_id")
    if selector.get("registry_kind") != "item":
        raise ValueError("TAG_MEMBERSHIP only supports the item registry")
    if selector.get("tag_id") != _I4_TAG_ID:
        raise ValueError("TAG_MEMBERSHIP only supports the controlled I4 tag")
    member_id = selector.get("member_id")
    if member_id not in _I4_TAG_MEMBERS:
        raise ValueError("TAG_MEMBERSHIP member is outside the controlled I4 fixture")
    if not isinstance(parameters, Mapping) or set(parameters) != {"expected_membership"}:
        raise ValueError("TAG_MEMBERSHIP parameters must declare expected_membership only")
    if not isinstance(parameters["expected_membership"], bool):
        raise ValueError("TAG_MEMBERSHIP expected_membership must be boolean")


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


class PersistencePhase(StrEnum):
    """Closed phases of the two-process persistence scenario."""

    PHASE_1 = "PHASE_1"
    PHASE_2 = "PHASE_2"


@dataclass(frozen=True, slots=True)
class PersistenceScenario:
    """Offline contract for one owned world and one persistence phase."""

    scenario_id: str
    world_id: str
    world_root: str
    target_artifact_sha256: str
    test_id: str
    phase: PersistencePhase
    expected_observation_id: str
    process_id: str
    evidence_refs: tuple[MinecraftEvidenceReference, ...] = ()
    predecessor_process_id: str | None = None
    same_world_required: bool = False
    reopen_only: bool = False
    setup_allowed: bool = True
    mutation_allowed_before_observation: bool = True
    world_root_must_exist: bool = False
    world_fingerprint: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for name in ("scenario_id", "world_id", "test_id", "expected_observation_id", "process_id"):
            object.__setattr__(self, name, _identity(name, getattr(self, name)))
        root = _non_empty_text("world_root", self.world_root).replace("\\", "/")
        if Path(root).is_absolute() or ".." in Path(root).parts or not _WORLD_ROOT_RE.fullmatch(root):
            raise ValueError("world_root must be a confined relative path")
        object.__setattr__(self, "world_root", root)
        artifact = _non_empty_text("target_artifact_sha256", self.target_artifact_sha256).casefold()
        if not _SHA256_RE.fullmatch(artifact):
            raise ValueError("target_artifact_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "target_artifact_sha256", artifact)
        object.__setattr__(self, "phase", PersistencePhase(str(self.phase)))
        for name in (
            "same_world_required",
            "reopen_only",
            "setup_allowed",
            "mutation_allowed_before_observation",
            "world_root_must_exist",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        predecessor = _optional_identity("predecessor_process_id", self.predecessor_process_id)
        object.__setattr__(self, "predecessor_process_id", predecessor)
        if self.phase is PersistencePhase.PHASE_1:
            if (
                predecessor is not None
                or self.reopen_only
                or not self.setup_allowed
                or not self.mutation_allowed_before_observation
                or self.world_root_must_exist
            ):
                raise ValueError("PHASE_1 must allow setup and mutation and cannot be reopen-only")
            if self.same_world_required:
                raise ValueError("PHASE_1 cannot require a previous same-world proof")
        else:
            if predecessor is None or predecessor == self.process_id:
                raise ValueError("PHASE_2 requires a distinct predecessor process")
            if (
                not self.same_world_required
                or not self.reopen_only
                or self.setup_allowed
                or self.mutation_allowed_before_observation
                or not self.world_root_must_exist
            ):
                raise ValueError("PHASE_2 must be REOPEN_ONLY with setup and pre-observation mutation disabled")
            if self.world_fingerprint is None:
                raise ValueError("PHASE_2 requires a bounded same-world fingerprint")
        refs = tuple(
            item if isinstance(item, MinecraftEvidenceReference) else MinecraftEvidenceReference.from_dict(item)
            for item in self.evidence_refs
        )
        for ref in refs:
            if ref.scenario_id not in (None, self.scenario_id):
                raise ValueError("evidence reference scenario does not match")
            if ref.phase not in (None, self.phase.value):
                raise ValueError("evidence reference phase does not match")
        object.__setattr__(self, "evidence_refs", refs)
        if self.world_fingerprint is not None:
            fingerprint = _closed_json(self.world_fingerprint, field_name="world_fingerprint", reject_unsafe_keys=False)
            if not isinstance(fingerprint, dict) or not fingerprint or set(fingerprint) - _WORLD_FINGERPRINT_KEYS:
                raise ValueError("world_fingerprint must contain only bounded world metadata")
            object.__setattr__(self, "world_fingerprint", fingerprint)

    def resolve_world_root(self, authorized_root: Path) -> Path:
        """Resolve the scenario world only inside the authorized execution root."""

        from pd_agent.tools import SecurePathResolver

        return SecurePathResolver(Path(authorized_root)).resolve_relative(self.world_root)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "world_id": self.world_id,
            "world_root": self.world_root,
            "target_artifact_sha256": self.target_artifact_sha256,
            "test_id": self.test_id,
            "phase": self.phase.value,
            "expected_observation_id": self.expected_observation_id,
            "process_id": self.process_id,
            "predecessor_process_id": self.predecessor_process_id,
            "same_world_required": self.same_world_required,
            "reopen_only": self.reopen_only,
            "setup_allowed": self.setup_allowed,
            "mutation_allowed_before_observation": self.mutation_allowed_before_observation,
            "world_root_must_exist": self.world_root_must_exist,
            "world_fingerprint": self.world_fingerprint,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PersistenceScenario":
        allowed = {
            "scenario_id", "world_id", "world_root", "target_artifact_sha256", "test_id", "phase",
            "expected_observation_id", "process_id", "predecessor_process_id", "same_world_required",
            "reopen_only", "setup_allowed", "mutation_allowed_before_observation", "world_fingerprint", "evidence_refs",
            "world_root_must_exist",
        }
        _strict_mapping(data, model="PersistenceScenario", allowed=allowed)
        required = {"scenario_id", "world_id", "world_root", "target_artifact_sha256", "test_id", "phase", "expected_observation_id", "process_id"} - set(data)
        if required:
            raise ValueError(f"PersistenceScenario missing fields: {sorted(required)!r}")
        return cls(
            scenario_id=str(data["scenario_id"]),
            world_id=str(data["world_id"]),
            world_root=str(data["world_root"]),
            target_artifact_sha256=str(data["target_artifact_sha256"]),
            test_id=str(data["test_id"]),
            phase=PersistencePhase(str(data["phase"])),
            expected_observation_id=str(data["expected_observation_id"]),
            process_id=str(data["process_id"]),
            predecessor_process_id=data.get("predecessor_process_id"),
            same_world_required=data.get("same_world_required", False),
            reopen_only=data.get("reopen_only", False),
            setup_allowed=data.get("setup_allowed", True),
            mutation_allowed_before_observation=data.get("mutation_allowed_before_observation", True),
            world_root_must_exist=data.get("world_root_must_exist", False),
            world_fingerprint=data.get("world_fingerprint"),
            evidence_refs=tuple(MinecraftEvidenceReference.from_dict(item) for item in data.get("evidence_refs", [])),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


_I7_COMMAND_PROFILE = "i7_inventory_mark"
_I7_COMMAND_TEXT = "pdagent_i7 mark"
_I8_EVENT_PROFILE = "i8_world_load_effect"


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    """Closed, typed invocation for the single I7 server command profile."""

    invocation_id: str
    profile: str
    typed_args: Mapping[str, Any]
    source: str = "controlled_server"
    permission_level: int = 4

    def __post_init__(self) -> None:
        object.__setattr__(self, "invocation_id", _identity("invocation_id", self.invocation_id))
        if self.profile != _I7_COMMAND_PROFILE:
            raise ValueError("unsupported command profile")
        args = _closed_json(self.typed_args, field_name="typed_args")
        if not isinstance(args, dict) or set(args) != {"count"}:
            raise ValueError("I7 command requires the typed count argument only")
        count = args["count"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 5:
            raise ValueError("I7 command count must be an integer from 1 through 5")
        object.__setattr__(self, "typed_args", args)
        if self.source != "controlled_server":
            raise ValueError("I7 command source is fixed to controlled_server")
        if self.permission_level != 4:
            raise ValueError("I7 command permission level is fixed to 4")

    @property
    def command(self) -> str:
        return _I7_COMMAND_TEXT

    def to_dict(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "profile": self.profile,
            "command": self.command,
            "typed_args": dict(self.typed_args),
            "source": self.source,
            "permission_level": self.permission_level,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommandInvocation":
        _strict_mapping(
            data,
            model="CommandInvocation",
            allowed={"invocation_id", "profile", "command", "typed_args", "source", "permission_level"},
        )
        required = {"invocation_id", "profile", "typed_args"} - set(data)
        if required:
            raise ValueError(f"CommandInvocation missing fields: {sorted(required)!r}")
        if data.get("command", _I7_COMMAND_TEXT) != _I7_COMMAND_TEXT:
            raise ValueError("command text is not part of the closed I7 profile")
        return cls(
            invocation_id=str(data["invocation_id"]),
            profile=str(data["profile"]),
            typed_args=dict(data["typed_args"]),
            source=str(data.get("source", "controlled_server")),
            permission_level=int(data.get("permission_level", 4)),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Structured result for a registered and typed I7 command invocation."""

    invocation_id: str
    registered: bool
    parsed: bool
    executed: bool
    return_code: int | None
    success: bool
    output_summary: str | None = None
    error: Mapping[str, Any] | None = None
    evidence_refs: tuple[MinecraftEvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "invocation_id", _identity("invocation_id", self.invocation_id))
        for name in ("registered", "parsed", "executed", "success"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        if self.return_code is not None and (
            isinstance(self.return_code, bool) or not isinstance(self.return_code, int)
        ):
            raise ValueError("return_code must be an integer or null")
        if self.success and not (self.registered and self.parsed and self.executed):
            raise ValueError("successful command must be registered, parsed and executed")
        if self.output_summary is not None:
            object.__setattr__(self, "output_summary", _non_empty_text("output_summary", self.output_summary))
        if self.error is not None:
            error = _closed_json(self.error, field_name="error", reject_unsafe_keys=False)
            if not isinstance(error, dict) or not error:
                raise ValueError("error must be a non-empty object")
            object.__setattr__(self, "error", error)
        refs = tuple(
            item if isinstance(item, MinecraftEvidenceReference) else MinecraftEvidenceReference.from_dict(item)
            for item in self.evidence_refs
        )
        object.__setattr__(self, "evidence_refs", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "registered": self.registered,
            "parsed": self.parsed,
            "executed": self.executed,
            "return_code": self.return_code,
            "success": self.success,
            "output_summary": self.output_summary,
            "error": self.error,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommandResult":
        _strict_mapping(
            data,
            model="CommandResult",
            allowed={"invocation_id", "registered", "parsed", "executed", "return_code", "success", "output_summary", "error", "evidence_refs"},
        )
        required = {"invocation_id", "registered", "parsed", "executed", "success"} - set(data)
        if required:
            raise ValueError(f"CommandResult missing fields: {sorted(required)!r}")
        return cls(
            invocation_id=str(data["invocation_id"]),
            registered=data["registered"],
            parsed=data["parsed"],
            executed=data["executed"],
            return_code=data.get("return_code"),
            success=data["success"],
            output_summary=data.get("output_summary"),
            error=dict(data["error"]) if data.get("error") is not None else None,
            evidence_refs=tuple(MinecraftEvidenceReference.from_dict(item) for item in data.get("evidence_refs", [])),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


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
    command_invocation: CommandInvocation | None = None
    event_profile: str | None = None

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
        if self.command_invocation is not None and not isinstance(self.command_invocation, CommandInvocation):
            object.__setattr__(self, "command_invocation", CommandInvocation.from_dict(self.command_invocation))
        if self.event_profile is not None and self.event_profile != _I8_EVENT_PROFILE:
            raise ValueError("unsupported event profile")

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
            **(
                {"command_invocation": self.command_invocation.to_dict()}
                if self.command_invocation is not None
                else {}
            ),
            **({"event_profile": self.event_profile} if self.event_profile is not None else {}),
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
            command_invocation=(
                CommandInvocation.from_dict(data["command_invocation"])
                if data.get("command_invocation") is not None
                else None
            ),
            event_profile=data.get("event_profile"),
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
