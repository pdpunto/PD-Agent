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

from pd_agent.tools import SecurePathResolver

from .contracts import (
    MinecraftEvidencePaths,
    MinecraftLaunchPlan,
    MinecraftProcessEvidence,
    MinecraftRuntimeEvidence,
    MinecraftTargetMetadata,
    MinecraftTestResult,
    MinecraftTestSpec,
    MinecraftTestStatus,
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


def _non_empty_set(values: Sequence[str] | None) -> frozenset[str]:
    if values is None:
        return frozenset()
    return frozenset(str(item).strip() for item in values if str(item).strip())


def _read_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


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
            ("pd.agent.minecraft.expect_neighbor_update", str(spec.expect_neighbor_update).lower()),
            ("pd.agent.minecraft.result_path", evidence_paths.harness_result_json.as_posix()),
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
            metadata={
                "phase": "runtime",
                "launch_mode": launch_mode,
                "expected_sha256": expected_sha256 or preflight.target.sha256,
                "command_display": process["command_display"],
                "process_exit_code": process["exit_code"],
                "process_timed_out": process["timed_out"],
                "harness_result_state": harness_result.get("functional_test_result") if isinstance(harness_result, Mapping) else None,
                "harness_result_path": str(harness_result_path),
                "latest_log_path": str(runtime_evidence.latest_log_path) if runtime_evidence.latest_log_path else None,
                "crash_reports_dir": str(runtime_evidence.crash_reports_dir) if runtime_evidence.crash_reports_dir else None,
                "launch_properties": list(launch_props),
                "environment_overrides": dict(self.environment_overrides),
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
            f"-Ppd.agent.resultPath={result.evidence_paths.harness_result_json}",
            f"-Ppd.agent.runDir={result.evidence_paths.root / 'runtime'}",
            f"-Ppd.agent.resultMode={result_mode}",
            f"-Ppd.agent.expectedBlockStateId={expected_block_state_id}",
            f"-Ppd.agent.expectNeighborUpdate={str(result.spec.expect_neighbor_update).lower()}",
            f"-Ppd.agent.hangMillis={hang_millis if launch_mode == 'hang' else '600000'}",
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

    def _classify_runtime(
        self,
        *,
        process: Mapping[str, Any],
        harness_result: Mapping[str, Any] | None,
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

        if functional_test_result != "PASS":
            metadata["classification"] = "INFRA_ERROR"
            return MinecraftTestStatus.INFRA_ERROR, "unexpected harness result", metadata

        metadata["classification"] = "PASS"
        return MinecraftTestStatus.PASS, reason, metadata

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
