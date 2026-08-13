"""Gradle benchmark environment seed and materialization helpers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
DEFAULT_SEED_ID = "gradle-wrapper-caches"
DEFAULT_SEED_VERSION = "1"
DEFAULT_BOOTSTRAP_STATUS = "READY"


class BenchmarkGradleEnvironmentError(ValueError):
    """Raised when the Gradle benchmark environment cannot be prepared."""


def _json_ready(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_ready(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))}
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return [_json_ready(item) for item in sorted(value, key=repr)]
    return value


def _canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(_json_ready(dict(data)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _iter_seed_files(root: Path) -> tuple[tuple[str, Path], ...]:
    items: list[tuple[str, Path]] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(dirnames, key=str.casefold)
        for dirname in dirnames:
            candidate = current_path / dirname
            if candidate.is_symlink():
                raise BenchmarkGradleEnvironmentError(f"symlink not allowed in Gradle seed: {candidate}")
        for filename in sorted(filenames, key=str.casefold):
            candidate = current_path / filename
            if candidate.is_symlink():
                raise BenchmarkGradleEnvironmentError(f"symlink not allowed in Gradle seed: {candidate}")
            if not candidate.is_file():
                continue
            items.append((candidate.relative_to(root).as_posix(), candidate))
    return tuple(items)


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkGradleSeedComponent:
    """One file entry in a Gradle seed manifest."""

    path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "size_bytes", int(self.size_bytes))
        object.__setattr__(self, "sha256", str(self.sha256))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkGradleSeedComponent":
        return cls(
            path=str(data["path"]),
            size_bytes=int(data["size_bytes"]),
            sha256=str(data["sha256"]),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkGradleSeedManifest:
    """Canonical inventory of a Gradle seed."""

    schema_version: int = SCHEMA_VERSION
    seed_id: str = DEFAULT_SEED_ID
    seed_version: str = DEFAULT_SEED_VERSION
    source_root: str | None = None
    components: tuple[BenchmarkGradleSeedComponent, ...] = ()
    total_size_bytes: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    identity_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed_id", str(self.seed_id))
        object.__setattr__(self, "seed_version", str(self.seed_version))
        object.__setattr__(self, "source_root", str(self.source_root) if self.source_root is not None else None)
        object.__setattr__(self, "components", tuple(self.components))
        object.__setattr__(self, "total_size_bytes", int(self.total_size_bytes))
        computed_hash = self.compute_identity_hash()
        if self.identity_hash is None:
            object.__setattr__(self, "identity_hash", computed_hash)
        elif str(self.identity_hash) != computed_hash:
            raise BenchmarkGradleEnvironmentError(
                f"seed manifest hash mismatch: expected {self.identity_hash}, computed {computed_hash}"
            )

    @property
    def component_count(self) -> int:
        return len(self.components)

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "seed_id": self.seed_id,
            "seed_version": self.seed_version,
            "components": [component.to_dict() for component in self.components],
            "total_size_bytes": self.total_size_bytes,
        }

    def compute_identity_hash(self) -> str:
        return _sha256_bytes(_canonical_json(self._identity_payload()).encode("utf-8"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "seed_id": self.seed_id,
            "seed_version": self.seed_version,
            "source_root": self.source_root,
            "components": [component.to_dict() for component in self.components],
            "component_count": self.component_count,
            "total_size_bytes": self.total_size_bytes,
            "created_at": self.created_at.isoformat(),
            "identity_hash": self.identity_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkGradleSeedManifest":
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            seed_id=str(data.get("seed_id", DEFAULT_SEED_ID)),
            seed_version=str(data.get("seed_version", DEFAULT_SEED_VERSION)),
            source_root=data.get("source_root"),
            components=tuple(BenchmarkGradleSeedComponent.from_dict(item) for item in data.get("components", [])),
            total_size_bytes=int(data.get("total_size_bytes", 0)),
            created_at=datetime.fromisoformat(str(data.get("created_at", datetime.now(timezone.utc).isoformat()))),
            identity_hash=data.get("identity_hash"),
        )

    @classmethod
    def build(
        cls,
        seed_root: Path,
        *,
        seed_id: str = DEFAULT_SEED_ID,
        seed_version: str = DEFAULT_SEED_VERSION,
    ) -> "BenchmarkGradleSeedManifest":
        root = Path(seed_root).resolve(strict=True)
        if not root.is_dir():
            raise BenchmarkGradleEnvironmentError("Gradle seed root must be an existing directory")
        components: list[BenchmarkGradleSeedComponent] = []
        total_size = 0
        for relative_path, file_path in _iter_seed_files(root):
            size_bytes = file_path.stat().st_size
            total_size += size_bytes
            components.append(
                BenchmarkGradleSeedComponent(
                    path=relative_path,
                    size_bytes=size_bytes,
                    sha256=_sha256_file(file_path),
                )
            )
        return cls(
            seed_id=seed_id,
            seed_version=seed_version,
            source_root=str(root),
            components=tuple(components),
            total_size_bytes=total_size,
        )

    def diff(self, other: "BenchmarkGradleSeedManifest") -> tuple[str, ...]:
        actual = {component.path: component for component in self.components}
        expected = {component.path: component for component in other.components}
        missing = tuple(sorted(set(expected) - set(actual)))
        extra = tuple(sorted(set(actual) - set(expected)))
        mismatched = tuple(
            sorted(
                path
                for path in set(actual).intersection(expected)
                if actual[path].sha256 != expected[path].sha256 or actual[path].size_bytes != expected[path].size_bytes
            )
        )
        return (*[f"missing:{path}" for path in missing], *[f"extra:{path}" for path in extra], *[f"mismatch:{path}" for path in mismatched])


@dataclass(frozen=True, slots=True)
class BenchmarkGradleEnvironment:
    """Materialized Gradle user home plus its verified seed inventory."""

    seed_root: Path
    execution_root: Path
    seed_manifest: BenchmarkGradleSeedManifest
    materialization_root: Path
    gradle_user_home: Path
    bootstrap_status: str = DEFAULT_BOOTSTRAP_STATUS
    offline: bool = True
    source_manifest_path: Path | None = None
    seed_manifest_path: Path | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed_root", Path(self.seed_root).resolve(strict=True))
        object.__setattr__(self, "execution_root", Path(self.execution_root).resolve(strict=True))
        object.__setattr__(self, "seed_manifest", self.seed_manifest)
        object.__setattr__(self, "materialization_root", Path(self.materialization_root).resolve(strict=False))
        object.__setattr__(self, "gradle_user_home", Path(self.gradle_user_home).resolve(strict=False))
        object.__setattr__(self, "bootstrap_status", str(self.bootstrap_status))
        object.__setattr__(self, "offline", bool(self.offline))
        object.__setattr__(
            self,
            "source_manifest_path",
            Path(self.source_manifest_path).resolve(strict=False) if self.source_manifest_path is not None else None,
        )
        object.__setattr__(
            self,
            "seed_manifest_path",
            Path(self.seed_manifest_path).resolve(strict=False) if self.seed_manifest_path is not None else None,
        )
        if self.bootstrap_status != DEFAULT_BOOTSTRAP_STATUS:
            raise BenchmarkGradleEnvironmentError(f"unsupported bootstrap status: {self.bootstrap_status}")
        if not self.gradle_user_home.exists():
            raise BenchmarkGradleEnvironmentError("isolated GRADLE_USER_HOME is missing")
        if not self._is_writable(self.gradle_user_home):
            raise BenchmarkGradleEnvironmentError(f"isolated GRADLE_USER_HOME is not writable: {self.gradle_user_home}")

    @property
    def environment_overrides(self) -> dict[str, str]:
        return {"GRADLE_USER_HOME": str(self.gradle_user_home)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "seed_root": str(self.seed_root),
            "execution_root": str(self.execution_root),
            "materialization_root": str(self.materialization_root),
            "gradle_user_home": str(self.gradle_user_home),
            "bootstrap_status": self.bootstrap_status,
            "offline": self.offline,
            "source_manifest_path": str(self.source_manifest_path) if self.source_manifest_path is not None else None,
            "seed_manifest_path": str(self.seed_manifest_path) if self.seed_manifest_path is not None else None,
            "seed_manifest": self.seed_manifest.to_dict(),
            "created_at": self.created_at.isoformat(),
            "environment_overrides": self.environment_overrides,
        }

    @classmethod
    def prepare(
        cls,
        *,
        seed_root: Path,
        execution_root: Path,
        seed_id: str = DEFAULT_SEED_ID,
        seed_version: str = DEFAULT_SEED_VERSION,
        seed_manifest_path: Path | None = None,
        offline: bool = True,
    ) -> "BenchmarkGradleEnvironment":
        seed_root = Path(seed_root).resolve(strict=True)
        execution_root = Path(execution_root).resolve(strict=True)
        if not seed_root.is_dir():
            raise BenchmarkGradleEnvironmentError("Gradle seed root must be an existing directory")
        if not execution_root.is_dir():
            raise BenchmarkGradleEnvironmentError("execution_root must be an existing directory")

        materialization_root = execution_root / "environment"
        gradle_user_home = materialization_root / "gradle-user-home"
        manifest_dir = materialization_root / "gradle-seed"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "manifest.json"
        bootstrap_path = materialization_root / "bootstrap.json"

        expected_manifest = cls._load_expected_manifest(seed_root, seed_manifest_path, seed_id=seed_id, seed_version=seed_version)
        actual_manifest = BenchmarkGradleSeedManifest.build(seed_root, seed_id=seed_id, seed_version=seed_version)
        selected_manifest = expected_manifest or actual_manifest

        if expected_manifest is not None and actual_manifest.identity_hash != expected_manifest.identity_hash:
            diff = actual_manifest.diff(expected_manifest)
            raise BenchmarkGradleEnvironmentError(
                "Gradle seed manifest mismatch: "
                f"expected={expected_manifest.identity_hash} actual={actual_manifest.identity_hash} diff={list(diff)}"
            )

        if gradle_user_home.exists():
            raise BenchmarkGradleEnvironmentError(f"isolated GRADLE_USER_HOME already exists: {gradle_user_home}")

        gradle_user_home.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(seed_root, gradle_user_home, symlinks=False)
        materialized_manifest = BenchmarkGradleSeedManifest.build(
            gradle_user_home,
            seed_id=selected_manifest.seed_id,
            seed_version=selected_manifest.seed_version,
        )
        if materialized_manifest.identity_hash != selected_manifest.identity_hash:
            diff = materialized_manifest.diff(selected_manifest)
            raise BenchmarkGradleEnvironmentError(
                "materialized Gradle home does not match seed manifest: "
                f"expected={selected_manifest.identity_hash} actual={materialized_manifest.identity_hash} diff={list(diff)}"
            )
        if not cls._is_writable(gradle_user_home):
            raise BenchmarkGradleEnvironmentError(f"isolated GRADLE_USER_HOME is not writable: {gradle_user_home}")

        manifest_path.write_text(json.dumps(selected_manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        bootstrap_payload = {
            "schema_version": SCHEMA_VERSION,
            "bootstrap_status": DEFAULT_BOOTSTRAP_STATUS,
            "offline": bool(offline),
            "seed_root": str(seed_root),
            "execution_root": str(execution_root),
            "materialization_root": str(materialization_root),
            "gradle_user_home": str(gradle_user_home),
            "seed_id": selected_manifest.seed_id,
            "seed_version": selected_manifest.seed_version,
            "manifest_hash": selected_manifest.identity_hash,
            "component_count": selected_manifest.component_count,
            "total_size_bytes": selected_manifest.total_size_bytes,
            "source_manifest_path": str(seed_manifest_path) if seed_manifest_path is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        bootstrap_path.write_text(json.dumps(bootstrap_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

        return cls(
            seed_root=seed_root,
            execution_root=execution_root,
            seed_manifest=selected_manifest,
            materialization_root=materialization_root,
            gradle_user_home=gradle_user_home,
            bootstrap_status=DEFAULT_BOOTSTRAP_STATUS,
            offline=offline,
            source_manifest_path=seed_manifest_path,
            seed_manifest_path=manifest_path,
        )

    @staticmethod
    def _load_expected_manifest(
        seed_root: Path,
        seed_manifest_path: Path | None,
        *,
        seed_id: str,
        seed_version: str,
    ) -> BenchmarkGradleSeedManifest | None:
        candidate = seed_manifest_path
        if candidate is None or not candidate.exists():
            return None
        data = json.loads(candidate.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise BenchmarkGradleEnvironmentError(f"seed manifest must be an object: {candidate}")
        manifest = BenchmarkGradleSeedManifest.from_dict(dict(data))
        if manifest.seed_id != seed_id or manifest.seed_version != seed_version:
            raise BenchmarkGradleEnvironmentError(
                f"seed manifest identity mismatch: expected {seed_id}@{seed_version}, got {manifest.seed_id}@{manifest.seed_version}"
            )
        return manifest

    @staticmethod
    def _is_writable(path: Path) -> bool:
        probe = path / ".pd-agent-write-test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            return False


__all__ = [
    "BenchmarkGradleEnvironment",
    "BenchmarkGradleEnvironmentError",
    "BenchmarkGradleSeedComponent",
    "BenchmarkGradleSeedManifest",
    "DEFAULT_BOOTSTRAP_STATUS",
    "DEFAULT_SEED_ID",
    "DEFAULT_SEED_VERSION",
    "SCHEMA_VERSION",
]
