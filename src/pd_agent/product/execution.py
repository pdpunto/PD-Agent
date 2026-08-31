"""Single-capacity background execution service for the v0.9 product boundary."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any

from pd_agent.core import RunState, RunStatus
from pd_agent.pass_policy import evaluate_pass
from pd_agent.reporting import FinalReport
from pd_agent.runtime import RunController
from pd_agent.validation import CompletionGate

from .catalog import CatalogError, ProductCatalog
from .models import ExecutionRecord, TaskRecord
from .projects import ProjectService


class ExecutionServiceError(RuntimeError):
    """Product-level execution dispatch error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class ProductExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    LIMIT_REACHED = "LIMIT_REACHED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    """Product projection over an ExecutionRecord and runtime facts."""

    execution: ExecutionRecord
    status: ProductExecutionStatus
    reason: str | None = None
    runtime_state: str | None = None
    current_milestone: str | None = None
    current_activity: str | None = None
    terminal: bool = False
    latest_sequence: int | None = None

    @property
    def execution_id(self) -> str:
        return self.execution.execution_id

    @property
    def run_id(self) -> str:
        return self.execution.run_id

    @property
    def task_id(self) -> str:
        return self.execution.task_id


class ExecutionService:
    """Own one productive worker and dispatch it without creating a new lifecycle."""

    def __init__(
        self,
        catalog: ProductCatalog,
        controller: RunController,
        projects: ProjectService | None = None,
        product_runner: Any | None = None,
        delivery_service: Any | None = None,
        runner: Any | None = None,
    ) -> None:
        self.catalog = catalog
        self.controller = controller
        self.projects = projects or ProjectService(catalog)
        if product_runner is not None and runner is not None and product_runner is not runner:
            raise ValueError("product runner was provided more than once")
        self.product_runner = product_runner or runner
        self.delivery_service = delivery_service
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pd-agent-execution")
        self._active_execution_id: str | None = None
        self._futures: dict[str, Future[object]] = {}
        self._snapshots: dict[str, ExecutionSnapshot] = {}
        self._shutdown = False

    def start(self, task_id: str, *, project_id: str | None = None) -> ExecutionSnapshot:
        """Persist an execution and submit it, returning before runtime completion."""
        with self._lock:
            if self._shutdown:
                raise ExecutionServiceError("EXECUTION_SERVICE_SHUTDOWN", "service is shut down")
            if self._active_execution_id is not None:
                raise ExecutionServiceError("EXECUTION_CAPACITY_REACHED", "one productive execution is already active")
            task = self._get_task(task_id, project_id)
            project = self.projects.get_project(task.project_id)
            execution = ExecutionRecord(task_id=task.task_id, created_at=datetime.now(timezone.utc))
            self.catalog.add_execution(execution)
            snapshot = ExecutionSnapshot(execution, ProductExecutionStatus.RUNNING)
            self._snapshots[execution.execution_id] = snapshot
            self._active_execution_id = execution.execution_id
            try:
                future = self._executor.submit(self._run_worker, execution, task, project)
            except BaseException as exc:
                self._active_execution_id = None
                self._snapshots[execution.execution_id] = ExecutionSnapshot(
                    execution, ProductExecutionStatus.FAILED, "dispatch_failed"
                )
                raise ExecutionServiceError("EXECUTION_DISPATCH_FAILED", "worker submission failed") from exc
            self._futures[execution.execution_id] = future
            future.add_done_callback(lambda completed, execution_id=execution.execution_id: self._finished(execution_id, completed))
            return snapshot

    def get(self, execution_id: str) -> ExecutionSnapshot:
        with self._lock:
            snapshot = self._snapshots.get(execution_id)
            if snapshot is not None:
                return snapshot
            execution = self.catalog.get_execution(execution_id)
            if execution.terminal_recorded_at is None:
                return ExecutionSnapshot(execution, ProductExecutionStatus.INTERRUPTED, "UNKNOWN")
            return ExecutionSnapshot(
                execution,
                ProductExecutionStatus(execution.status),
                execution.status_reason,
                terminal=True,
            )

    def list(self) -> tuple[ExecutionSnapshot, ...]:
        with self._lock:
            execution_ids = tuple(self.catalog.snapshot()["executions"])
        return tuple(self.get(execution_id) for execution_id in sorted(execution_ids))

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            executor = self._executor
        # Waiting is explicit and safe: no fake cancellation is reported.
        executor.shutdown(wait=wait)

    close = shutdown

    def _get_task(self, task_id: str, project_id: str | None) -> TaskRecord:
        try:
            task = self.catalog.get_task(task_id)
            if project_id is not None and task.project_id != project_id:
                raise ExecutionServiceError("OWNERSHIP_INVALID", "task does not belong to project")
            self.projects.reopen_project(task.project_id)
            return task
        except CatalogError as exc:
            raise ExecutionServiceError(exc.code, str(exc)) from exc

    def _run_worker(self, execution: ExecutionRecord, task: TaskRecord, project: Any) -> object:
        if self.product_runner is not None:
            return self.product_runner.run(execution, project, task)
        return self.controller.run(Path(project.workspace_ref), task.request, run_id=execution.execution_id)

    def _finished(self, execution_id: str, future: Future[object]) -> None:
        with self._lock:
            try:
                execution = self.catalog.get_execution(execution_id)
                try:
                    result = future.result()
                except BaseException as exc:
                    status = ProductExecutionStatus.FAILED
                    reason = self._worker_failure_reason(exc)
                else:
                    if self.product_runner is not None:
                        status, reason = self._reconcile_product_result(result)
                    else:
                        run_state, report = result
                        status, reason = self._reconcile(run_state, report)
                terminal = ExecutionRecord(
                    execution_id=execution.execution_id,
                    task_id=execution.task_id,
                    run_id=execution.run_id,
                    created_at=execution.created_at,
                    terminal_recorded_at=datetime.now(timezone.utc),
                    status=status.value,
                    status_reason=reason,
                )
                self.catalog.update_execution(terminal)
                if status is ProductExecutionStatus.SUCCEEDED and self.delivery_service is not None:
                    try:
                        self.delivery_service.create(execution_id)
                    except Exception:
                        # Runtime success remains authoritative; DeliveryService
                        # exposes the unavailable delivery through its own errors.
                        pass
                self._snapshots[execution_id] = ExecutionSnapshot(terminal, status, reason, terminal=True)
            except BaseException:
                # A persistence failure must not strand the global capacity slot.
                if execution_id not in self._snapshots:
                    try:
                        execution = self.catalog.get_execution(execution_id)
                    except BaseException:
                        execution = None
                    if execution is not None:
                        self._snapshots[execution_id] = ExecutionSnapshot(
                            execution, ProductExecutionStatus.FAILED, "reconciliation_failed", terminal=True
                        )
            finally:
                self._futures.pop(execution_id, None)
                if self._active_execution_id == execution_id:
                    self._active_execution_id = None

    def _reconcile(self, state: RunState, report: FinalReport) -> tuple[ProductExecutionStatus, str | None]:
        if state.state is RunStatus.COMPLETED:
            if self._authoritative_success(state, report):
                return ProductExecutionStatus.SUCCEEDED, None
            return ProductExecutionStatus.FAILED, "completion_not_authoritative"
        if state.state is RunStatus.BLOCKED:
            return ProductExecutionStatus.BLOCKED, state.termination_reason
        if state.state is RunStatus.LIMIT_REACHED:
            return ProductExecutionStatus.LIMIT_REACHED, state.termination_reason
        if state.state is RunStatus.ABORTED:
            return ProductExecutionStatus.INTERRUPTED, state.termination_reason
        return ProductExecutionStatus.FAILED, state.termination_reason

    def _reconcile_product_result(self, result: Any) -> tuple[ProductExecutionStatus, str | None]:
        """Reconcile a productive runner only through persisted runtime facts."""
        if not hasattr(result, "run_id"):
            return ProductExecutionStatus.FAILED, "invalid_runner_result"
        if result.run_id is None:
            return ProductExecutionStatus.FAILED, "invalid_runner_result"
        storage = getattr(self.controller, "storage", None)
        if storage is None:
            return ProductExecutionStatus.FAILED, "runtime_evidence_unavailable"
        try:
            state = storage.read_run_state(result.run_id)
            report = storage.read_final_report(result.run_id)
        except Exception:
            return ProductExecutionStatus.FAILED, "runtime_evidence_unavailable"
        return self._reconcile(state, report)

    @staticmethod
    def _worker_failure_reason(error: BaseException) -> str:
        """Classify early failures without exposing exception internals."""
        from .fabric import ProductFabricTaskContractError

        if isinstance(error, ProductFabricTaskContractError):
            return "task_contract_resolution_failed"
        return "worker_exception"

    def _authoritative_success(self, state: RunState, report: FinalReport) -> bool:
        storage = getattr(self.controller, "storage", None)
        if storage is not None:
            if not evaluate_pass(storage, state.run_id).passed:
                return False
            if state.task_contract is not None:
                completion = CompletionGate().evaluate(
                    state.task_contract,
                    state.progress_ledger,
                    state,
                )
                return completion.complete
            return True
        return (
            report.final_state is RunStatus.COMPLETED
            and report.completion_status in {"PASS", "SUCCEEDED"}
        )

    def _status_from_runtime(self, run_id: str) -> ProductExecutionStatus:
        storage = getattr(self.controller, "storage", None)
        if storage is None:
            return ProductExecutionStatus.INTERRUPTED
        try:
            state = storage.read_run_state(run_id)
        except Exception:
            return ProductExecutionStatus.INTERRUPTED
        if state.state is RunStatus.COMPLETED:
            try:
                report = storage.read_final_report(run_id)
            except Exception:
                return ProductExecutionStatus.FAILED
            return ProductExecutionStatus.SUCCEEDED if self._authoritative_success(state, report) else ProductExecutionStatus.FAILED
        if state.state is RunStatus.BLOCKED:
            return ProductExecutionStatus.BLOCKED
        if state.state is RunStatus.LIMIT_REACHED:
            return ProductExecutionStatus.LIMIT_REACHED
        if state.state is RunStatus.ABORTED:
            return ProductExecutionStatus.INTERRUPTED
        return ProductExecutionStatus.INTERRUPTED


__all__ = ["ExecutionService", "ExecutionServiceError", "ExecutionSnapshot", "ProductExecutionStatus"]
