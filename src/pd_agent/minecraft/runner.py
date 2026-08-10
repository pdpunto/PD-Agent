"""Minecraft test harness runner skeleton."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from pd_agent.tools import SecurePathResolver

from .contracts import (
    MinecraftEvidencePaths,
    MinecraftLaunchPlan,
    MinecraftTargetMetadata,
    MinecraftTestResult,
    MinecraftTestSpec,
    MinecraftTestStatus,
)
from .errors import MinecraftTestValidationError, UnsupportedMinecraftEnvironmentError


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
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


def _non_empty_set(values: Sequence[str] | None) -> frozenset[str]:
    if values is None:
        return frozenset()
    return frozenset(str(item).strip() for item in values if str(item).strip())


@dataclass(slots=True)
class MinecraftTestRunner:
    """Validate Minecraft runtime contracts without launching Minecraft yet."""

    project_root: Path
    evidence_root: Path | None = None
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
        object.__setattr__(self, "supported_minecraft_versions", _non_empty_set(tuple(self.supported_minecraft_versions)))
        object.__setattr__(self, "supported_loader_versions", _non_empty_set(tuple(self.supported_loader_versions)))
        object.__setattr__(self, "supported_java_versions", _non_empty_set(tuple(self.supported_java_versions)))

    def validate_spec(self, spec: MinecraftTestSpec, *, java_version: str | None = None) -> None:
        if spec.minecraft_version not in self.supported_minecraft_versions:
            raise UnsupportedMinecraftEnvironmentError(
                f"unsupported minecraft_version: {spec.minecraft_version}"
            )
        if spec.loader_version not in self.supported_loader_versions:
            raise UnsupportedMinecraftEnvironmentError(f"unsupported loader_version: {spec.loader_version}")
        if java_version is not None and java_version not in self.supported_java_versions:
            raise UnsupportedMinecraftEnvironmentError(f"unsupported java_version: {java_version}")

    def validate_target(self, spec: MinecraftTestSpec, *, java_version: str | None = None) -> MinecraftTargetMetadata:
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
        paths = MinecraftEvidencePaths.for_run(self.evidence_root, run_id, create=create)
        return paths

    def build_launch_plan(
        self,
        spec: MinecraftTestSpec,
        *,
        run_id: str | None = None,
        java_version: str | None = None,
    ) -> MinecraftLaunchPlan:
        run_id = self._resolve_run_id(run_id)
        target = self.validate_target(spec, java_version=java_version)
        evidence_paths = self.build_evidence_paths(run_id, create=True)
        run_dir = evidence_paths.root / "runtime"
        system_properties = (
            ("pd.agent.minecraft.run_id", run_id),
            ("pd.agent.minecraft.target_mod_id", spec.target_mod_id),
            ("pd.agent.minecraft.expected_sha256", target.sha256),
            ("pd.agent.minecraft.test_id", spec.test_id),
            ("pd.agent.minecraft.result_path", evidence_paths.result_json.as_posix()),
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
            metadata={"phase": "batch-a"},
        )

    def run(
        self,
        spec: MinecraftTestSpec,
        *,
        run_id: str | None = None,
        java_version: str | None = None,
    ) -> MinecraftTestResult:
        return self.prepare_run(spec, run_id=run_id, java_version=java_version)

    def _resolve_run_id(self, run_id: str | None) -> str:
        if run_id is not None:
            value = str(run_id).strip()
            if not value:
                raise MinecraftTestValidationError("run_id cannot be empty")
            return value
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
