"""Artifact validation for Fabric build outputs."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from pd_agent.core import ArtifactResult, ArtifactValidationError, BuildResult
from pd_agent.project import ProjectSnapshot
from pd_agent.reporting import RunEvent, RunEventType, RunStorage


class ArtifactClassification(StrEnum):
    """Small explicit artifact classification set."""

    VALID = "VALID"
    MISSING = "MISSING"
    EMPTY = "EMPTY"
    CORRUPT = "CORRUPT"
    INVALID_METADATA = "INVALID_METADATA"
    AMBIGUOUS = "AMBIGUOUS"
    STALE = "STALE"
    BUILD_FAILED = "BUILD_FAILED"


@dataclass(frozen=True, slots=True)
class _Candidate:
    path: Path
    size: int
    timestamp: datetime
    root_entries: tuple[str, ...]
    mod_id: str | None
    version: str | None
    expected_mod_id: str | None
    expected_version: str | None
    classification: ArtifactClassification
    issues: tuple[str, ...]
    jar_entries_checked: int = 0
    required_entries_checked: tuple[str, ...] = ()
    missing_required_entries: tuple[str, ...] = ()


class ArtifactValidator:
    """Readonly validator for Fabric build jars."""

    def __init__(
        self,
        reporting: RunStorage | None = None,
        freshness_window_seconds: float = 1.0,
    ) -> None:
        self.reporting = reporting
        self.freshness_window_seconds = freshness_window_seconds

    def validate(
        self,
        project_snapshot: ProjectSnapshot,
        build_result: BuildResult,
        *,
        run_id: str | None = None,
        required_entries: tuple[str, ...] | list[str] | None = None,
    ) -> ArtifactResult:
        if build_result is None:  # pragma: no cover - defensive guard
            raise ArtifactValidationError("build_result is required")

        if not build_result.success:
            result = ArtifactResult(
                path=None,
                size=0,
                timestamp=build_result.started_at,
                classification=ArtifactClassification.BUILD_FAILED.value,
                metadata={
                    "valid": False,
                    "issues": ["build failed"],
                    "candidate_count": 0,
                    "filtered_candidate_count": 0,
                    "target_subproject": self._path_text(project_snapshot.target_subproject),
                },
            )
            self._emit(run_id, result, project_snapshot.project_root)
            return result

        normalized_entries, entry_error = self._normalize_required_entries(required_entries)
        if entry_error is not None:
            result = ArtifactResult(
                path=None,
                size=0,
                timestamp=build_result.started_at,
                classification=ArtifactClassification.INVALID_METADATA.value,
                metadata={
                    "valid": False,
                    "issues": [entry_error],
                    "candidate_count": 0,
                    "filtered_candidate_count": 0,
                    "required_entries": list(normalized_entries),
                    "required_entries_checked": list(normalized_entries),
                    "missing_required_entries": [],
                },
            )
            self._emit(run_id, result, project_snapshot.project_root)
            return result

        target_root = self._target_root(project_snapshot)
        libs_dir = target_root / "build" / "libs"
        candidate_paths = self._discover_candidates(libs_dir)
        if not candidate_paths:
            result = ArtifactResult(
                path=None,
                size=0,
                timestamp=build_result.started_at,
                classification=ArtifactClassification.MISSING.value,
                metadata={
                    "valid": False,
                    "issues": ["no jar candidates found"],
                    "candidate_count": 0,
                    "filtered_candidate_count": 0,
                    "directory": str(libs_dir),
                    "target_subproject": self._path_text(project_snapshot.target_subproject),
                },
            )
            self._emit(run_id, result, project_snapshot.project_root)
            return result

        candidates = tuple(
            self._classify_candidate(
                path,
                project_snapshot=project_snapshot,
                build_result=build_result,
                target_root=target_root,
                candidate_count=len(candidate_paths),
                required_entries=normalized_entries,
            )
            for path in candidate_paths
        )
        result = self._select_result(candidates, build_result)
        self._emit(run_id, result, project_snapshot.project_root)
        return result

    def _select_result(self, candidates: tuple[_Candidate, ...], build_result: BuildResult) -> ArtifactResult:
        valid = [candidate for candidate in candidates if candidate.classification == ArtifactClassification.VALID]

        if len(candidates) == 1:
            return self._as_result(candidates[0], len(candidates))

        if len(valid) == 1:
            return self._as_result(valid[0], len(candidates))

        if len(valid) > 1:
            preferred = self._prefer_expected(valid)
            if preferred is not None:
                return self._as_result(preferred, len(candidates))
            return self._ambiguous_result(candidates, build_result, "multiple valid jars")

        return self._ambiguous_result(candidates, build_result, "multiple jar candidates")

    def _prefer_expected(self, candidates: list[_Candidate]) -> _Candidate | None:
        matched = [
            candidate
            for candidate in candidates
            if candidate.expected_mod_id is not None
            and candidate.expected_version is not None
            and candidate.mod_id == candidate.expected_mod_id
            and candidate.version == candidate.expected_version
        ]
        if len(matched) == 1:
            return matched[0]
        return None

    def _as_result(self, candidate: _Candidate, candidate_count: int) -> ArtifactResult:
        metadata = {
            "valid": candidate.classification == ArtifactClassification.VALID,
            "issues": list(candidate.issues),
            "candidate_count": candidate_count,
            "filtered_candidate_count": candidate_count,
            "jar_entries_checked": candidate.jar_entries_checked,
            "mod_id": candidate.mod_id,
            "version": candidate.version,
            "expected_mod_id": candidate.expected_mod_id,
            "expected_version": candidate.expected_version,
            "root_entries": list(candidate.root_entries),
            "required_entries": list(candidate.required_entries_checked),
            "required_entries_checked": list(candidate.required_entries_checked),
            "missing_required_entries": list(candidate.missing_required_entries),
        }
        return ArtifactResult(
            path=candidate.path,
            size=candidate.size,
            timestamp=candidate.timestamp,
            classification=candidate.classification.value,
            metadata=metadata,
        )

    def _ambiguous_result(
        self,
        candidates: tuple[_Candidate, ...],
        build_result: BuildResult,
        issue: str,
    ) -> ArtifactResult:
        return ArtifactResult(
            path=None,
            size=0,
            timestamp=build_result.started_at,
            classification=ArtifactClassification.AMBIGUOUS.value,
            metadata={
                "valid": False,
                "issues": [issue],
                "candidate_count": len(candidates),
                "filtered_candidate_count": len(candidates),
            },
        )

    def _classify_candidate(
        self,
        path: Path,
        *,
        project_snapshot: ProjectSnapshot,
        build_result: BuildResult,
        target_root: Path,
        candidate_count: int,
        required_entries: tuple[str, ...],
    ) -> _Candidate:
        stat = path.stat()
        timestamp = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        size = stat.st_size
        expected = self._expected_metadata(project_snapshot, target_root)

        if size == 0:
            return _Candidate(
                path=path,
                size=size,
                timestamp=timestamp,
                root_entries=(),
                mod_id=None,
                version=None,
                expected_mod_id=expected["mod_id"],
                expected_version=expected["version"],
                classification=ArtifactClassification.EMPTY,
                issues=("empty jar",),
                required_entries_checked=required_entries,
            )

        if not zipfile.is_zipfile(path):
            return _Candidate(
                path=path,
                size=size,
                timestamp=timestamp,
                root_entries=(),
                mod_id=None,
                version=None,
                expected_mod_id=expected["mod_id"],
                expected_version=expected["version"],
                classification=ArtifactClassification.CORRUPT,
                issues=("not a valid zip",),
                required_entries_checked=required_entries,
            )

        try:
            with zipfile.ZipFile(path) as jar:
                entries = tuple(jar.namelist())
                root_entries = tuple(self._root_entry_names(entries))
                if "fabric.mod.json" not in root_entries:
                    return _Candidate(
                        path=path,
                        size=size,
                        timestamp=timestamp,
                        root_entries=root_entries,
                        mod_id=None,
                        version=None,
                        expected_mod_id=expected["mod_id"],
                        expected_version=expected["version"],
                        classification=ArtifactClassification.INVALID_METADATA,
                        issues=("missing root fabric.mod.json",),
                        jar_entries_checked=len(entries),
                        required_entries_checked=required_entries,
                    )
                raw_manifest = jar.read("fabric.mod.json").decode("utf-8")
        except (zipfile.BadZipFile, OSError, KeyError, UnicodeDecodeError):
            return _Candidate(
                path=path,
                size=size,
                timestamp=timestamp,
                root_entries=(),
                mod_id=None,
                version=None,
                expected_mod_id=expected["mod_id"],
                expected_version=expected["version"],
                classification=ArtifactClassification.CORRUPT,
                issues=("corrupt jar",),
                required_entries_checked=required_entries,
            )

        try:
            manifest = json.loads(raw_manifest)
        except json.JSONDecodeError:
            return _Candidate(
                path=path,
                size=size,
                timestamp=timestamp,
                root_entries=root_entries,
                mod_id=None,
                version=None,
                expected_mod_id=expected["mod_id"],
                expected_version=expected["version"],
                classification=ArtifactClassification.INVALID_METADATA,
                issues=("invalid fabric.mod.json JSON",),
                jar_entries_checked=len(entries),
                required_entries_checked=required_entries,
            )

        if not isinstance(manifest, Mapping):
            return _Candidate(
                path=path,
                size=size,
                timestamp=timestamp,
                root_entries=root_entries,
                mod_id=None,
                version=None,
                expected_mod_id=expected["mod_id"],
                expected_version=expected["version"],
                classification=ArtifactClassification.INVALID_METADATA,
                issues=("fabric.mod.json is not an object",),
                jar_entries_checked=len(entries),
                required_entries_checked=required_entries,
            )

        mod_id = self._coerce_str(manifest.get("id"))
        version = self._coerce_str(manifest.get("version"))
        issues: list[str] = []
        if mod_id is None:
            issues.append("missing id")
        if version is None:
            issues.append("missing version")
        if expected["mod_id"] is not None and mod_id is not None and mod_id != expected["mod_id"]:
            issues.append("mod id mismatch")
        if expected["version"] is not None and version is not None and version != expected["version"]:
            issues.append("version mismatch")

        stale = self._is_stale(timestamp, build_result.started_at)
        if stale:
            issues.append("stale artifact")
        missing_required_entries = tuple(entry for entry in required_entries if entry not in entries)
        if missing_required_entries:
            issues.append("missing required entries: " + ", ".join(missing_required_entries))

        if issues and any(
            issue in {"missing id", "missing version", "mod id mismatch", "version mismatch"}
            for issue in issues
        ):
            classification = ArtifactClassification.INVALID_METADATA
        elif stale:
            classification = ArtifactClassification.STALE
        elif missing_required_entries:
            classification = ArtifactClassification.INVALID_METADATA
        else:
            classification = ArtifactClassification.VALID

        return _Candidate(
            path=path,
            size=size,
            timestamp=timestamp,
            root_entries=root_entries,
            mod_id=mod_id,
            version=version,
            expected_mod_id=expected["mod_id"],
            expected_version=expected["version"],
            classification=classification,
            issues=tuple(issues),
            jar_entries_checked=len(entries),
            required_entries_checked=required_entries,
            missing_required_entries=missing_required_entries,
        )

    def _normalize_required_entries(
        self, required_entries: tuple[str, ...] | list[str] | None
    ) -> tuple[tuple[str, ...], str | None]:
        if required_entries is None:
            return (), None
        if not isinstance(required_entries, (list, tuple)):
            return (), "required_entries must be a sequence"
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in required_entries:
            if not isinstance(raw, str):
                return tuple(normalized), "required entry must be a string"
            entry = raw.replace("\\", "/").strip()
            if not entry or entry.startswith("/") or entry.startswith("\\"):
                return tuple(normalized), f"invalid required JAR entry: {raw!r}"
            parts = entry.split("/")
            if any(part in {"", ".", ".."} for part in parts):
                return tuple(normalized), f"invalid required JAR entry: {raw!r}"
            if ":" in parts[0] or entry.startswith("//"):
                return tuple(normalized), f"invalid required JAR entry: {raw!r}"
            if entry in seen:
                return tuple(normalized), f"duplicate required JAR entry: {entry}"
            seen.add(entry)
            normalized.append(entry)
        return tuple(normalized), None

    def _discover_candidates(self, libs_dir: Path) -> tuple[Path, ...]:
        if not libs_dir.exists():
            return ()
        jars = [
            path
            for path in libs_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".jar"
            and not self._is_auxiliary(path.name)
        ]
        return tuple(sorted(jars, key=lambda path: str(path).casefold()))

    def _target_root(self, project_snapshot: ProjectSnapshot) -> Path:
        if project_snapshot.target_subproject is not None:
            return project_snapshot.target_subproject.resolve(strict=False)
        return project_snapshot.project_root.resolve(strict=False)

    def _expected_metadata(self, project_snapshot: ProjectSnapshot, target_root: Path) -> dict[str, str | None]:
        manifests = [
            manifest
            for manifest in project_snapshot.fabric_manifests
            if self._manifest_root(manifest.path) == target_root
        ]
        manifest = manifests[0] if len(manifests) == 1 else None
        return {
            "mod_id": manifest.mod_id if manifest is not None else None,
            "version": manifest.version if manifest is not None else None,
        }

    def _manifest_root(self, manifest_path: Path) -> Path:
        posix = manifest_path.as_posix()
        if posix.endswith("/src/main/resources/fabric.mod.json") and len(manifest_path.parents) > 3:
            return manifest_path.parents[3].resolve(strict=False)
        return manifest_path.parent.resolve(strict=False)

    def _root_entry_names(self, entries: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            name
            for name in entries
            if "/" not in name.rstrip("/") and not name.startswith("__MACOSX/")
        )

    def _is_stale(self, artifact_timestamp: datetime, build_started_at: datetime) -> bool:
        return artifact_timestamp.timestamp() + self.freshness_window_seconds < build_started_at.timestamp()

    def _coerce_str(self, value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    def _is_auxiliary(self, filename: str) -> bool:
        lowered = filename.lower()
        return any(lowered.endswith(suffix) for suffix in ("-sources.jar", "-javadoc.jar", "-dev.jar"))

    def _emit(self, run_id: str | None, result: ArtifactResult, project_root: Path) -> None:
        if run_id is None or self.reporting is None:
            return
        self.reporting.append_event(
            RunEvent(
                run_id=run_id,
                event_type=RunEventType.ARTIFACT_VALIDATED,
                payload={
                    "path": (
                        result.path.relative_to(project_root).as_posix()
                        if result.path is not None and result.path.is_relative_to(project_root)
                        else str(result.path) if result.path is not None else None
                    ),
                    "size": result.size,
                    "timestamp": result.timestamp.isoformat(),
                    "classification": result.classification,
                    "valid": result.classification == ArtifactClassification.VALID.value,
                    "metadata": {
                        "mod_id": result.metadata.get("mod_id"),
                        "version": result.metadata.get("version"),
                        "candidate_count": result.metadata.get("candidate_count"),
                        "jar_entries_checked": result.metadata.get("jar_entries_checked"),
                        "required_entries_checked": result.metadata.get("required_entries_checked", []),
                        "missing_required_entries": result.metadata.get("missing_required_entries", []),
                        "issues": result.metadata.get("issues", []),
                    },
                },
            )
        )

    def _path_text(self, path: Path | None) -> str | None:
        return str(path) if path is not None else None
