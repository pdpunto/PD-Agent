"""Thin HTTP adapters over the v0.9 product services."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse

from ..app import WebServices
from ..dto import (
    DeliveryDTO,
    ExecutionDTO,
    HumanEvidenceDTO,
    ProjectCreateRequest,
    ProjectDTO,
    RevealDTO,
    TaskCreateRequest,
    TaskDTO,
    TechnicalEvidenceDTO,
)


def register_routes(app: FastAPI) -> None:
    router = APIRouter(prefix="/api/v1")

    def services(request: Request) -> WebServices:
        return request.app.state.services

    @router.get("/projects", response_model=tuple[ProjectDTO, ...])
    def list_projects(deps: WebServices = Depends(services)) -> tuple[ProjectDTO, ...]:
        return tuple(_project(item) for item in deps.project.list_projects())

    @router.post("/projects", response_model=ProjectDTO, status_code=201)
    def create_project(payload: ProjectCreateRequest, deps: WebServices = Depends(services)) -> ProjectDTO:
        return _project(deps.project.register_project(payload.name, payload.workspace))

    @router.get("/projects/{project_id}", response_model=ProjectDTO)
    def get_project(project_id: UUID, deps: WebServices = Depends(services)) -> ProjectDTO:
        return _project(deps.project.get_project(str(project_id)))

    @router.post("/projects/{project_id}/tasks", response_model=TaskDTO, status_code=201)
    def create_task(project_id: UUID, payload: TaskCreateRequest, deps: WebServices = Depends(services)) -> TaskDTO:
        return _task(deps.project.create_task(str(project_id), payload.request))

    @router.post("/tasks/{task_id}/executions", response_model=ExecutionDTO, status_code=202)
    def start_execution(task_id: UUID, deps: WebServices = Depends(services)) -> ExecutionDTO:
        return _execution(deps.execution.start(str(task_id)))

    @router.get("/executions/{execution_id}", response_model=ExecutionDTO)
    def get_execution(execution_id: UUID, deps: WebServices = Depends(services)) -> ExecutionDTO:
        return _execution(deps.execution.get(str(execution_id)))

    @router.get("/executions/{execution_id}/evidence/human", response_model=HumanEvidenceDTO)
    def human_evidence(execution_id: UUID, deps: WebServices = Depends(services)) -> HumanEvidenceDTO:
        return HumanEvidenceDTO.model_validate(deps.evidence.human_evidence(str(execution_id)).to_dict())

    @router.get("/executions/{execution_id}/evidence/technical", response_model=TechnicalEvidenceDTO)
    def technical_evidence(execution_id: UUID, deps: WebServices = Depends(services)) -> TechnicalEvidenceDTO:
        return TechnicalEvidenceDTO.model_validate(deps.evidence.technical_evidence(str(execution_id)).to_dict())

    @router.get("/projects/{project_id}/history")
    def project_history(project_id: UUID, deps: WebServices = Depends(services)) -> dict[str, Any]:
        history = deps.project.project_history(str(project_id))
        return {
            "project_id": project_id,
            "tasks": [_task(item).model_dump(mode="json") for item in history["tasks"]],
            "executions": [_execution_metadata(item).model_dump(mode="json") for item in history["executions"]],
            "deliveries": [_delivery(item).model_dump(mode="json") for item in history["deliveries"]],
        }

    @router.get("/deliveries/{delivery_id}", response_model=DeliveryDTO)
    def get_delivery(delivery_id: UUID, deps: WebServices = Depends(services)) -> DeliveryDTO:
        return _delivery(deps.delivery.get(str(delivery_id)))

    @router.get("/deliveries/{delivery_id}/artifact", response_class=FileResponse)
    def download_artifact(delivery_id: UUID, deps: WebServices = Depends(services)) -> FileResponse:
        artifact = deps.delivery.resolve(str(delivery_id))
        return FileResponse(artifact.path, media_type="application/java-archive", filename=artifact.filename)

    @router.post("/deliveries/{delivery_id}/reveal", response_model=RevealDTO)
    def reveal_delivery(delivery_id: UUID, deps: WebServices = Depends(services)) -> RevealDTO:
        action = deps.delivery.execute_reveal(str(delivery_id))
        return RevealDTO(delivery_id=delivery_id, revealed=True, filename=action.target.name)

    app.include_router(router)


def _project(item: Any) -> ProjectDTO:
    return ProjectDTO.model_validate({"project_id": item.project_id, "name": item.name, "created_at": item.created_at, "updated_at": item.updated_at, "task_ids": item.task_ids})


def _task(item: Any) -> TaskDTO:
    return TaskDTO.model_validate(item.to_dict())


def _execution(item: Any) -> ExecutionDTO:
    return ExecutionDTO(execution_id=item.execution.execution_id, run_id=item.execution.run_id, task_id=item.execution.task_id, status=item.status.value, reason=item.reason, terminal=item.terminal, current_milestone=item.current_milestone, current_activity=item.current_activity, latest_sequence=item.latest_sequence)


def _execution_metadata(item: Any) -> ExecutionDTO:
    return ExecutionDTO(execution_id=item.execution_id, run_id=item.run_id, task_id=item.task_id, status=item.status, reason=item.status_reason, terminal=item.status != "RUNNING")


def _delivery(item: Any) -> DeliveryDTO:
    return DeliveryDTO.model_validate({key: value for key, value in item.to_dict().items() if key != "artifact_ref"})


__all__ = ["register_routes"]
