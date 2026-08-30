"""File-backed product metadata catalog for v0.9."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any, Mapping

from .models import DeliveryRecord, ExecutionRecord, ProjectRecord, TaskRecord


CATALOG_SCHEMA_VERSION = 1
CATALOG_FILE_NAME = "catalog-v1.json"


class CatalogError(ValueError):
    """Safe product catalog error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CatalogError("CATALOG_CORRUPT", f"{field_name} must be an object")
    return value


def _record_map(value: object, field_name: str) -> dict[str, dict[str, Any]]:
    mapping = _mapping(value, field_name)
    records: dict[str, dict[str, Any]] = {}
    for key, payload in mapping.items():
        if not isinstance(key, str) or not isinstance(payload, Mapping):
            raise CatalogError("CATALOG_CORRUPT", f"{field_name} contains an invalid record")
        records[key] = dict(payload)
    return records


class ProductCatalog:
    """Versioned metadata/index authority, separate from RunStorage."""

    def __init__(self, data_root: Path | str) -> None:
        self.data_root = Path(data_root)
        self.product_root = self.data_root / "product"
        self.path = self.product_root / CATALOG_FILE_NAME
        self._lock = RLock()
        with self._lock:
            self._data = self._read_or_bootstrap_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data, sort_keys=True))

    def reload(self) -> None:
        with self._lock:
            self._data = self._read_or_bootstrap_locked()

    def get_project(self, project_id: str) -> ProjectRecord:
        with self._lock:
            payload = self._data["projects"].get(project_id)
            if payload is None:
                raise CatalogError("PROJECT_NOT_FOUND", f"unknown project: {project_id}")
            return ProjectRecord.from_dict(payload)

    def list_projects(self) -> tuple[ProjectRecord, ...]:
        with self._lock:
            return tuple(ProjectRecord.from_dict(self._data["projects"][key]) for key in sorted(self._data["projects"]))

    def get_task(self, task_id: str) -> TaskRecord:
        with self._lock:
            payload = self._data["tasks"].get(task_id)
            if payload is None:
                raise CatalogError("TASK_NOT_FOUND", f"unknown task: {task_id}")
            return TaskRecord.from_dict(payload)

    def get_execution(self, execution_id: str) -> ExecutionRecord:
        with self._lock:
            payload = self._data["executions"].get(execution_id)
            if payload is None:
                raise CatalogError("EXECUTION_NOT_FOUND", f"unknown execution: {execution_id}")
            return ExecutionRecord.from_dict(payload)

    def get_delivery(self, delivery_id: str) -> DeliveryRecord:
        with self._lock:
            payload = self._data["deliveries"].get(delivery_id)
            if payload is None:
                raise CatalogError("DELIVERY_NOT_FOUND", f"unknown delivery: {delivery_id}")
            return DeliveryRecord.from_dict(payload)

    def add_project(self, project: ProjectRecord) -> ProjectRecord:
        with self._lock:
            if project.project_id in self._data["projects"]:
                raise CatalogError("PROJECT_EXISTS", f"project already exists: {project.project_id}")
            candidate = self._copy_data()
            candidate["projects"][project.project_id] = project.to_dict()
            self._commit_locked(candidate)
            return project

    def add_task(self, task: TaskRecord) -> TaskRecord:
        with self._lock:
            if task.project_id not in self._data["projects"]:
                raise CatalogError("OWNERSHIP_INVALID", "task project does not exist")
            if task.task_id in self._data["tasks"]:
                raise CatalogError("TASK_EXISTS", f"task already exists: {task.task_id}")
            candidate = self._copy_data()
            candidate["tasks"][task.task_id] = task.to_dict()
            project = ProjectRecord.from_dict(candidate["projects"][task.project_id])
            candidate["projects"][task.project_id] = replace(project, task_ids=(*project.task_ids, task.task_id)).to_dict()
            self._commit_locked(candidate)
            return task

    def add_execution(self, execution: ExecutionRecord) -> ExecutionRecord:
        with self._lock:
            task_payload = self._data["tasks"].get(execution.task_id)
            if task_payload is None:
                raise CatalogError("OWNERSHIP_INVALID", "execution task does not exist")
            if execution.execution_id in self._data["executions"]:
                raise CatalogError("EXECUTION_EXISTS", f"execution already exists: {execution.execution_id}")
            candidate = self._copy_data()
            candidate["executions"][execution.execution_id] = execution.to_dict()
            task = TaskRecord.from_dict(task_payload)
            candidate["tasks"][execution.task_id] = replace(task, execution_ids=(*task.execution_ids, execution.execution_id)).to_dict()
            self._commit_locked(candidate)
            return execution

    def add_delivery(self, delivery: DeliveryRecord) -> DeliveryRecord:
        with self._lock:
            task_payload = self._data["tasks"].get(delivery.task_id)
            execution_payload = self._data["executions"].get(delivery.execution_id)
            if delivery.project_id not in self._data["projects"] or task_payload is None or execution_payload is None:
                raise CatalogError("OWNERSHIP_INVALID", "delivery references an unknown owner")
            task = TaskRecord.from_dict(task_payload)
            execution = ExecutionRecord.from_dict(execution_payload)
            if task.project_id != delivery.project_id or execution.task_id != delivery.task_id:
                raise CatalogError("OWNERSHIP_INVALID", "delivery ownership chain is inconsistent")
            if delivery.delivery_id in self._data["deliveries"]:
                raise CatalogError("DELIVERY_EXISTS", f"delivery already exists: {delivery.delivery_id}")
            candidate = self._copy_data()
            candidate["deliveries"][delivery.delivery_id] = delivery.to_dict()
            self._commit_locked(candidate)
            return delivery

    def project_history(self, project_id: str) -> dict[str, tuple[Any, ...]]:
        project = self.get_project(project_id)
        with self._lock:
            tasks = tuple(TaskRecord.from_dict(self._data["tasks"][task_id]) for task_id in project.task_ids)
            executions = tuple(
                ExecutionRecord.from_dict(payload)
                for payload in self._data["executions"].values()
                if any(execution_id == payload["execution_id"] for task in tasks for execution_id in task.execution_ids)
            )
            deliveries = tuple(
                DeliveryRecord.from_dict(payload)
                for payload in self._data["deliveries"].values()
                if payload["project_id"] == project_id
            )
            return {"tasks": tasks, "executions": executions, "deliveries": deliveries}

    def _read_or_bootstrap_locked(self) -> dict[str, Any]:
        if not self.path.exists():
            data = self._empty_data()
            self._write_locked(data)
            return data
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CatalogError("CATALOG_CORRUPT", "catalog is not valid UTF-8 JSON") from exc
        return self._validate(data)

    def _validate(self, value: object) -> dict[str, Any]:
        data = _mapping(value, "catalog")
        if data.get("schema_version") != CATALOG_SCHEMA_VERSION:
            raise CatalogError("CATALOG_VERSION_UNSUPPORTED", "unsupported catalog schema version")
        expected = {"schema_version", "projects", "tasks", "executions", "deliveries"}
        if set(data) != expected:
            raise CatalogError("CATALOG_CORRUPT", "catalog schema keys are invalid")
        normalized = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "projects": _record_map(data["projects"], "projects"),
            "tasks": _record_map(data["tasks"], "tasks"),
            "executions": _record_map(data["executions"], "executions"),
            "deliveries": _record_map(data["deliveries"], "deliveries"),
        }
        try:
            projects = {key: ProjectRecord.from_dict(payload) for key, payload in normalized["projects"].items()}
            tasks = {key: TaskRecord.from_dict(payload) for key, payload in normalized["tasks"].items()}
            executions = {key: ExecutionRecord.from_dict(payload) for key, payload in normalized["executions"].items()}
            deliveries = {key: DeliveryRecord.from_dict(payload) for key, payload in normalized["deliveries"].items()}
        except (TypeError, ValueError, KeyError) as exc:
            raise CatalogError("CATALOG_CORRUPT", "catalog contains an invalid record") from exc
        if any(key != record.project_id for key, record in projects.items()) or any(key != record.task_id for key, record in tasks.items()) or any(key != record.execution_id for key, record in executions.items()) or any(key != record.delivery_id for key, record in deliveries.items()):
            raise CatalogError("CATALOG_CORRUPT", "record key does not match record identity")
        for task in tasks.values():
            if task.project_id not in projects or task.task_id not in projects[task.project_id].task_ids:
                raise CatalogError("CATALOG_CORRUPT", "task ownership index is inconsistent")
        for execution in executions.values():
            if execution.task_id not in tasks or execution.execution_id not in tasks[execution.task_id].execution_ids:
                raise CatalogError("CATALOG_CORRUPT", "execution ownership index is inconsistent")
        for delivery in deliveries.values():
            task = tasks.get(delivery.task_id)
            execution = executions.get(delivery.execution_id)
            if task is None or execution is None or task.project_id != delivery.project_id or execution.task_id != delivery.task_id:
                raise CatalogError("CATALOG_CORRUPT", "delivery ownership chain is inconsistent")
        return normalized

    def _empty_data(self) -> dict[str, Any]:
        return {"schema_version": CATALOG_SCHEMA_VERSION, "projects": {}, "tasks": {}, "executions": {}, "deliveries": {}}

    def _copy_data(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._data))

    def _commit_locked(self, data: Mapping[str, Any]) -> None:
        validated = self._validate(data)
        self._write_locked(validated)
        self._data = validated

    def _write_locked(self, data: Mapping[str, Any]) -> None:
        self.product_root.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.product_root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise CatalogError("CATALOG_WRITE_FAILED", "catalog write did not complete") from exc


__all__ = ["CATALOG_FILE_NAME", "CATALOG_SCHEMA_VERSION", "CatalogError", "ProductCatalog"]
