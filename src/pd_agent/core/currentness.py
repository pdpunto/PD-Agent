"""Durable identities and currentness facts for the v0.8 I3 foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import ArtifactResult, FabricTaskContract, FabricValidationRequirement


SCHEMA_VERSION = 1
SOURCE_REVISION_ALGORITHM = "sha256-source-tree-v1"
_DEFAULT_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".gradle",
        "build",
        "evidence",
        "reports",
        "report",
        "tmp",
        "temp",
        "runtime",
        "runtime-output",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".venv",
        "venv",
    }
)


def _text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(relative: Path, excluded_parts: frozenset[str]) -> bool:
    return any(part.casefold() in excluded_parts for part in relative.parts)


@dataclass(frozen=True, slots=True)
class SourceRevision:
    revision: str
    algorithm: str = SOURCE_REVISION_ALGORITHM
    file_count: int = 0

    def __post_init__(self) -> None:
        revision = _text(self.revision, field_name="revision").casefold()
        if len(revision) != 64 or any(char not in "0123456789abcdef" for char in revision):
            raise ValueError("revision must be a SHA-256 hex digest")
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "algorithm", _text(self.algorithm, field_name="algorithm"))
        if self.file_count < 0:
            raise ValueError("file_count must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {"revision": self.revision, "algorithm": self.algorithm, "file_count": self.file_count}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceRevision":
        return cls(revision=data["revision"], algorithm=data.get("algorithm", SOURCE_REVISION_ALGORITHM), file_count=int(data.get("file_count", 0)))


def compute_source_revision(
    project_root: Path,
    *,
    excluded_parts: set[str] | frozenset[str] | None = None,
) -> SourceRevision:
    """Hash regular files inside ``project_root`` without following escapes.

    Paths and bytes are framed before hashing. Symlinks are excluded rather than
    followed, so hashing never reads content outside the authorized root.
    """

    root = Path(project_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project_root must be an existing directory")
    excluded = frozenset(part.casefold() for part in (excluded_parts or _DEFAULT_EXCLUDED_PARTS))
    records: list[tuple[str, bytes]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if _excluded(relative, excluded) or path.is_symlink() or not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        records.append((relative.as_posix(), resolved.read_bytes()))

    digest = hashlib.sha256()
    for relative, content in records:
        path_bytes = relative.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return SourceRevision(revision=digest.hexdigest(), file_count=len(records))


def _canonical(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validation_contract_revision(
    requirement: FabricValidationRequirement | Mapping[str, Any],
) -> str:
    """Return the stable identity of one validation obligation."""

    if isinstance(requirement, FabricValidationRequirement):
        payload = requirement.to_dict()
    else:
        payload = FabricValidationRequirement.from_dict(requirement).to_dict()
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BuildAttemptIdentity:
    build_attempt_id: str
    source_revision: str
    contract_identity: tuple[str, str, str]
    toolchain_identity: str | None = None
    result_ref: str | None = None
    success: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "build_attempt_id", _text(self.build_attempt_id, field_name="build_attempt_id"))
        object.__setattr__(self, "source_revision", _text(self.source_revision, field_name="source_revision"))
        if len(self.contract_identity) != 3:
            raise ValueError("contract_identity must contain task, revision and fingerprint")
        object.__setattr__(self, "contract_identity", tuple(_text(item, field_name="contract_identity") for item in self.contract_identity))
        if self.toolchain_identity is not None:
            object.__setattr__(self, "toolchain_identity", _text(self.toolchain_identity, field_name="toolchain_identity"))
        if self.result_ref is not None:
            object.__setattr__(self, "result_ref", _text(self.result_ref, field_name="result_ref"))

    def is_current(self, *, source_revision: str, contract_identity: tuple[str, str, str], toolchain_identity: str | None = None) -> bool:
        return self.success and self.source_revision == source_revision and self.contract_identity == tuple(contract_identity) and (toolchain_identity is None or self.toolchain_identity == toolchain_identity)

    def to_dict(self) -> dict[str, Any]:
        return {"build_attempt_id": self.build_attempt_id, "source_revision": self.source_revision, "contract_identity": list(self.contract_identity), "toolchain_identity": self.toolchain_identity, "result_ref": self.result_ref, "success": self.success}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BuildAttemptIdentity":
        return cls(build_attempt_id=data["build_attempt_id"], source_revision=data["source_revision"], contract_identity=tuple(data["contract_identity"]), toolchain_identity=data.get("toolchain_identity"), result_ref=data.get("result_ref"), success=bool(data.get("success", False)))


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    artifact_identity: str
    sha256: str
    producing_build_attempt_id: str
    source_revision: str
    contract_identity: tuple[str, str, str]

    def __post_init__(self) -> None:
        for name in ("artifact_identity", "sha256", "producing_build_attempt_id", "source_revision"):
            object.__setattr__(self, name, _text(getattr(self, name), field_name=name))
        if len(self.sha256) != 64 or any(char not in "0123456789abcdefABCDEF" for char in self.sha256):
            raise ValueError("sha256 must be a SHA-256 hex digest")
        if len(self.contract_identity) != 3:
            raise ValueError("contract_identity must contain task, revision and fingerprint")
        object.__setattr__(self, "contract_identity", tuple(_text(item, field_name="contract_identity") for item in self.contract_identity))

    def is_current(self, build: BuildAttemptIdentity, *, source_revision: str, contract_identity: tuple[str, str, str]) -> bool:
        return build.is_current(source_revision=source_revision, contract_identity=contract_identity) and build.build_attempt_id == self.producing_build_attempt_id and self.source_revision == source_revision and self.contract_identity == tuple(contract_identity)

    def to_dict(self) -> dict[str, Any]:
        return {"artifact_identity": self.artifact_identity, "sha256": self.sha256, "producing_build_attempt_id": self.producing_build_attempt_id, "source_revision": self.source_revision, "contract_identity": list(self.contract_identity)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactIdentity":
        return cls(artifact_identity=data["artifact_identity"], sha256=data["sha256"], producing_build_attempt_id=data["producing_build_attempt_id"], source_revision=data["source_revision"], contract_identity=tuple(data["contract_identity"]))


def artifact_identity_from_result(
    artifact: ArtifactResult,
    *,
    producing_build_attempt_id: str,
    source_revision: str,
    contract_identity: tuple[str, str, str],
) -> ArtifactIdentity:
    if artifact.path is None or not artifact.path.is_file():
        raise ValueError("a persisted artifact file is required")
    sha256 = _sha256_file(artifact.path)
    return ArtifactIdentity(artifact_identity=sha256, sha256=sha256, producing_build_attempt_id=producing_build_attempt_id, source_revision=source_revision, contract_identity=contract_identity)


@dataclass(frozen=True, slots=True)
class RuntimeAttemptIdentity:
    runtime_attempt_id: str
    artifact_identity: str
    validation_revision: str
    requirement_ids: tuple[str, ...] = ()
    result_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("runtime_attempt_id", "artifact_identity", "validation_revision"):
            object.__setattr__(self, name, _text(getattr(self, name), field_name=name))
        object.__setattr__(self, "requirement_ids", tuple(_text(item, field_name="requirement_id") for item in self.requirement_ids))
        object.__setattr__(self, "result_refs", tuple(_text(item, field_name="result_ref") for item in self.result_refs))

    def is_current(self, *, artifact_identity: str, validation_revision: str) -> bool:
        return self.artifact_identity == artifact_identity and self.validation_revision == validation_revision

    def to_dict(self) -> dict[str, Any]:
        return {"runtime_attempt_id": self.runtime_attempt_id, "artifact_identity": self.artifact_identity, "validation_revision": self.validation_revision, "requirement_ids": list(self.requirement_ids), "result_refs": list(self.result_refs)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimeAttemptIdentity":
        return cls(runtime_attempt_id=data["runtime_attempt_id"], artifact_identity=data["artifact_identity"], validation_revision=data["validation_revision"], requirement_ids=tuple(data.get("requirement_ids", ())), result_refs=tuple(data.get("result_refs", ())))


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    evidence_id: str
    evidence_kind: str
    source_revision: str | None = None
    build_attempt_id: str | None = None
    artifact_identity: str | None = None
    validation_revision: str | None = None
    runtime_attempt_id: str | None = None
    stale_for_completion: bool = False
    stale_reason: str | None = None
    superseding_identity: str | None = None

    def __post_init__(self) -> None:
        for name in ("evidence_id", "evidence_kind"):
            object.__setattr__(self, name, _text(getattr(self, name), field_name=name))
        for name in ("source_revision", "build_attempt_id", "artifact_identity", "validation_revision", "runtime_attempt_id", "stale_reason", "superseding_identity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _text(value, field_name=name))

    def evaluate_currentness(self, *, source_revision: str | None = None, artifact_identity: str | None = None, validation_revision: str | None = None) -> "EvidenceBinding":
        reason = None
        superseding = None
        if source_revision is not None and self.source_revision is not None and self.source_revision != source_revision:
            reason, superseding = "source_revision_changed", source_revision
        elif artifact_identity is not None and self.artifact_identity is not None and self.artifact_identity != artifact_identity:
            reason, superseding = "artifact_identity_changed", artifact_identity
        elif validation_revision is not None and self.validation_revision is not None and self.validation_revision != validation_revision:
            reason, superseding = "validation_revision_changed", validation_revision
        return EvidenceBinding(**{**self.to_dict(), "stale_for_completion": reason is not None, "stale_reason": reason, "superseding_identity": superseding})

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "evidence_kind": self.evidence_kind, "source_revision": self.source_revision, "build_attempt_id": self.build_attempt_id, "artifact_identity": self.artifact_identity, "validation_revision": self.validation_revision, "runtime_attempt_id": self.runtime_attempt_id, "stale_for_completion": self.stale_for_completion, "stale_reason": self.stale_reason, "superseding_identity": self.superseding_identity}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceBinding":
        return cls(**{key: data.get(key) for key in ("evidence_id", "evidence_kind", "source_revision", "build_attempt_id", "artifact_identity", "validation_revision", "runtime_attempt_id", "stale_for_completion", "stale_reason", "superseding_identity")})


__all__ = [
    "ArtifactIdentity",
    "BuildAttemptIdentity",
    "EvidenceBinding",
    "RuntimeAttemptIdentity",
    "SourceRevision",
    "SOURCE_REVISION_ALGORITHM",
    "artifact_identity_from_result",
    "compute_source_revision",
    "validation_contract_revision",
]
