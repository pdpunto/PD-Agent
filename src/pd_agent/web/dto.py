"""Closed, path-safe DTOs for the v0.9 product HTTP boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreateRequest(_DTO):
    name: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=4096)


class TaskCreateRequest(_DTO):
    request: str = Field(min_length=1, max_length=32_000)


class ProjectDTO(_DTO):
    project_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    task_ids: tuple[UUID, ...]


class TaskDTO(_DTO):
    task_id: UUID
    project_id: UUID
    request: str
    created_at: datetime
    execution_ids: tuple[UUID, ...]


class ExecutionDTO(_DTO):
    execution_id: UUID
    run_id: UUID
    task_id: UUID
    status: str
    reason: str | None = None
    terminal: bool
    current_milestone: str | None = None
    current_activity: str | None = None
    latest_sequence: int | None = None


class HumanEvidenceDTO(_DTO):
    execution_id: UUID
    status: str
    current_milestone: str | None = None
    current_activity: str | None = None
    changes: tuple[str, ...] = ()
    build_summary: str | None = None
    repair_summary: str | None = None
    runtime_validation_summary: str | None = None
    completion_summary: str | None = None
    artifact_summary: str | None = None


class TechnicalEvidenceDTO(_DTO):
    execution_id: UUID
    run_id: UUID
    status: str
    runtime_state: str | None = None
    started_at: str | None = None
    changed_files: tuple[str, ...] = ()
    build_attempts: tuple[dict[str, Any], ...] = ()
    validation_summaries: tuple[dict[str, Any], ...] = ()
    runtime_observations: tuple[dict[str, Any], ...] = ()
    failure_classification: str | None = None
    artifact_sha256: str | None = None
    evidence_refs: tuple[str, ...] = ()
    failure_diagnostics: dict[str, Any] | None = None


class DeliveryDTO(_DTO):
    delivery_id: UUID
    project_id: UUID
    task_id: UUID
    execution_id: UUID
    artifact_sha256: str
    created_at: datetime


class RevealDTO(_DTO):
    delivery_id: UUID
    revealed: bool
    filename: str


class ErrorDetailDTO(_DTO):
    code: str
    message: str
    request_id: str


class ErrorEnvelopeDTO(_DTO):
    error: ErrorDetailDTO
