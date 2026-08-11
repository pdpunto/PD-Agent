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


def _validate_mod_id(value: object) -> str:
    mod_id = _non_empty_text("target_mod_id", value)
    if not _MOD_ID_RE.fullmatch(mod_id):
        raise ValueError(f"invalid target_mod_id: {mod_id!r}")
    return mod_id


@dataclass(frozen=True, slots=True)
class MinecraftTestSpec:
    """Minimum Minecraft runtime test specification."""

    target_jar: Path
    target_mod_id: str
    minecraft_version: str
    loader_version: str
    test_id: str
    timeout_seconds: int
    expect_neighbor_update: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_jar", _normalize_path(self.target_jar))
        object.__setattr__(self, "target_mod_id", _validate_mod_id(self.target_mod_id))
        object.__setattr__(self, "minecraft_version", _non_empty_text("minecraft_version", self.minecraft_version))
        object.__setattr__(self, "loader_version", _non_empty_text("loader_version", self.loader_version))
        object.__setattr__(self, "test_id", _non_empty_text("test_id", self.test_id))
        timeout_seconds = int(self.timeout_seconds)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        object.__setattr__(self, "timeout_seconds", timeout_seconds)
        object.__setattr__(self, "expect_neighbor_update", bool(self.expect_neighbor_update))

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_jar": self.target_jar.as_posix(),
            "target_mod_id": self.target_mod_id,
            "minecraft_version": self.minecraft_version,
            "loader_version": self.loader_version,
            "test_id": self.test_id,
            "timeout_seconds": self.timeout_seconds,
            "expect_neighbor_update": self.expect_neighbor_update,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MinecraftTestSpec":
        return cls(
            target_jar=Path(data["target_jar"]),
            target_mod_id=str(data["target_mod_id"]),
            minecraft_version=str(data["minecraft_version"]),
            loader_version=str(data["loader_version"]),
            test_id=str(data["test_id"]),
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
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is MinecraftTestStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "reason": self.reason,
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
            metadata=dict(data.get("metadata", {})),
        )
