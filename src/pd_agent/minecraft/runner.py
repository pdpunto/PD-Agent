"""Minecraft test harness runner."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from pd_agent.core import SecurityViolation
from pd_agent.tools import SecurePathResolver

from .contracts import (
    CommandResult,
    MinecraftEvidencePaths,
    MinecraftEvidenceKind,
    MinecraftEvidenceReference,
    MinecraftLaunchPlan,
    MinecraftProcessEvidence,
    MinecraftObservationType,
    MinecraftObservationStatus,
    MinecraftRuntimeEvidence,
    MinecraftTargetMetadata,
    MinecraftTestResult,
    MinecraftTestSpec,
    MinecraftTestStatus,
    ObservationResult,
    validate_item_component_profile,
    validate_block_entity_profile,
    validate_inventory_profile,
    validate_tag_membership_profile,
    validate_recipe_match_profile,
    validate_loot_result_profile,
)
from .errors import MinecraftTestValidationError, UnsupportedMinecraftEnvironmentError


DEFAULT_PRODUCTION_TASK = "productionServerRun"


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _read_manifest(path: Path) -> Mapping[str, Any]:
    with zipfile.ZipFile(path) as jar:
        try:
            raw = jar.read("fabric.mod.json")
        except KeyError as exc:
            raise MinecraftTestValidationError("target jar is missing fabric.mod.json") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise MinecraftTestValidationError("fabric.mod.json is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise MinecraftTestValidationError("fabric.mod.json is not valid JSON") from exc
    if not isinstance(data, Mapping):
        raise MinecraftTestValidationError("fabric.mod.json must be an object")
    return data


def _target_entrypoint_class(manifest: Mapping[str, Any], *, target_path: Path) -> str:
    entrypoints = manifest.get("entrypoints")
    if not isinstance(entrypoints, Mapping):
        raise MinecraftTestValidationError(f"target fabric.mod.json is missing entrypoints: {target_path}")
    main = entrypoints.get("main")
    if isinstance(main, str):
        candidates = (main,)
    elif isinstance(main, Sequence) and not isinstance(main, (str, bytes, bytearray)):
        candidates = tuple(str(item).strip() for item in main if str(item).strip())
    else:
        raise MinecraftTestValidationError(f"target fabric.mod.json is missing main entrypoint: {target_path}")
    if not candidates:
        raise MinecraftTestValidationError(f"target fabric.mod.json main entrypoint is empty: {target_path}")
    if len(candidates) != 1:
        raise MinecraftTestValidationError(f"target fabric.mod.json main entrypoint is ambiguous: {target_path}")
    return candidates[0]


def _observation_params(data: Mapping[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {}
    return {str(key): value for key, value in dict(data).items()}


def _registry_identifier_from_params(params: Mapping[str, Any]) -> str | None:
    raw = params.get("identifier")
    if raw is None:
        raw = params.get("registry_identifier")
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return text


def _registry_kind_from_params(params: Mapping[str, Any]) -> str | None:
    raw = params.get("registry_kind")
    if raw is None:
        raw = params.get("kind")
    if raw is None:
        return None
    text = str(raw).strip().casefold()
    if not text:
        return None
    return text


def _item_component_params(params: Mapping[str, Any]) -> tuple[str, str, bool]:
    component_id = str(params.get("component_id", "")).strip()
    item_id = str(params.get("item_id", "minecraft:diamond")).strip()
    round_trip = params.get("round_trip", False)
    validate_item_component_profile({"kind": "harness_stack", "item_id": item_id}, {
        "component_id": component_id,
        "round_trip": round_trip,
    })
    return component_id, item_id, round_trip


def _item_component_properties(params: Mapping[str, Any]) -> tuple[str, str, str]:
    component_id, item_id, round_trip = _item_component_params(params)
    return component_id, item_id, str(round_trip).lower()


def _controlled_world_profile(observation_type: MinecraftObservationType, params: Mapping[str, Any]) -> tuple[str, ...]:
    selector_kind = (
        "harness_block_entity"
        if observation_type is MinecraftObservationType.BLOCK_ENTITY_STATE
        else "harness_inventory"
    )
    selector = {"kind": selector_kind, "fixture": "hopper", "pos": [8, 64, 8]}
    if observation_type is MinecraftObservationType.BLOCK_ENTITY_STATE:
        validate_block_entity_profile(selector, params)
        return (str(params.get("block_entity_id", "minecraft:hopper")), str(params.get("mutation", True)).lower())
    validate_inventory_profile(selector, params)
    return (
        str(params.get("slot", 0)),
        str(params.get("item_id", "minecraft:diamond")),
        str(params.get("count", 5)),
        str(params.get("mutation", True)).lower(),
    )


def _tag_membership_properties(params: Mapping[str, Any]) -> tuple[str, str, str, str]:
    selector = {
        "registry_kind": params.get("registry_kind", "item"),
        "tag_id": params.get("tag_id", "pdagentl11_harness:i4_controlled_members"),
        "member_id": params.get("member_id", "minecraft:diamond"),
    }
    parameters = {"expected_membership": params.get("expected_membership", True)}
    validate_tag_membership_profile(selector, parameters)
    return (
        selector["registry_kind"],
        selector["tag_id"],
        selector["member_id"],
        str(parameters["expected_membership"]).lower(),
    )


def _recipe_match_properties(params: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    values = {
        "input_item_id": params.get("input_item_id", "minecraft:diamond"),
        "input_count": params.get("input_count", 1),
        "expected_output_item_id": params.get("expected_output_item_id", "minecraft:gold_ingot"),
        "expected_output_count": params.get("expected_output_count", 1),
    }
    validate_recipe_match_profile(
        {"kind": "crafting_recipe", "recipe_id": params.get("recipe_id", "pdagentl11_harness:i5_marble_lantern")},
        values,
    )


def _loot_result_properties(params: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    values = {
        "context_profile": params.get("context_profile", "generic"),
        "seed": params.get("seed", 0),
        "expected_item_id": params.get("expected_item_id", "minecraft:gold_ingot"),
        "expected_count": params.get("expected_count", 1),
    }
    loot_table_id = params.get("loot_table_id", "pdagentl11_harness:i6_fixed_drop")
    validate_loot_result_profile({"kind": "loot_table", "loot_table_id": loot_table_id}, values)
    return (
        str(loot_table_id),
        values["context_profile"],
        str(values["seed"]),
        values["expected_item_id"],
        str(values["expected_count"]),
    )
    return (
        str(params.get("recipe_id", "pdagentl11_harness:i5_marble_lantern")),
        values["input_item_id"],
        str(values["input_count"]),
        values["expected_output_item_id"],
        str(values["expected_output_count"]),
    )


def _non_empty_set(values: Sequence[str] | None) -> frozenset[str]:
    if values is None:
        return frozenset()
    return frozenset(str(item).strip() for item in values if str(item).strip())


def _read_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass(slots=True)
class MinecraftTestRunner:
    """Validate and execute the dedicated Fabric runtime harness."""

    project_root: Path
    evidence_root: Path | None = None
    harness_root: Path | None = None
    production_task: str = DEFAULT_PRODUCTION_TASK
    environment_overrides: Mapping[str, str] = field(default_factory=dict)
    supported_minecraft_versions: frozenset[str] = field(
        default_factory=lambda: frozenset({"1.21.11"})
    )
    supported_loader_versions: frozenset[str] = field(default_factory=lambda: frozenset({"0.19.3"}))
    supported_java_versions: frozenset[str] = field(default_factory=lambda: frozenset({"21"}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", Path(self.project_root).resolve(strict=True))
        if self.evidence_root is None:
            object.__setattr__(self, "evidence_root", self.project_root / "evidence" / "minecraft")
        else:
            object.__setattr__(self, "evidence_root", Path(self.evidence_root).resolve(strict=False))
        if self.harness_root is None:
            object.__setattr__(
                self,
                "harness_root",
                self.project_root / "tests" / "fixtures" / "l11_minecraft_harness",
            )
        else:
            object.__setattr__(self, "harness_root", Path(self.harness_root).resolve(strict=False))
        object.__setattr__(
            self,
            "environment_overrides",
            {str(key): str(value) for key, value in dict(self.environment_overrides).items()},
        )
        object.__setattr__(
            self,
            "supported_minecraft_versions",
            _non_empty_set(tuple(self.supported_minecraft_versions)),
        )
        object.__setattr__(
            self,
            "supported_loader_versions",
            _non_empty_set(tuple(self.supported_loader_versions)),
        )
        object.__setattr__(
            self,
            "supported_java_versions",
            _non_empty_set(tuple(self.supported_java_versions)),
        )

    def validate_spec(self, spec: MinecraftTestSpec, *, java_version: str | None = None) -> None:
        if spec.minecraft_version not in self.supported_minecraft_versions:
            raise UnsupportedMinecraftEnvironmentError(
                f"unsupported minecraft_version: {spec.minecraft_version}"
            )
        if spec.loader_version not in self.supported_loader_versions:
            raise UnsupportedMinecraftEnvironmentError(f"unsupported loader_version: {spec.loader_version}")
        if java_version is not None and java_version not in self.supported_java_versions:
            raise UnsupportedMinecraftEnvironmentError(f"unsupported java_version: {java_version}")
        if spec.observation_type is MinecraftObservationType.ITEM_COMPONENT_STATE:
            _item_component_params(spec.observation_params)
        elif spec.observation_type in {
            MinecraftObservationType.BLOCK_ENTITY_STATE,
            MinecraftObservationType.INVENTORY_STATE,
        }:
            _controlled_world_profile(spec.observation_type, spec.observation_params)
        elif spec.observation_type is MinecraftObservationType.TAG_MEMBERSHIP:
            _tag_membership_properties(spec.observation_params)
        elif spec.observation_type is MinecraftObservationType.RECIPE_MATCH:
            _recipe_match_properties(spec.observation_params)
        elif spec.observation_type is MinecraftObservationType.LOOT_RESULT:
            _loot_result_properties(spec.observation_params)

    def validate_target(
        self,
        spec: MinecraftTestSpec,
        *,
        java_version: str | None = None,
    ) -> MinecraftTargetMetadata:
        self.validate_spec(spec, java_version=java_version)
        resolver = SecurePathResolver(self.project_root)
        target_path = resolver.resolve_existing_file(spec.target_jar)
        if target_path.suffix.lower() != ".jar":
            raise MinecraftTestValidationError("target must be a .jar file")
        if not zipfile.is_zipfile(target_path):
            raise MinecraftTestValidationError("target is not a valid jar")

        manifest = _read_manifest(target_path)
        mod_id = str(manifest.get("id", "")).strip()
        if not mod_id:
            raise MinecraftTestValidationError("target fabric.mod.json is missing id")
        if mod_id != spec.target_mod_id:
            raise MinecraftTestValidationError(
                f"target mod id mismatch: expected {spec.target_mod_id!r}, got {mod_id!r}"
            )

        return MinecraftTargetMetadata(
            path=target_path,
            size_bytes=target_path.stat().st_size,
            sha256=_sha256(target_path),
            mod_id=mod_id,
            minecraft_version=spec.minecraft_version,
            loader_version=spec.loader_version,
            java_version=java_version,
        )

    def build_evidence_paths(self, run_id: str, *, create: bool = True) -> MinecraftEvidencePaths:
        return MinecraftEvidencePaths.for_run(self.evidence_root, run_id, create=create)

    def build_launch_plan(
        self,
        spec: MinecraftTestSpec,
        *,
        run_id: str | None = None,
        java_version: str | None = None,
    ) -> MinecraftLaunchPlan:
        run_id = self._resolve_run_id(run_id)
        target = self.validate_target(spec, java_version=java_version)
        target_entrypoint_class = _target_entrypoint_class(_read_manifest(target.path), target_path=target.path)
        evidence_paths = self.build_evidence_paths(run_id, create=True)
        run_dir = evidence_paths.root / "runtime"
        system_properties = (
            ("pd.agent.minecraft.run_id", run_id),
            ("pd.agent.minecraft.target_mod_id", spec.target_mod_id),
            ("pd.agent.minecraft.expected_sha256", target.sha256),
            ("pd.agent.targetEntrypointClass", target_entrypoint_class),
            ("pd.agent.minecraft.test_id", spec.test_id),
            ("pd.agent.observationType", spec.observation_type.value),
            ("pd.agent.minecraft.expect_neighbor_update", str(spec.expect_neighbor_update).lower()),
            ("pd.agent.minecraft.result_path", evidence_paths.harness_result_json.as_posix()),
            *(
                (("pd.agent.runtimeModJars", os.pathsep.join(path.as_posix() for path in spec.runtime_mod_jars)),)
                if spec.runtime_mod_jars
                else ()
            ),
            *(
                (("pd.agent.observationRegistryKind", registry_kind),)
                if (registry_kind := _registry_kind_from_params(spec.observation_params)) is not None
                else ()
            ),
            *(
                (("pd.agent.observationIdentifier", observation_identifier),)
                if (observation_identifier := _registry_identifier_from_params(spec.observation_params)) is not None
                else ()
            ),
            *(
                tuple(zip(
                    ("pd.agent.observationComponentId", "pd.agent.observationItemId", "pd.agent.observationRoundTrip"),
                    _item_component_properties(spec.observation_params),
                ))
                if spec.observation_type is MinecraftObservationType.ITEM_COMPONENT_STATE
                else ()
            ),
            *(
                tuple(zip(
                    ("pd.agent.observationRegistryKind", "pd.agent.observationTagId", "pd.agent.observationMemberId", "pd.agent.observationExpectedMembership"),
                    _tag_membership_properties(spec.observation_params),
                ))
                if spec.observation_type is MinecraftObservationType.TAG_MEMBERSHIP
                else ()
            ),
            *(
                tuple(zip(
                    ("pd.agent.observationBlockEntityId", "pd.agent.observationMutation"),
                    _controlled_world_profile(spec.observation_type, spec.observation_params),
                ))
                if spec.observation_type is MinecraftObservationType.BLOCK_ENTITY_STATE
                else ()
            ),
            *(
                tuple(zip(
                    ("pd.agent.observationSlot", "pd.agent.observationItemId", "pd.agent.observationCount", "pd.agent.observationMutation"),
                    _controlled_world_profile(spec.observation_type, spec.observation_params),
                ))
                if spec.observation_type is MinecraftObservationType.INVENTORY_STATE
                else ()
            ),
            *(
                tuple(zip(
                    ("pd.agent.observationRecipeId", "pd.agent.observationInputItemId", "pd.agent.observationInputCount", "pd.agent.observationExpectedOutputItemId", "pd.agent.observationExpectedOutputCount"),
                    _recipe_match_properties(spec.observation_params),
                ))
                if spec.observation_type is MinecraftObservationType.RECIPE_MATCH
                else ()
            ),
            *(
                tuple(zip(
                    ("pd.agent.observationLootTableId", "pd.agent.observationLootContextProfile", "pd.agent.observationLootSeed", "pd.agent.observationLootExpectedItemId", "pd.agent.observationLootExpectedCount"),
                    _loot_result_properties(spec.observation_params),
                ))
                if spec.observation_type is MinecraftObservationType.LOOT_RESULT
                else ()
            ),
        )
        return MinecraftLaunchPlan(
            run_id=run_id,
            run_dir=run_dir,
            spec_path=evidence_paths.spec_json,
            target_path=target.path,
            evidence_paths=evidence_paths,
            system_properties=system_properties,
            jvm_args=(),
            program_args=(),
            java_version=java_version,
        )

    def prepare_run(
        self,
        spec: MinecraftTestSpec,
        *,
        run_id: str | None = None,
        java_version: str | None = None,
    ) -> MinecraftTestResult:
        run_id = self._resolve_run_id(run_id)
        target = self.validate_target(spec, java_version=java_version)
        evidence_paths = self.build_evidence_paths(run_id, create=True)
        _write_json(evidence_paths.spec_json, spec.to_dict())
        _write_json(evidence_paths.target_json, target.to_dict())
        launch_plan = self.build_launch_plan(spec, run_id=run_id, java_version=java_version)
        now = datetime.now(timezone.utc)
        return MinecraftTestResult(
            run_id=run_id,
            status=MinecraftTestStatus.INFRA_ERROR,
            reason="Minecraft runtime launch not implemented in Batch A",
            spec=spec,
            target=target,
            evidence_paths=evidence_paths,
            launch_plan=launch_plan,
            process_evidence=None,
            runtime_evidence=None,
            started_at=now,
            finished_at=now,
            duration_seconds=0.0,
            metadata={"phase": "preflight"},
        )

    def run(
        self,
        spec: MinecraftTestSpec,
        *,
        run_id: str | None = None,
        java_version: str | None = None,
        launch_mode: str = "pass",
        expected_sha256: str | None = None,
        authorized_runtime_roots: Sequence[Path] | None = None,
    ) -> MinecraftTestResult:
        preflight = self.prepare_run(spec, run_id=run_id, java_version=java_version)
        if not self.harness_root.exists():
            return self._finalize_runtime_failure(
                preflight,
                status=MinecraftTestStatus.INFRA_ERROR,
                reason=f"harness root missing: {self.harness_root}",
                metadata={"launch_mode": launch_mode, "phase": "preflight"},
            )

        launch_mode = self._normalize_launch_mode(launch_mode)
        runtime_dependency_records: tuple[dict[str, Any], ...] = ()
        if spec.runtime_mod_jars:
            try:
                runtime_dependency_records = self._validate_runtime_mod_dependencies(
                    spec.runtime_mod_jars,
                    target_path=preflight.target.path,
                    authorized_runtime_roots=authorized_runtime_roots,
                )
            except (MinecraftTestValidationError, SecurityViolation) as exc:
                return self._finalize_runtime_failure(
                    preflight,
                    status=MinecraftTestStatus.INFRA_ERROR,
                    reason=str(exc),
                    metadata={
                        "launch_mode": launch_mode,
                        "phase": "preflight",
                        "runtime_mod_dependencies": [],
                    },
                )
        launch_props = self._build_launch_properties(preflight, launch_mode, expected_sha256=expected_sha256)
        command = self._build_command(launch_props)
        process = self._run_command(command, cwd=self.harness_root, timeout_seconds=spec.timeout_seconds)
        process_evidence = MinecraftProcessEvidence(
            command_display=process["command_display"],
            cwd=process["cwd"],
            started_at=process["started_at"],
            finished_at=process["finished_at"],
            duration_seconds=process["duration_seconds"],
            exit_code=process["exit_code"],
            timed_out=process["timed_out"],
            stdout_log=preflight.evidence_paths.stdout_log,
            stderr_log=preflight.evidence_paths.stderr_log,
            metadata={
                "launch_mode": launch_mode,
                "task": self.production_task,
                "run_dir": str(preflight.launch_plan.run_dir) if preflight.launch_plan else None,
                "command_display": process["command_display"],
                "environment_overrides": dict(self.environment_overrides),
            },
        )
        preflight.evidence_paths.stdout_log.write_text(process["stdout"], encoding="utf-8")
        preflight.evidence_paths.stderr_log.write_text(process["stderr"], encoding="utf-8")

        runtime_root = preflight.launch_plan.run_dir if preflight.launch_plan else preflight.evidence_paths.root / "runtime"
        harness_result_path = preflight.evidence_paths.harness_result_json
        runtime_metadata: dict[str, Any] = {"launch_mode": launch_mode}
        runtime_evidence = self._collect_runtime_evidence(
            preflight.evidence_paths,
            runtime_root,
            metadata=runtime_metadata,
            harness_result_path=harness_result_path,
        )
        harness_result = self._read_harness_result(harness_result_path)
        status, reason, runtime_metadata = self._classify_runtime(
            process=process,
            harness_result=harness_result,
            latest_log=_read_text(runtime_evidence.latest_log_path),
            launch_mode=launch_mode,
            target=preflight.target,
            timeout_seconds=spec.timeout_seconds,
        )
        runtime_evidence = MinecraftRuntimeEvidence(
            harness_result_path=runtime_evidence.harness_result_path,
            latest_log_path=runtime_evidence.latest_log_path,
            crash_reports_dir=runtime_evidence.crash_reports_dir,
            metadata={
                **runtime_evidence.metadata,
                **runtime_metadata,
                "harness_result_path": str(runtime_evidence.harness_result_path) if runtime_evidence.harness_result_path else None,
                "environment_overrides": dict(self.environment_overrides),
            },
        )
        if runtime_dependency_records:
            runtime_evidence = MinecraftRuntimeEvidence(
                harness_result_path=runtime_evidence.harness_result_path,
                latest_log_path=runtime_evidence.latest_log_path,
                crash_reports_dir=runtime_evidence.crash_reports_dir,
                metadata={
                    **runtime_evidence.metadata,
                    "runtime_mod_dependencies": list(runtime_dependency_records),
                },
            )
        final_result = MinecraftTestResult(
            run_id=preflight.run_id,
            status=status,
            reason=reason,
            spec=spec,
            target=preflight.target,
            evidence_paths=preflight.evidence_paths,
            launch_plan=preflight.launch_plan,
            process_evidence=process_evidence,
            runtime_evidence=runtime_evidence,
            started_at=process["started_at"],
            finished_at=process["finished_at"],
            duration_seconds=process["duration_seconds"],
            target_failure_reason=runtime_metadata.get("target_failure_reason"),
            metadata={
                "phase": "runtime",
                "launch_mode": launch_mode,
                "expected_sha256": expected_sha256 or preflight.target.sha256,
                "command_display": process["command_display"],
                "process_exit_code": process["exit_code"],
                "process_timed_out": process["timed_out"],
                "harness_result_state": harness_result.get("functional_test_result") if isinstance(harness_result, Mapping) else None,
                "command_result": harness_result.get("command_result") if isinstance(harness_result, Mapping) else None,
                "harness_result_path": str(harness_result_path),
                "latest_log_path": str(runtime_evidence.latest_log_path) if runtime_evidence.latest_log_path else None,
                "crash_reports_dir": str(runtime_evidence.crash_reports_dir) if runtime_evidence.crash_reports_dir else None,
                "launch_properties": list(launch_props),
                "environment_overrides": dict(self.environment_overrides),
            },
        )
        if runtime_dependency_records:
            final_result = MinecraftTestResult(
                run_id=final_result.run_id,
                status=final_result.status,
                reason=final_result.reason,
                spec=final_result.spec,
                target=final_result.target,
                evidence_paths=final_result.evidence_paths,
                launch_plan=final_result.launch_plan,
                process_evidence=final_result.process_evidence,
                runtime_evidence=final_result.runtime_evidence,
                started_at=final_result.started_at,
                finished_at=final_result.finished_at,
                duration_seconds=final_result.duration_seconds,
                target_failure_reason=final_result.target_failure_reason,
                metadata={
                    **dict(final_result.metadata),
                    "runtime_mod_dependencies": list(runtime_dependency_records),
                },
            )
        _write_json(preflight.evidence_paths.result_json, final_result.to_dict())
        return final_result

    def _build_launch_properties(
        self,
        result: MinecraftTestResult,
        launch_mode: str,
        *,
        expected_sha256: str | None = None,
    ) -> tuple[str, ...]:
        target = result.target
        expected_block_state_id = "air" if launch_mode == "functional_fail" else "diamond_block"
        expected_sha256 = expected_sha256 or target.sha256
        target_entrypoint_class = _target_entrypoint_class(_read_manifest(target.path), target_path=target.path)
        result_mode = launch_mode
        hang_millis = str(max(int((result.duration_seconds or 0) * 1000) + 60_000, 600_000))
        if launch_mode != "hang":
            hang_millis = "600000"
        return (
            f"-Ppd.agent.targetJar={target.path}",
            f"-Ppd.agent.targetModId={target.mod_id}",
            f"-Ppd.agent.targetSha256={expected_sha256}",
            f"-Ppd.agent.targetEntrypointClass={target_entrypoint_class}",
            f"-Ppd.agent.testId={result.spec.test_id}",
            f"-Ppd.agent.observationType={result.spec.observation_type.value}",
            f"-Ppd.agent.resultPath={result.evidence_paths.harness_result_json}",
            f"-Ppd.agent.runDir={result.evidence_paths.root / 'runtime'}",
            f"-Ppd.agent.resultMode={result_mode}",
            f"-Ppd.agent.expectedBlockStateId={expected_block_state_id}",
            f"-Ppd.agent.expectNeighborUpdate={str(result.spec.expect_neighbor_update).lower()}",
            f"-Ppd.agent.hangMillis={hang_millis if launch_mode == 'hang' else '600000'}",
            *(
                (
                    f"-Ppd.agent.commandProfile={result.spec.command_invocation.profile}",
                    f"-Ppd.agent.commandInvocationId={result.spec.command_invocation.invocation_id}",
                    f"-Ppd.agent.commandCount={result.spec.command_invocation.typed_args['count']}",
                )
                if result.spec.command_invocation is not None
                else ()
            ),
            *(
                (f"-Ppd.agent.runtimeModJars={os.pathsep.join(path.as_posix() for path in result.spec.runtime_mod_jars)}",)
                if result.spec.runtime_mod_jars
                else ()
            ),
            *(
                (f"-Ppd.agent.observationRegistryKind={registry_kind}",)
                if (registry_kind := _registry_kind_from_params(result.spec.observation_params)) is not None
                else ()
            ),
            *(
                (f"-Ppd.agent.observationIdentifier={observation_identifier}",)
                if (observation_identifier := _registry_identifier_from_params(result.spec.observation_params)) is not None
                else ()
            ),
            *(
                tuple(
                    f"-P{name}={value}"
                    for name, value in zip(
                        ("pd.agent.observationComponentId", "pd.agent.observationItemId", "pd.agent.observationRoundTrip"),
                        _item_component_properties(result.spec.observation_params),
                    )
                )
                if result.spec.observation_type is MinecraftObservationType.ITEM_COMPONENT_STATE
                else ()
            ),
            *(
                tuple(
                    f"-P{name}={value}"
                    for name, value in zip(
                        ("pd.agent.observationRegistryKind", "pd.agent.observationTagId", "pd.agent.observationMemberId", "pd.agent.observationExpectedMembership"),
                        _tag_membership_properties(result.spec.observation_params),
                    )
                )
                if result.spec.observation_type is MinecraftObservationType.TAG_MEMBERSHIP
                else ()
            ),
            *(
                tuple(
                    f"-P{name}={value}"
                    for name, value in zip(
                        ("pd.agent.observationBlockEntityId", "pd.agent.observationMutation"),
                        _controlled_world_profile(result.spec.observation_type, result.spec.observation_params),
                    )
                )
                if result.spec.observation_type is MinecraftObservationType.BLOCK_ENTITY_STATE
                else ()
            ),
            *(
                tuple(
                    f"-P{name}={value}"
                    for name, value in zip(
                        ("pd.agent.observationSlot", "pd.agent.observationItemId", "pd.agent.observationCount", "pd.agent.observationMutation"),
                        _controlled_world_profile(result.spec.observation_type, result.spec.observation_params),
                    )
                )
                if result.spec.observation_type is MinecraftObservationType.INVENTORY_STATE
                else ()
            ),
            *(
                tuple(
                    f"-P{name}={value}"
                    for name, value in zip(
                        ("pd.agent.observationRecipeId", "pd.agent.observationInputItemId", "pd.agent.observationInputCount", "pd.agent.observationExpectedOutputItemId", "pd.agent.observationExpectedOutputCount"),
                        _recipe_match_properties(result.spec.observation_params),
                    )
                )
                if result.spec.observation_type is MinecraftObservationType.RECIPE_MATCH
                else ()
            ),
            *(
                tuple(
                    f"-P{name}={value}"
                    for name, value in zip(
                        ("pd.agent.observationLootTableId", "pd.agent.observationLootContextProfile", "pd.agent.observationLootSeed", "pd.agent.observationLootExpectedItemId", "pd.agent.observationLootExpectedCount"),
                        _loot_result_properties(result.spec.observation_params),
                    )
                )
                if result.spec.observation_type is MinecraftObservationType.LOOT_RESULT
                else ()
            ),
        )

    def _build_command(self, launch_properties: tuple[str, ...]) -> tuple[str, ...]:
        wrapper = self.harness_root / "gradlew.bat"
        if not wrapper.exists():
            raise MinecraftTestValidationError(f"missing gradle wrapper: {wrapper}")
        if os.name == "nt":
            return ("cmd", "/c", str(wrapper), self.production_task, "--no-daemon", "--stacktrace", "--console=plain", *launch_properties)
        return (
            str(wrapper),
            self.production_task,
            "--no-daemon",
            "--stacktrace",
            "--console=plain",
            *launch_properties,
        )

    def _run_command(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        preexec_fn = None if os.name == "nt" else os.setsid
        env = os.environ.copy()
        env.update(self.environment_overrides)
        proc = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
            env=env,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_process_tree(proc.pid)
            stdout, stderr = proc.communicate()
        finished_at = datetime.now(timezone.utc)
        return {
            "command_display": " ".join(str(part) for part in command),
            "cwd": cwd,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": max((finished_at - started_at).total_seconds(), 0.0),
            "exit_code": int(proc.returncode or 0),
            "timed_out": timed_out,
            "stdout": stdout or "",
            "stderr": stderr or "",
        }

    def _kill_process_tree(self, pid: int) -> None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
            return
        try:
            os.killpg(pid, 9)
        except OSError:
            pass

    def _collect_runtime_evidence(
        self,
        evidence_paths: MinecraftEvidencePaths,
        runtime_root: Path,
        *,
        metadata: Mapping[str, Any],
        harness_result_path: Path | None,
    ) -> MinecraftRuntimeEvidence:
        runtime_root = Path(runtime_root)
        latest_log_src = runtime_root / "logs" / "latest.log"
        if not latest_log_src.exists():
            alt_latest = runtime_root / "latest.log"
            latest_log_src = alt_latest if alt_latest.exists() else latest_log_src
        latest_log_path = None
        if latest_log_src.exists():
            latest_log_path = evidence_paths.latest_log
            latest_log_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(latest_log_src, latest_log_path)

        crash_reports_src = runtime_root / "crash-reports"
        crash_reports_path = None
        if crash_reports_src.exists():
            crash_reports_path = evidence_paths.crash_reports_dir
            if crash_reports_path.exists():
                shutil.rmtree(crash_reports_path)
            shutil.copytree(crash_reports_src, crash_reports_path)

        return MinecraftRuntimeEvidence(
            harness_result_path=harness_result_path if harness_result_path.exists() else None,
            latest_log_path=latest_log_path,
            crash_reports_dir=crash_reports_path,
            metadata=dict(metadata),
        )

    def _read_harness_result(self, path: Path) -> Mapping[str, Any] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {"_malformed": True, "_error": str(exc), "_raw": path.read_text(encoding="utf-8", errors="replace")}
        if not isinstance(data, Mapping):
            return {"_malformed": True, "_error": "harness result must be an object"}
        return data

    def _target_startup_failure_from_log(
        self,
        latest_log: str | None,
        *,
        target: MinecraftTargetMetadata,
    ) -> str | None:
        if not latest_log:
            return None

        required_markers = (
            "Failed to start the minecraft server",
            "Could not execute entrypoint stage",
            f"provided by '{target.mod_id}'",
        )
        if not all(marker in latest_log for marker in required_markers):
            return None

        evidence_lines = [
            line.strip()
            for line in latest_log.splitlines()
            if (
                "Failed to start the minecraft server" in line
                or "Could not execute entrypoint stage" in line
                or f"provided by '{target.mod_id}'" in line
                or "Caused by:" in line
            )
        ]
        return "\n".join(evidence_lines[:8]) or f"startup failure attributed to {target.mod_id}"

    def _classify_runtime(
        self,
        *,
        process: Mapping[str, Any],
        harness_result: Mapping[str, Any] | None,
        latest_log: str | None,
        launch_mode: str,
        target: MinecraftTargetMetadata,
        timeout_seconds: int,
    ) -> tuple[MinecraftTestStatus, str, dict[str, Any]]:
        metadata: dict[str, Any] = {
            "launch_mode": launch_mode,
            "target_path": str(target.path),
            "target_sha256": target.sha256,
            "target_mod_id": target.mod_id,
            "timeout_seconds": timeout_seconds,
        }
        if process["timed_out"]:
            metadata["classification"] = "TIMEOUT"
            return MinecraftTestStatus.TIMEOUT, "execution timeout", metadata

        if harness_result is None:
            target_startup_failure = self._target_startup_failure_from_log(
                latest_log,
                target=target,
            )
            if target_startup_failure is not None:
                metadata["classification"] = "CRASH"
                metadata["target_startup_failure"] = True
                metadata["target_startup_failure_evidence"] = target_startup_failure
                target_failure_reason = self._target_startup_failure_reason(target_startup_failure)
                if target_failure_reason is not None:
                    metadata["target_failure_reason"] = target_failure_reason
                return (
                    MinecraftTestStatus.CRASH,
                    "target mod failed during Minecraft startup",
                    metadata,
                )

            if process["exit_code"] != 0:
                metadata["classification"] = "CRASH"
                return MinecraftTestStatus.CRASH, "Minecraft process exited abnormally", metadata

            metadata["classification"] = "INFRA_ERROR"
            return MinecraftTestStatus.INFRA_ERROR, "missing harness result", metadata

        if harness_result.get("_malformed"):
            metadata["classification"] = "INFRA_ERROR"
            metadata["malformed_error"] = harness_result.get("_error")
            return MinecraftTestStatus.INFRA_ERROR, "malformed harness result", metadata

        target_loaded = bool(harness_result.get("target_loaded"))
        target_origin_resolved = bool(harness_result.get("target_origin_resolved"))
        target_sha_match = bool(harness_result.get("target_sha_match"))
        server_started = bool(harness_result.get("server_started"))
        functional_test_result = str(harness_result.get("functional_test_result", "")).upper()
        shutdown_requested = bool(harness_result.get("shutdown_requested"))
        reason = str(harness_result.get("reason", "")).strip() or "runtime completed"

        metadata.update(
            {
                "target_loaded": target_loaded,
                "target_origin_resolved": target_origin_resolved,
                "target_sha_match": target_sha_match,
                "server_started": server_started,
                "functional_test_result": functional_test_result,
                "shutdown_requested": shutdown_requested,
            }
        )
        if command_payload := harness_result.get("command_result"):
            try:
                metadata["command_result"] = CommandResult.from_dict(command_payload).to_dict()
            except (TypeError, ValueError) as exc:
                metadata["command_result_error"] = str(exc)
        if result_type := harness_result.get("observation_type"):
            if str(result_type).upper() == MinecraftObservationType.ITEM_COMPONENT_STATE.value:
                observation = ObservationResult(
                    observation_id=str(harness_result.get("test_id", "")),
                    observation_type=MinecraftObservationType.ITEM_COMPONENT_STATE,
                    status=(
                        MinecraftObservationStatus.PASS
                        if functional_test_result == "PASS"
                        else MinecraftObservationStatus(functional_test_result)
                    ),
                    expected={
                        "component_id": harness_result.get("component_id"),
                        "item_id": harness_result.get("item_id"),
                        "present": True,
                        "value": harness_result.get("component_json_after"),
                    },
                    actual={
                        "component_id": harness_result.get("component_id"),
                        "item_id": harness_result.get("item_id"),
                        "present_before": not bool(harness_result.get("component_absent_before")),
                        "present_after": harness_result.get("component_json_after") is not None,
                        "value_after_mutation": harness_result.get("component_json_after_mutation"),
                        "value_after": harness_result.get("component_json_after"),
                        "value_restored": harness_result.get("component_json_restored"),
                        "round_trip": harness_result.get("component_round_trip"),
                    },
                    phase="RUNTIME",
                    evidence_refs=(
                        MinecraftEvidenceReference(
                            kind=MinecraftEvidenceKind.OBSERVATION,
                            ref="harness-result.json",
                            phase="RUNTIME",
                        ),
                    ),
                    error=(
                        None
                        if functional_test_result == "PASS"
                        else {"code": "ITEM_COMPONENT_STATE_MISMATCH", "message": reason}
                    ),
                )
                metadata["observation_result"] = observation.to_dict()
            elif str(result_type).upper() in {
                MinecraftObservationType.BLOCK_ENTITY_STATE.value,
                MinecraftObservationType.INVENTORY_STATE.value,
            }:
                observation_type = MinecraftObservationType(str(result_type).upper())
                observation = ObservationResult(
                    observation_id=str(harness_result.get("test_id", "")),
                    observation_type=observation_type,
                    status=(
                        MinecraftObservationStatus.PASS
                        if functional_test_result == "PASS"
                        else MinecraftObservationStatus(functional_test_result)
                    ),
                    expected=dict(harness_result.get("observation_expected", {})),
                    actual=dict(harness_result.get("observation_actual", {})),
                    phase="RUNTIME",
                    evidence_refs=(
                        MinecraftEvidenceReference(
                            kind=MinecraftEvidenceKind.OBSERVATION,
                            ref="harness-result.json",
                            phase="RUNTIME",
                        ),
                    ),
                    error=(
                        None
                        if functional_test_result == "PASS"
                        else {"code": f"{observation_type.value}_MISMATCH", "message": reason}
                    ),
                )
                metadata["observation_result"] = observation.to_dict()
            elif str(result_type).upper() == MinecraftObservationType.TAG_MEMBERSHIP.value:
                observation = ObservationResult(
                    observation_id=str(harness_result.get("test_id", "")),
                    observation_type=MinecraftObservationType.TAG_MEMBERSHIP,
                    status=(
                        MinecraftObservationStatus.PASS
                        if functional_test_result == "PASS"
                        else MinecraftObservationStatus(functional_test_result)
                    ),
                    expected=dict(harness_result.get("observation_expected", {})),
                    actual=dict(harness_result.get("observation_actual", {})),
                    phase="RUNTIME",
                    evidence_refs=(
                        MinecraftEvidenceReference(
                            kind=MinecraftEvidenceKind.OBSERVATION,
                            ref="harness-result.json",
                            phase="RUNTIME",
                        ),
                    ),
                    error=(
                        None
                        if functional_test_result == "PASS"
                        else {"code": "TAG_MEMBERSHIP_MISMATCH", "message": reason}
                    ),
                )
                metadata["observation_result"] = observation.to_dict()
            elif str(result_type).upper() == MinecraftObservationType.RECIPE_MATCH.value:
                observation = ObservationResult(
                    observation_id=str(harness_result.get("test_id", "")),
                    observation_type=MinecraftObservationType.RECIPE_MATCH,
                    status=(
                        MinecraftObservationStatus.PASS
                        if functional_test_result == "PASS"
                        else MinecraftObservationStatus(functional_test_result)
                    ),
                    expected=dict(harness_result.get("observation_expected", {})),
                    actual=dict(harness_result.get("observation_actual", {})),
                    phase="RUNTIME",
                    evidence_refs=(
                        MinecraftEvidenceReference(
                            kind=MinecraftEvidenceKind.OBSERVATION,
                            ref="harness-result.json",
                            phase="RUNTIME",
                        ),
                    ),
                    error=(
                        None
                        if functional_test_result == "PASS"
                        else {"code": "RECIPE_MATCH_MISMATCH", "message": reason}
                    ),
                )
                metadata["observation_result"] = observation.to_dict()
            elif str(result_type).upper() == MinecraftObservationType.LOOT_RESULT.value:
                observation = ObservationResult(
                    observation_id=str(harness_result.get("test_id", "")),
                    observation_type=MinecraftObservationType.LOOT_RESULT,
                    status=(
                        MinecraftObservationStatus.PASS
                        if functional_test_result == "PASS"
                        else MinecraftObservationStatus(functional_test_result)
                    ),
                    expected=dict(harness_result.get("observation_expected", {})),
                    actual=dict(harness_result.get("observation_actual", {})),
                    phase="RUNTIME",
                    evidence_refs=(MinecraftEvidenceReference(
                        kind=MinecraftEvidenceKind.OBSERVATION,
                        ref="harness-result.json",
                        phase="RUNTIME",
                    ),),
                    error=(None if functional_test_result == "PASS" else {
                        "code": "LOOT_RESULT_MISMATCH", "message": reason
                    }),
                )
                metadata["observation_result"] = observation.to_dict()

        if not target_loaded or not target_origin_resolved or not target_sha_match:
            metadata["classification"] = "INFRA_ERROR"
            return MinecraftTestStatus.INFRA_ERROR, reason, metadata

        if not server_started or not shutdown_requested:
            metadata["classification"] = "INFRA_ERROR"
            return MinecraftTestStatus.INFRA_ERROR, reason, metadata

        if process["exit_code"] != 0:
            metadata["classification"] = "CRASH"
            return MinecraftTestStatus.CRASH, reason, metadata

        if functional_test_result == "FAIL":
            metadata["classification"] = "FAIL"
            return MinecraftTestStatus.FAIL, reason, metadata

        if functional_test_result in {"BLOCKED", "INVALID"}:
            metadata["classification"] = functional_test_result
            return MinecraftTestStatus.INFRA_ERROR, reason, metadata

        if functional_test_result != "PASS":
            metadata["classification"] = "INFRA_ERROR"
            return MinecraftTestStatus.INFRA_ERROR, "unexpected harness result", metadata

        metadata["classification"] = "PASS"
        return MinecraftTestStatus.PASS, reason, metadata

    @staticmethod
    def _target_startup_failure_reason(evidence: str) -> str | None:
        """Extract one compact, target-attributable startup cause from evidence."""

        for marker in ("Item id not set", "Block id not set", "target initialization exception"):
            if marker.casefold() in evidence.casefold():
                return marker
        return None

    def _finalize_runtime_failure(
        self,
        preflight: MinecraftTestResult,
        *,
        status: MinecraftTestStatus,
        reason: str,
        metadata: Mapping[str, Any],
    ) -> MinecraftTestResult:
        result = MinecraftTestResult(
            run_id=preflight.run_id,
            status=status,
            reason=reason,
            spec=preflight.spec,
            target=preflight.target,
            evidence_paths=preflight.evidence_paths,
            launch_plan=preflight.launch_plan,
            process_evidence=None,
            runtime_evidence=MinecraftRuntimeEvidence(metadata=dict(metadata)),
            started_at=preflight.started_at,
            finished_at=datetime.now(timezone.utc),
            duration_seconds=0.0,
            metadata=dict(metadata),
        )
        _write_json(preflight.evidence_paths.result_json, result.to_dict())
        return result

    def _validate_runtime_mod_dependencies(
        self,
        runtime_mod_jars: Sequence[Path],
        *,
        target_path: Path,
        authorized_runtime_roots: Sequence[Path] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        roots = tuple(
            Path(root).resolve(strict=True)
            for root in (authorized_runtime_roots if authorized_runtime_roots is not None else (self.project_root,))
        )
        if not roots:
            roots = (self.project_root,)
        resolved_target = Path(target_path).resolve(strict=True)
        validated: list[dict[str, Any]] = []
        seen_paths: set[str] = set()

        for raw_path in runtime_mod_jars:
            candidate = Path(raw_path).expanduser()
            if not str(candidate).strip():
                raise MinecraftTestValidationError("runtime mod dependency path cannot be empty")

            resolved_candidate = self._resolve_runtime_mod_dependency(candidate, roots)
            if resolved_candidate == resolved_target:
                raise MinecraftTestValidationError("runtime mod dependency cannot be the target jar")
            if resolved_candidate.suffix.lower() != ".jar":
                raise MinecraftTestValidationError("runtime mod dependency must be a .jar file")
            if not resolved_candidate.is_file():
                raise MinecraftTestValidationError(f"runtime mod dependency is not a file: {resolved_candidate}")
            if not zipfile.is_zipfile(resolved_candidate):
                raise MinecraftTestValidationError(f"runtime mod dependency is not a valid jar: {resolved_candidate}")

            resolved_key = resolved_candidate.as_posix().casefold()
            if resolved_key in seen_paths:
                raise MinecraftTestValidationError(
                    f"runtime mod dependency duplicates are not allowed: {resolved_candidate}"
                )
            seen_paths.add(resolved_key)
            validated.append(
                {
                    "path": resolved_candidate.as_posix(),
                    "sha256": _sha256(resolved_candidate),
                    "source": None,
                }
            )

        return tuple(validated)

    def _resolve_runtime_mod_dependency(self, raw_path: Path, roots: Sequence[Path]) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            try:
                resolved = candidate.resolve(strict=True)
            except FileNotFoundError as exc:
                raise MinecraftTestValidationError(f"missing runtime mod dependency: {candidate}") from exc
            if not any(_is_within_root(resolved, root) for root in roots):
                raise SecurityViolation(f"runtime mod dependency escapes authorized roots: {resolved}")
            return resolved

        matches: list[Path] = []
        for root in roots:
            try:
                resolved = (root / candidate).resolve(strict=True)
            except FileNotFoundError:
                continue
            if _is_within_root(resolved, root):
                matches.append(resolved)
        if not matches:
            raise MinecraftTestValidationError(f"missing runtime mod dependency: {candidate}")
        unique_matches = {item.as_posix().casefold(): item for item in matches}
        if len(unique_matches) > 1:
            raise MinecraftTestValidationError(f"runtime mod dependency path is ambiguous: {candidate}")
        return next(iter(unique_matches.values()))

    def _normalize_launch_mode(self, launch_mode: str) -> str:
        normalized = str(launch_mode).strip().lower()
        if normalized not in {"pass", "functional_fail", "crash", "missing_result", "malformed_result", "hang"}:
            raise MinecraftTestValidationError(f"unsupported launch_mode: {launch_mode}")
        return normalized

    def _resolve_run_id(self, run_id: str | None) -> str:
        if run_id is not None:
            value = str(run_id).strip()
            if not value:
                raise MinecraftTestValidationError("run_id cannot be empty")
            return value
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


__all__ = ["MinecraftTestRunner"]
