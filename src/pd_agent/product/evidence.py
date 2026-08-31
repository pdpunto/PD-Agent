"""Read-only product projections over authoritative runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from pd_agent.core import RunState, RunStatus, ValidationResult, ValidationStage
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage

from .execution import ExecutionService, ExecutionSnapshot, ProductExecutionStatus
from .models import ExecutionRecord


MILESTONES = (
    "Entendiendo",
    "Investigando",
    "Editando",
    "Compilando",
    "Probando",
    "Verificando",
    "Reparando",
    "Entregando",
)


@dataclass(frozen=True, slots=True)
class HumanEvidenceDTO:
    """Small allowlisted evidence view for normal product details."""

    execution_id: str
    status: str
    current_milestone: str | None = None
    current_activity: str | None = None
    changes: tuple[str, ...] = ()
    build_summary: str | None = None
    repair_summary: str | None = None
    runtime_validation_summary: str | None = None
    completion_summary: str | None = None
    artifact_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "current_milestone": self.current_milestone,
            "current_activity": self.current_activity,
            "changes": list(self.changes),
            "build_summary": self.build_summary,
            "repair_summary": self.repair_summary,
            "runtime_validation_summary": self.runtime_validation_summary,
            "completion_summary": self.completion_summary,
            "artifact_summary": self.artifact_summary,
        }


@dataclass(frozen=True, slots=True)
class TechnicalEvidenceDTO:
    """Explicit technical allowlist; never a raw event/evidence dump."""

    execution_id: str
    run_id: str
    status: str
    runtime_state: str | None = None
    started_at: str | None = None
    changed_files: tuple[str, ...] = ()
    build_attempts: tuple[Mapping[str, Any], ...] = ()
    validation_summaries: tuple[Mapping[str, Any], ...] = ()
    runtime_observations: tuple[Mapping[str, Any], ...] = ()
    failure_classification: str | None = None
    artifact_sha256: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "status": self.status,
            "runtime_state": self.runtime_state,
            "started_at": self.started_at,
            "changed_files": list(self.changed_files),
            "build_attempts": [dict(item) for item in self.build_attempts],
            "validation_summaries": [dict(item) for item in self.validation_summaries],
            "runtime_observations": [dict(item) for item in self.runtime_observations],
            "failure_classification": self.failure_classification,
            "artifact_sha256": self.artifact_sha256,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class ProductExecutionSnapshot:
    """Polling-ready projection with stale-snapshot comparison metadata."""

    execution_id: str
    run_id: str
    status: ProductExecutionStatus
    runtime_state: RunStatus | None
    current_milestone: str | None
    current_activity: str | None
    terminal: bool
    latest_sequence: int | None
    human_evidence: HumanEvidenceDTO
    technical_evidence: TechnicalEvidenceDTO

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "status": self.status.value,
            "runtime_state": self.runtime_state.value if self.runtime_state else None,
            "current_milestone": self.current_milestone,
            "current_activity": self.current_activity,
            "terminal": self.terminal,
            "latest_sequence": self.latest_sequence,
            "human_evidence": self.human_evidence.to_dict(),
            "technical_evidence": self.technical_evidence.to_dict(),
        }


class EvidenceService:
    """Reconstruct read-only projections from RunStorage and product facts."""

    def __init__(self, storage: RunStorage, execution_service: ExecutionService | None = None) -> None:
        self.storage = storage
        self.execution_service = execution_service

    def snapshot(self, execution_id: str) -> ProductExecutionSnapshot:
        try:
            state = self.storage.read_run_state(execution_id)
        except FileNotFoundError:
            return self._early_failure_snapshot(execution_id)
        events = self.storage.read_events(execution_id)
        report = self._read_report(execution_id)
        product = self._product_snapshot(execution_id, state)
        milestone, activity = self._progress(state, events, product.status, report)
        latest_sequence = max((event.sequence or 0 for event in events), default=0) or None
        human = self._human(execution_id, state, report, product.status, milestone, activity)
        technical = self._technical(execution_id, state, report, product.status, events)
        return ProductExecutionSnapshot(
            execution_id=execution_id,
            run_id=state.run_id,
            status=product.status,
            runtime_state=state.state,
            current_milestone=milestone,
            current_activity=activity,
            terminal=product.status is not ProductExecutionStatus.RUNNING,
            latest_sequence=latest_sequence,
            human_evidence=human,
            technical_evidence=technical,
        )

    def _early_failure_snapshot(self, execution_id: str) -> ProductExecutionSnapshot:
        """Project a terminal product failure that predates RunState creation."""
        if self.execution_service is None:
            raise FileNotFoundError(f"run state not found: {execution_id}")
        product = self.execution_service.get(execution_id)
        reason = product.reason
        human = HumanEvidenceDTO(
            execution_id=execution_id,
            status=product.status.value,
            current_activity=reason,
        )
        technical = TechnicalEvidenceDTO(
            execution_id=execution_id,
            run_id=product.execution.run_id,
            status=product.status.value,
            started_at=product.execution.created_at.isoformat(),
            failure_classification=reason,
        )
        return ProductExecutionSnapshot(
            execution_id=execution_id,
            run_id=product.execution.run_id,
            status=product.status,
            runtime_state=None,
            current_milestone=None,
            current_activity=reason,
            terminal=product.terminal,
            latest_sequence=None,
            human_evidence=human,
            technical_evidence=technical,
        )

    @staticmethod
    def is_stale(candidate: ProductExecutionSnapshot, rendered: ProductExecutionSnapshot) -> bool:
        """Return true when candidate cannot replace the rendered snapshot."""
        if candidate.execution_id != rendered.execution_id or candidate.run_id != rendered.run_id:
            return True
        return (candidate.latest_sequence or 0) < (rendered.latest_sequence or 0)

    @staticmethod
    def is_newer(candidate: ProductExecutionSnapshot, rendered: ProductExecutionSnapshot) -> bool:
        return not EvidenceService.is_stale(candidate, rendered) and (candidate.latest_sequence or 0) > (rendered.latest_sequence or 0)

    def human_evidence(self, execution_id: str) -> HumanEvidenceDTO:
        return self.snapshot(execution_id).human_evidence

    def technical_evidence(self, execution_id: str) -> TechnicalEvidenceDTO:
        return self.snapshot(execution_id).technical_evidence

    def _read_report(self, execution_id: str) -> FinalReport | None:
        try:
            return self.storage.read_final_report(execution_id)
        except (OSError, KeyError, ValueError):
            return None

    def _product_snapshot(self, execution_id: str, state: RunState) -> ExecutionSnapshot:
        if self.execution_service is not None:
            try:
                return self.execution_service.get(execution_id)
            except Exception:
                pass
        status = ProductExecutionStatus.RUNNING
        if state.state is RunStatus.BLOCKED:
            status = ProductExecutionStatus.BLOCKED
        elif state.state is RunStatus.LIMIT_REACHED:
            status = ProductExecutionStatus.LIMIT_REACHED
        elif state.state is RunStatus.ABORTED:
            status = ProductExecutionStatus.INTERRUPTED
        elif state.state is RunStatus.COMPLETED:
            status = ProductExecutionStatus.SUCCEEDED if self._completion_is_authoritative(state, self._read_report(execution_id)) else ProductExecutionStatus.FAILED
        elif state.state.is_terminal():
            status = ProductExecutionStatus.FAILED
        return ExecutionSnapshot(
            ExecutionRecord(execution_id=execution_id, task_id=execution_id, run_id=state.run_id, created_at=state.started_at),
            status,
            state.termination_reason,
        )

    def _progress(self, state: RunState, events: tuple[RunEvent, ...], status: ProductExecutionStatus, report: FinalReport | None) -> tuple[str | None, str | None]:
        event_types = [event.event_type for event in events]
        if status is ProductExecutionStatus.SUCCEEDED and state.state is RunStatus.COMPLETED:
            return "Entregando", None
        if any(item in event_types for item in (RunEventType.REPAIR_ATTEMPT_RECORDED, RunEventType.SEMANTIC_REPAIR_FEEDBACK, RunEventType.FAILURE_ACTIVE)) or state.state in {RunStatus.DIAGNOSING, RunStatus.CORRECTING}:
            return "Reparando", "Trabajando · Reparando un problema"
        if state.state is RunStatus.VALIDATING_FUNCTIONAL or any(item in event_types for item in (RunEventType.RUNTIME_VALIDATION_RECORDED, RunEventType.VALIDATION_COMPLETED)):
            return "Probando", "Trabajando · Probando el resultado"
        if state.state is RunStatus.VALIDATING_ARTIFACT or any(item in event_types for item in (RunEventType.ARTIFACT_VALIDATED, RunEventType.COMPLETION_GATE_EVALUATED)):
            return "Verificando", "Trabajando · Verificando el resultado"
        if state.state is RunStatus.BUILDING or any(item in event_types for item in (RunEventType.BUILD_STARTED, RunEventType.BUILD_FINISHED, RunEventType.BUILD_ATTEMPT_RECORDED)):
            return "Compilando", "Trabajando · Compilando"
        if state.state is RunStatus.EDITING or any(item in event_types for item in (RunEventType.FILE_CHANGED, RunEventType.TOOL_EXECUTED)):
            return "Editando", "Trabajando · Editando archivos"
        if any(item in event_types for item in (RunEventType.KNOWLEDGE_RETRIEVED, RunEventType.KNOWLEDGE_SELECTED, RunEventType.KNOWLEDGE_REFERENCED)):
            return "Investigando", "Trabajando · Investigando"
        if state.state in {RunStatus.INSPECTING, RunStatus.PLANNING}:
            return "Entendiendo", "Trabajando · Entendiendo la tarea"
        if state.state is RunStatus.REPORTING and report is not None:
            return "Entregando", None
        return None, None

    def _human(self, execution_id: str, state: RunState, report: FinalReport | None, status: ProductExecutionStatus, milestone: str | None, activity: str | None) -> HumanEvidenceDTO:
        builds = len(state.build_results)
        build_summary = f"{builds} intento(s) de compilación; último resultado: {'PASS' if state.build_results and state.build_results[-1].success else 'no PASS'}" if builds else None
        repair_summary = "Se detectó evidencia de reparación" if any(result.status.value == "REPAIRABLE_FAIL" for result in state.validation_results) else None
        runtime = next((result.status.value for result in reversed(state.validation_results) if result.stage is ValidationStage.RUNTIME), None)
        artifact = "Artefacto válido" if state.artifact_result is not None and state.artifact_result.classification == "VALID" else None
        completion = report.completion_status if report and report.completion_status else ("Completada" if status is ProductExecutionStatus.SUCCEEDED else None)
        return HumanEvidenceDTO(execution_id, status.value, milestone, activity, _safe_changed_files(state.changed_files), build_summary, repair_summary, runtime, completion, artifact)

    def _technical(self, execution_id: str, state: RunState, report: FinalReport | None, status: ProductExecutionStatus, events: tuple[RunEvent, ...]) -> TechnicalEvidenceDTO:
        builds = tuple({"attempt": result.attempt, "exit_code": result.exit_code, "success": result.success} for result in state.build_results)
        validations = tuple({"stage": result.stage.value, "status": result.status.value} for result in state.validation_results)
        observations = tuple({"event_type": event.event_type.value, "sequence": event.sequence} for event in events if event.event_type in {RunEventType.RUNTIME_VALIDATION_RECORDED, RunEventType.VALIDATION_COMPLETED})
        artifact_sha = state.artifact_result.metadata.get("sha256") if state.artifact_result is not None else None
        return TechnicalEvidenceDTO(execution_id, state.run_id, status.value, state.state.value, state.started_at.isoformat(), _safe_changed_files(state.changed_files), builds, validations, observations, state.provider_error_kind, artifact_sha, report.evidence_refs if report else ())

    @staticmethod
    def _completion_is_authoritative(state: RunState, report: FinalReport | None) -> bool:
        return bool(report and report.final_state is RunStatus.COMPLETED and report.completion_status in {"PASS", "SUCCEEDED"})


def _safe_changed_files(paths: tuple[str, ...]) -> tuple[str, ...]:
    safe: list[str] = []
    for raw in paths:
        normalized = raw.replace("\\", "/")
        path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(normalized)
        if normalized.startswith("/") or path.is_absolute() or windows_path.drive or windows_path.root or ".." in path.parts or not normalized:
            continue
        safe.append(normalized)
    return tuple(dict.fromkeys(safe))


__all__ = ["EvidenceService", "HumanEvidenceDTO", "MILESTONES", "ProductExecutionSnapshot", "TechnicalEvidenceDTO"]
