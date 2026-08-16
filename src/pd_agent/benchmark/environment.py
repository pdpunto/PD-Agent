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
_NONPORTABLE_SEED_FILE_NAMES = frozenset({"file-access.bin", "file-access.properties"})


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
            relative_path = candidate.relative_to(root).as_posix()
            if _is_nonportable_seed_entry(relative_path, current_path=current_path):
                continue
            items.append((candidate.relative_to(root).as_posix(), candidate))
    return tuple(items)


def _is_nonportable_seed_entry(relative_path: str, *, current_path: Path | None = None) -> bool:
    normalized = relative_path.replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1].casefold()
    if filename == "gc.properties":
        return True
    if filename.endswith(".lock") or filename.endswith(".lck"):
        return True
    if normalized.startswith("caches/journal-1/") and filename in _NONPORTABLE_SEED_FILE_NAMES:
        return True
    if current_path is not None and current_path.name.casefold() == "journal-1" and filename in _NONPORTABLE_SEED_FILE_NAMES:
        return True
    return False


def _portable_seed_manifest(manifest: "BenchmarkGradleSeedManifest") -> "BenchmarkGradleSeedManifest":
    portable_components = tuple(
        component
        for component in manifest.components
        if not _is_nonportable_seed_entry(component.path)
    )
    if len(portable_components) == len(manifest.components):
        return manifest
    return BenchmarkGradleSeedManifest(
        schema_version=manifest.schema_version,
        seed_id=manifest.seed_id,
        seed_version=manifest.seed_version,
        source_root=manifest.source_root,
        components=portable_components,
        total_size_bytes=sum(component.size_bytes for component in portable_components),
        created_at=manifest.created_at,
    )


def _sanitize_materialized_gradle_home(root: Path) -> None:
    root = Path(root)
    if not root.exists():
        return
    for current, _, filenames in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current)
        for filename in filenames:
            candidate = current_path / filename
            relative_path = candidate.relative_to(root).as_posix()
            if not _is_nonportable_seed_entry(relative_path, current_path=current_path):
                continue
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkGradleSeedComponent:
    """One file entry in a Gradle seed manifest."""

    path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        normalized_path = str(self.path).replace("\\", "/")
        object.__setattr__(self, "path", normalized_path)
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
        size_bytes = data.get("size_bytes", data.get("size"))
        return cls(
            path=str(data["path"]).replace("\\", "/"),
            size_bytes=int(size_bytes),
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
        raw_components = data.get("components")
        if raw_components is None:
            raw_components = data.get("entries", [])
        total_size_value = data.get("total_size_bytes", data.get("total_bytes", 0))
        created_at_value = data.get("created_at", datetime.now(timezone.utc).isoformat())
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            seed_id=str(data.get("seed_id", DEFAULT_SEED_ID)),
            seed_version=str(data.get("seed_version", DEFAULT_SEED_VERSION)),
            source_root=data.get("source_root"),
            components=tuple(
                sorted(
                    (BenchmarkGradleSeedComponent.from_dict(item) for item in raw_components),
                    key=lambda component: component.path.casefold(),
                )
            ),
            total_size_bytes=int(total_size_value),
            created_at=datetime.fromisoformat(str(created_at_value)),
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
        components.sort(key=lambda component: component.path.casefold())
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
        portable_expected_manifest = _portable_seed_manifest(expected_manifest) if expected_manifest is not None else None
        portable_actual_manifest = _portable_seed_manifest(actual_manifest)
        selected_manifest = portable_expected_manifest or portable_actual_manifest

        if portable_expected_manifest is not None and portable_actual_manifest.identity_hash != portable_expected_manifest.identity_hash:
            diff = portable_actual_manifest.diff(portable_expected_manifest)
            raise BenchmarkGradleEnvironmentError(
                "Gradle seed manifest mismatch: "
                f"expected={portable_expected_manifest.identity_hash} actual={portable_actual_manifest.identity_hash} diff={list(diff)}"
            )

        if gradle_user_home.exists():
            raise BenchmarkGradleEnvironmentError(f"isolated GRADLE_USER_HOME already exists: {gradle_user_home}")

        gradle_user_home.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(seed_root, gradle_user_home, symlinks=False)
        _sanitize_materialized_gradle_home(gradle_user_home)
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

    @classmethod
    def restore(cls, *, execution_root: Path) -> "BenchmarkGradleEnvironment":
        execution_root = Path(execution_root).resolve(strict=True)
        if not execution_root.is_dir():
            raise BenchmarkGradleEnvironmentError("execution_root must be an existing directory")

        materialization_root = execution_root / "environment"
        gradle_user_home = materialization_root / "gradle-user-home"
        manifest_path = materialization_root / "gradle-seed" / "manifest.json"
        bootstrap_path = materialization_root / "bootstrap.json"

        if not gradle_user_home.exists():
            raise BenchmarkGradleEnvironmentError(f"isolated GRADLE_USER_HOME is missing: {gradle_user_home}")
        if not manifest_path.exists():
            raise BenchmarkGradleEnvironmentError(f"Gradle seed manifest missing: {manifest_path}")
        if not bootstrap_path.exists():
            raise BenchmarkGradleEnvironmentError(f"Gradle bootstrap evidence missing: {bootstrap_path}")

        bootstrap_data = json.loads(bootstrap_path.read_text(encoding="utf-8-sig"))
        if not isinstance(bootstrap_data, Mapping):
            raise BenchmarkGradleEnvironmentError(f"bootstrap evidence must be an object: {bootstrap_path}")
        if str(bootstrap_data.get("bootstrap_status", "")) != DEFAULT_BOOTSTRAP_STATUS:
            raise BenchmarkGradleEnvironmentError(
                f"unsupported bootstrap status in resume materialization: {bootstrap_data.get('bootstrap_status')}"
            )
        if not bool(bootstrap_data.get("offline", True)):
            raise BenchmarkGradleEnvironmentError("resume materialization is not offline")

        seed_manifest = BenchmarkGradleSeedManifest.from_dict(
            json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        )
        _sanitize_materialized_gradle_home(gradle_user_home)
        actual_manifest = BenchmarkGradleSeedManifest.build(
            gradle_user_home,
            seed_id=seed_manifest.seed_id,
            seed_version=seed_manifest.seed_version,
        )
        if actual_manifest.identity_hash != seed_manifest.identity_hash:
            diff = actual_manifest.diff(seed_manifest)
            raise BenchmarkGradleEnvironmentError(
                "restored Gradle home does not match stored seed manifest: "
                f"expected={seed_manifest.identity_hash} actual={actual_manifest.identity_hash} diff={list(diff)}"
            )
        manifest_hash = bootstrap_data.get("manifest_hash")
        if manifest_hash is not None and str(manifest_hash) != seed_manifest.identity_hash:
            raise BenchmarkGradleEnvironmentError(
                f"materialized Gradle home manifest hash mismatch: expected {manifest_hash}, actual {seed_manifest.identity_hash}"
            )
        if not cls._is_writable(gradle_user_home):
            raise BenchmarkGradleEnvironmentError(f"isolated GRADLE_USER_HOME is not writable: {gradle_user_home}")

        instance = object.__new__(cls)
        object.__setattr__(instance, "seed_root", Path(bootstrap_data.get("seed_root", gradle_user_home)).resolve(strict=False))
        object.__setattr__(instance, "execution_root", execution_root)
        object.__setattr__(instance, "seed_manifest", seed_manifest)
        object.__setattr__(instance, "materialization_root", materialization_root)
        object.__setattr__(instance, "gradle_user_home", gradle_user_home)
        object.__setattr__(instance, "bootstrap_status", str(bootstrap_data.get("bootstrap_status", DEFAULT_BOOTSTRAP_STATUS)))
        object.__setattr__(instance, "offline", bool(bootstrap_data.get("offline", True)))
        source_manifest_path = bootstrap_data.get("source_manifest_path")
        object.__setattr__(
            instance,
            "source_manifest_path",
            Path(source_manifest_path).resolve(strict=False) if source_manifest_path is not None else None,
        )
        object.__setattr__(instance, "seed_manifest_path", manifest_path)
        created_at_value = bootstrap_data.get("created_at")
        object.__setattr__(
            instance,
            "created_at",
            datetime.fromisoformat(str(created_at_value)) if created_at_value is not None else datetime.now(timezone.utc),
        )
        return instance

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
        data = json.loads(candidate.read_text(encoding="utf-8-sig"))
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
