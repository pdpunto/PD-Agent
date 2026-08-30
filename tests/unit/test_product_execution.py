from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Event, Thread
from uuid import uuid4

import pytest

from pd_agent.core import RunState, RunStatus
from pd_agent.product import (
    ExecutionRecord,
    ExecutionService,
    ExecutionServiceError,
    ProductCatalog,
    ProductExecutionStatus,
    ProjectService,
)
from pd_agent.reporting import FinalReport


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


class ControlledController:
    def __init__(self, *, status: RunStatus = RunStatus.COMPLETED, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.started = Event()
        self.release = Event()
        self.calls: list[tuple[Path, str, str]] = []

    def run(self, project_root: Path, task: str, *, run_id: str):
        self.calls.append((project_root, task, run_id))
        self.started.set()
        self.release.wait(timeout=5)
        if self.error is not None:
            raise self.error
        state = RunState(run_id=run_id, project_root=project_root, task=task, state=self.status)
        report = FinalReport(
            run_id=run_id,
            final_state=self.status,
            summary="controlled result",
            completion_status="PASS" if self.status is RunStatus.COMPLETED else None,
        )
        return state, report


def _service(tmp_path: Path, controller: ControlledController) -> tuple[ExecutionService, ProductCatalog, str, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    catalog = ProductCatalog(tmp_path / "data")
    projects = ProjectService(catalog)
    project = projects.register_project("Demo", workspace)
    task = projects.create_task(project.project_id, "do work")
    return ExecutionService(catalog, controller, projects), catalog, project.project_id, task.task_id


def test_start_persists_before_nonblocking_dispatch_and_maps_identity(tmp_path: Path) -> None:
    controller = ControlledController()
    service, catalog, _project_id, task_id = _service(tmp_path, controller)
    try:
        snapshot = service.start(task_id)
        assert controller.started.wait(timeout=2)
        assert snapshot.status is ProductExecutionStatus.RUNNING
        assert snapshot.execution_id == snapshot.run_id
        assert controller.calls[0][2] == snapshot.execution_id
        assert catalog.get_execution(snapshot.execution_id).run_id == snapshot.execution_id
        assert service.get(snapshot.execution_id).status is ProductExecutionStatus.RUNNING
    finally:
        controller.release.set()
        service.shutdown()


def test_one_capacity_no_queue_and_release_after_success(tmp_path: Path) -> None:
    controller = ControlledController()
    service, _catalog, _project_id, task_id = _service(tmp_path, controller)
    try:
        first = service.start(task_id)
        assert controller.started.wait(timeout=2)
        with pytest.raises(ExecutionServiceError, match="EXECUTION_CAPACITY_REACHED") as error:
            service.start(task_id)
        assert error.value.code == "EXECUTION_CAPACITY_REACHED"
        assert len(controller.calls) == 1
        controller.release.set()
        for _ in range(100):
            if service.get(first.execution_id).status is ProductExecutionStatus.SUCCEEDED:
                break
            Event().wait(0.01)
        assert service.get(first.execution_id).status is ProductExecutionStatus.SUCCEEDED
        controller.started.clear()
        controller.release.clear()
        second = service.start(task_id)
        assert second.execution_id != first.execution_id
    finally:
        controller.release.set()
        service.shutdown()


def test_near_simultaneous_starts_obtain_only_one_capacity_slot(tmp_path: Path) -> None:
    controller = ControlledController()
    service, _catalog, _project_id, task_id = _service(tmp_path, controller)
    barrier = Barrier(2)
    results: list[object] = []

    def start() -> None:
        barrier.wait()
        try:
            results.append(service.start(task_id))
        except Exception as exc:
            results.append(exc)

    threads = [Thread(target=start) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        assert sum(isinstance(item, ExecutionServiceError) for item in results) == 1
        assert sum(not isinstance(item, Exception) for item in results) == 1
    finally:
        controller.release.set()
        service.shutdown()


def test_worker_exception_releases_capacity_and_is_failed(tmp_path: Path) -> None:
    controller = ControlledController(error=RuntimeError("worker failed"))
    service, _catalog, _project_id, task_id = _service(tmp_path, controller)
    try:
        snapshot = service.start(task_id)
        controller.started.wait(timeout=2)
        controller.release.set()
        for _ in range(100):
            if service.get(snapshot.execution_id).status is ProductExecutionStatus.FAILED:
                break
            Event().wait(0.01)
        result = service.get(snapshot.execution_id)
        assert result.status is ProductExecutionStatus.FAILED
        assert result.reason == "worker_exception"
        assert service._active_execution_id is None
    finally:
        service.shutdown()


@pytest.mark.parametrize(
    ("runtime_status", "expected"),
    [
        (RunStatus.FAILED, ProductExecutionStatus.FAILED),
        (RunStatus.BLOCKED, ProductExecutionStatus.BLOCKED),
        (RunStatus.LIMIT_REACHED, ProductExecutionStatus.LIMIT_REACHED),
        (RunStatus.ABORTED, ProductExecutionStatus.INTERRUPTED),
    ],
)
def test_terminal_runtime_statuses_project_truthfully(
    tmp_path: Path, runtime_status: RunStatus, expected: ProductExecutionStatus
) -> None:
    controller = ControlledController(status=runtime_status)
    service, _catalog, _project_id, task_id = _service(tmp_path, controller)
    try:
        snapshot = service.start(task_id)
        controller.started.wait(timeout=2)
        controller.release.set()
        for _ in range(100):
            if service.get(snapshot.execution_id).status is expected:
                break
            Event().wait(0.01)
        assert service.get(snapshot.execution_id).status is expected
    finally:
        service.shutdown()


def test_persisted_nonterminal_execution_is_interrupted_on_new_service(tmp_path: Path) -> None:
    controller = ControlledController()
    service, catalog, project_id, task_id = _service(tmp_path, controller)
    service.shutdown()
    execution_id = uuid4()
    catalog.add_execution(ExecutionRecord(execution_id=execution_id, task_id=task_id, created_at=NOW))
    restarted = ExecutionService(catalog, controller)
    try:
        snapshot = restarted.get(str(execution_id))
        assert snapshot.status is ProductExecutionStatus.INTERRUPTED
        assert snapshot.reason == "UNKNOWN"
        assert snapshot.execution.run_id == str(execution_id)
        assert catalog.get_task(task_id).project_id == project_id
    finally:
        restarted.shutdown()


def test_ownership_and_shutdown_contract(tmp_path: Path) -> None:
    controller = ControlledController()
    service, _catalog, project_id, task_id = _service(tmp_path, controller)
    try:
        with pytest.raises(ExecutionServiceError, match="OWNERSHIP_INVALID"):
            service.start(task_id, project_id=str(uuid4()))
        snapshot = service.start(task_id)
        assert controller.started.wait(timeout=2)
        done = Event()

        def shutdown() -> None:
            service.shutdown()
            done.set()

        thread = Thread(target=shutdown)
        thread.start()
        assert not done.wait(timeout=0.05)
        controller.release.set()
        assert done.wait(timeout=2)
        thread.join()
        assert service.get(snapshot.execution_id).status is ProductExecutionStatus.SUCCEEDED
        with pytest.raises(ExecutionServiceError, match="EXECUTION_SERVICE_SHUTDOWN"):
            service.start(task_id)
    finally:
        controller.release.set()
        service.shutdown()
