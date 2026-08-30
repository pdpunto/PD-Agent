"""Project continuity service over ProductCatalog."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .catalog import CatalogError, ProductCatalog
from .models import DeliveryRecord, ExecutionRecord, ProjectRecord, TaskRecord


class WorkspaceError(CatalogError):
    """A registered workspace cannot be safely reopened."""


class ProjectService:
    """Register authorized workspaces and coordinate product metadata."""

    def __init__(self, catalog: ProductCatalog) -> None:
        self.catalog = catalog

    def register_project(self, name: str, workspace: Path | str) -> ProjectRecord:
        root = self._canonical_workspace(workspace)
        now = datetime.now(timezone.utc)
        return self.catalog.add_project(ProjectRecord(name=name, workspace_ref=str(root), created_at=now, updated_at=now))

    create_project = register_project
    import_project = register_project

    def get_project(self, project_id: str) -> ProjectRecord:
        return self.catalog.get_project(project_id)

    def list_projects(self) -> tuple[ProjectRecord, ...]:
        return self.catalog.list_projects()

    def reopen_project(self, project_id: str) -> ProjectRecord:
        project = self.catalog.get_project(project_id)
        current = self._canonical_workspace(project.workspace_ref)
        if str(current) != project.workspace_ref:
            raise WorkspaceError("WORKSPACE_CHANGED", "registered workspace resolves differently")
        return project

    def create_task(self, project_id: str, request: str) -> TaskRecord:
        project = self.catalog.get_project(project_id)
        task = TaskRecord(project_id=project.project_id, request=request, created_at=datetime.now(timezone.utc))
        return self.catalog.add_task(task)

    def attach_execution(self, execution: ExecutionRecord) -> ExecutionRecord:
        return self.catalog.add_execution(execution)

    def attach_delivery(self, delivery: DeliveryRecord) -> DeliveryRecord:
        return self.catalog.add_delivery(delivery)

    def project_history(self, project_id: str) -> dict[str, tuple[object, ...]]:
        return self.catalog.project_history(project_id)

    def _canonical_workspace(self, workspace: Path | str) -> Path:
        candidate = Path(workspace).expanduser()
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise WorkspaceError("WORKSPACE_UNAVAILABLE", "workspace does not exist") from exc
        if not resolved.is_dir():
            raise WorkspaceError("WORKSPACE_UNAVAILABLE", "workspace is not a directory")
        return resolved


__all__ = ["ProjectService", "WorkspaceError"]
