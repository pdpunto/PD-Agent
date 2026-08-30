"""Serializable product records, separate from runtime and evidence state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping
from uuid import UUID, uuid4


def _new_id() -> str:
    return str(uuid4())


def _uuid4_text(value: UUID | str, field_name: str) -> str:
    try:
        parsed = value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a UUIDv4") from exc
    if parsed.version != 4:
        raise ValueError(f"{field_name} must be a UUIDv4")
    return str(parsed)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _timestamp(value: datetime | str, field_name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _id_tuple(values: object, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of UUIDv4 values")
    return tuple(_uuid4_text(value, field_name) for value in values)


def _required(data: Mapping[str, Any], field_name: str) -> Any:
    if field_name not in data:
        raise ValueError(f"missing required field: {field_name}")
    return data[field_name]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    """Persistent product identity for an authorized workspace context."""

    project_id: str = ""
    name: str = ""
    workspace_ref: str = ""
    created_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    updated_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    task_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _uuid4_text(self.project_id or _new_id(), "project_id"))
        object.__setattr__(self, "name", _text(self.name, "name"))
        object.__setattr__(self, "workspace_ref", _text(self.workspace_ref, "workspace_ref"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _timestamp(self.updated_at, "updated_at"))
        object.__setattr__(self, "task_ids", _id_tuple(self.task_ids, "task_ids"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "workspace_ref": self.workspace_ref,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "task_ids": list(self.task_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectRecord":
        return cls(
            project_id=_required(data, "project_id"),
            name=_required(data, "name"),
            workspace_ref=_required(data, "workspace_ref"),
            created_at=_required(data, "created_at"),
            updated_at=_required(data, "updated_at"),
            task_ids=data.get("task_ids", []),
        )

    def canonical_json(self) -> str:
        return _json(self.to_dict())


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """A concrete natural-language request belonging to a Project."""

    task_id: str = ""
    project_id: str = ""
    request: str = ""
    created_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    execution_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _uuid4_text(self.task_id or _new_id(), "task_id"))
        object.__setattr__(self, "project_id", _uuid4_text(self.project_id, "project_id"))
        object.__setattr__(self, "request", _text(self.request, "request"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "execution_ids", _id_tuple(self.execution_ids, "execution_ids"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "request": self.request,
            "created_at": self.created_at.isoformat(),
            "execution_ids": list(self.execution_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskRecord":
        return cls(
            task_id=_required(data, "task_id"),
            project_id=_required(data, "project_id"),
            request=_required(data, "request"),
            created_at=_required(data, "created_at"),
            execution_ids=data.get("execution_ids", []),
        )

    def canonical_json(self) -> str:
        return _json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """Product metadata for one productive execution."""

    execution_id: str = ""
    task_id: str = ""
    run_id: str = ""
    created_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    terminal_recorded_at: datetime | None = None

    def __post_init__(self) -> None:
        execution_id = _uuid4_text(self.execution_id or _new_id(), "execution_id")
        object.__setattr__(self, "execution_id", execution_id)
        object.__setattr__(self, "task_id", _uuid4_text(self.task_id, "task_id"))
        object.__setattr__(self, "run_id", _uuid4_text(self.run_id or execution_id, "run_id"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        if self.terminal_recorded_at is not None:
            object.__setattr__(self, "terminal_recorded_at", _timestamp(self.terminal_recorded_at, "terminal_recorded_at"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "terminal_recorded_at": self.terminal_recorded_at.isoformat() if self.terminal_recorded_at else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionRecord":
        return cls(
            execution_id=_required(data, "execution_id"),
            task_id=_required(data, "task_id"),
            run_id=_required(data, "run_id"),
            created_at=_required(data, "created_at"),
            terminal_recorded_at=data.get("terminal_recorded_at"),
        )

    def canonical_json(self) -> str:
        return _json(self.to_dict())


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    """Trusted metadata for delivering a validated artifact."""

    delivery_id: str = ""
    project_id: str = ""
    task_id: str = ""
    execution_id: str = ""
    artifact_sha256: str = ""
    artifact_ref: str = ""
    created_at: datetime = datetime.min.replace(tzinfo=timezone.utc)

    def __post_init__(self) -> None:
        object.__setattr__(self, "delivery_id", _uuid4_text(self.delivery_id or _new_id(), "delivery_id"))
        object.__setattr__(self, "project_id", _uuid4_text(self.project_id, "project_id"))
        object.__setattr__(self, "task_id", _uuid4_text(self.task_id, "task_id"))
        object.__setattr__(self, "execution_id", _uuid4_text(self.execution_id, "execution_id"))
        artifact_sha256 = _text(self.artifact_sha256, "artifact_sha256").lower()
        if _SHA256.fullmatch(artifact_sha256) is None:
            raise ValueError("artifact_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "artifact_sha256", artifact_sha256)
        object.__setattr__(self, "artifact_ref", _text(self.artifact_ref, "artifact_ref"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "artifact_sha256": self.artifact_sha256,
            "artifact_ref": self.artifact_ref,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeliveryRecord":
        return cls(
            delivery_id=_required(data, "delivery_id"),
            project_id=_required(data, "project_id"),
            task_id=_required(data, "task_id"),
            execution_id=_required(data, "execution_id"),
            artifact_sha256=_required(data, "artifact_sha256"),
            artifact_ref=_required(data, "artifact_ref"),
            created_at=_required(data, "created_at"),
        )

    def canonical_json(self) -> str:
        return _json(self.to_dict())


__all__ = ["DeliveryRecord", "ExecutionRecord", "ProjectRecord", "TaskRecord"]
