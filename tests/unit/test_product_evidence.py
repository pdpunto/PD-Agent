from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pd_agent.core import RunState, RunStatus
from pd_agent.product import EvidenceService, ExecutionRecord, HumanEvidenceDTO, ProductExecutionSnapshot, ProductExecutionStatus, TechnicalEvidenceDTO
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage


def _persist(
    tmp_path: Path,
    *,
    state: RunState,
    events: tuple[RunEvent, ...] = (),
    report: FinalReport | None = None,
) -> tuple[RunStorage, str]:
    storage = RunStorage(tmp_path / "runs")
    storage.write_run_state(state)
    for event in events:
        storage.append_event(event)
    if report is not None:
        storage.write_final_report(report)
    return storage, state.run_id


def _state(tmp_path: Path, status: RunStatus) -> RunState:
    return RunState(run_id=str(uuid4()), project_root=tmp_path, task="task", state=status)


def test_progress_mapping_uses_real_state_and_event_authority(tmp_path: Path) -> None:
    cases = (
        (RunStatus.INSPECTING, (), "Entendiendo"),
        (RunStatus.EDITING, (RunEventType.FILE_CHANGED,), "Editando"),
        (RunStatus.BUILDING, (RunEventType.BUILD_STARTED,), "Compilando"),
        (RunStatus.VALIDATING_FUNCTIONAL, (RunEventType.RUNTIME_VALIDATION_RECORDED,), "Probando"),
        (RunStatus.VALIDATING_ARTIFACT, (RunEventType.ARTIFACT_VALIDATED,), "Verificando"),
        (RunStatus.DIAGNOSING, (), "Reparando"),
        (RunStatus.REPORTING, (), "Entregando"),
    )
    for index, (status, event_types, expected) in enumerate(cases):
        state = _state(tmp_path / str(index), status)
        state.project_root.mkdir(parents=True)
        events = tuple(RunEvent(run_id=state.run_id, event_type=event_type) for event_type in event_types)
        report = FinalReport(run_id=state.run_id, final_state=status, summary="report") if status is RunStatus.REPORTING else None
        storage, run_id = _persist(tmp_path / f"persisted-{index}", state=state, events=events, report=report)
        snapshot = EvidenceService(storage).snapshot(run_id)
        assert snapshot.current_milestone == expected


def test_knowledge_and_repair_activity_require_real_events(tmp_path: Path) -> None:
    state = _state(tmp_path, RunStatus.INITIALIZING)
    storage, run_id = _persist(
        tmp_path,
        state=state,
        events=(RunEvent(run_id=state.run_id, event_type=RunEventType.KNOWLEDGE_RETRIEVED),),
    )
    snapshot = EvidenceService(storage).snapshot(run_id)
    assert snapshot.current_milestone == "Investigando"
    assert snapshot.current_activity == "Trabajando · Investigando"

    repair_state = _state(tmp_path / "repair", RunStatus.CORRECTING)
    repair_state.project_root.mkdir(parents=True)
    storage, run_id = _persist(tmp_path / "repair-persisted", state=repair_state)
    repair = EvidenceService(storage).snapshot(run_id)
    assert repair.current_milestone == "Reparando"
    assert repair.current_activity == "Trabajando · Reparando un problema"


def test_unsupported_activity_is_not_fabricated(tmp_path: Path) -> None:
    state = _state(tmp_path, RunStatus.INITIALIZING)
    storage, run_id = _persist(tmp_path, state=state)
    snapshot = EvidenceService(storage).snapshot(run_id)
    assert snapshot.current_milestone is None
    assert snapshot.current_activity is None
    assert "percent" not in snapshot.to_dict()


def test_success_requires_authoritative_completion_evidence(tmp_path: Path) -> None:
    state = _state(tmp_path, RunStatus.COMPLETED)
    report = FinalReport(run_id=state.run_id, final_state=RunStatus.COMPLETED, summary="done")
    storage, run_id = _persist(tmp_path, state=state, report=report)
    assert EvidenceService(storage).snapshot(run_id).status is ProductExecutionStatus.FAILED

    passed = FinalReport(
        run_id=state.run_id,
        final_state=RunStatus.COMPLETED,
        summary="done",
        completion_status="PASS",
    )
    storage.write_final_report(passed)
    assert EvidenceService(storage).snapshot(run_id).status is ProductExecutionStatus.SUCCEEDED


def test_terminal_projections_are_truthful(tmp_path: Path) -> None:
    for index, status in enumerate((RunStatus.FAILED, RunStatus.BLOCKED, RunStatus.LIMIT_REACHED, RunStatus.ABORTED)):
        state = _state(tmp_path / str(index), status)
        state.project_root.mkdir(parents=True)
        storage, run_id = _persist(tmp_path / f"terminal-{index}", state=state)
        projected = EvidenceService(storage).snapshot(run_id)
        expected = {
            RunStatus.FAILED: ProductExecutionStatus.FAILED,
            RunStatus.BLOCKED: ProductExecutionStatus.BLOCKED,
            RunStatus.LIMIT_REACHED: ProductExecutionStatus.LIMIT_REACHED,
            RunStatus.ABORTED: ProductExecutionStatus.INTERRUPTED,
        }[status]
        assert projected.status is expected


def test_early_product_failure_has_safe_evidence_without_run_state(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    execution = ExecutionRecord(run_id=str(uuid4()), task_id=str(uuid4()))

    class ProductFailureService:
        def get(self, execution_id: str):
            assert execution_id == execution.execution_id
            from pd_agent.product.execution import ExecutionSnapshot

            return ExecutionSnapshot(
                execution,
                ProductExecutionStatus.FAILED,
                "task_contract_resolution_failed",
                terminal=True,
            )

    service = EvidenceService(storage, ProductFailureService())
    snapshot = service.snapshot(execution.execution_id)

    assert snapshot.status is ProductExecutionStatus.FAILED
    assert snapshot.terminal is True
    assert snapshot.runtime_state is None
    assert snapshot.human_evidence.current_activity == "task_contract_resolution_failed"
    assert snapshot.technical_evidence.failure_classification == "task_contract_resolution_failed"
    assert snapshot.technical_evidence.build_attempts == ()
    assert snapshot.technical_evidence.runtime_observations == ()


def test_snapshot_has_monotonic_stale_comparison(tmp_path: Path) -> None:
    state = _state(tmp_path, RunStatus.BUILDING)
    storage, run_id = _persist(tmp_path, state=state, events=(RunEvent(run_id=state.run_id, event_type=RunEventType.BUILD_STARTED),))
    old = EvidenceService(storage).snapshot(run_id)
    storage.append_event(RunEvent(run_id=state.run_id, event_type=RunEventType.BUILD_FINISHED))
    new = EvidenceService(storage).snapshot(run_id)
    assert new.latest_sequence == 2
    assert EvidenceService.is_stale(old, new)
    assert EvidenceService.is_newer(new, old)
    assert not EvidenceService.is_stale(new, old)


def test_allowlisted_dtos_exclude_sensitive_payloads_and_paths(tmp_path: Path) -> None:
    state = _state(tmp_path, RunStatus.EDITING)
    state.changed_files = ("src/main.py", r"C:\secret\key.txt", "../outside.txt")
    storage, run_id = _persist(
        tmp_path,
        state=state,
        events=(
            RunEvent(
                run_id=state.run_id,
                event_type=RunEventType.MODEL_RESPONDED,
                payload={
                    "api_key": "secret",
                    "authorization": "Bearer secret",
                    "system_prompt": "private",
                    "chain_of_thought": "private",
                    "provider_response": {"token": "secret"},
                    "traceback": "private",
                    "absolute_path": r"C:\secret\file",
                },
            ),
        ),
    )
    snapshot = EvidenceService(storage).snapshot(run_id)
    human = snapshot.human_evidence.to_dict()
    technical = snapshot.technical_evidence.to_dict()
    serialized = str(human) + str(technical)
    for secret in ("secret", "Bearer", "private", "C:\\secret"):
        assert secret not in serialized
    assert human["changes"] == ["src/main.py"]
    assert "MODEL_RESPONDED" not in serialized
    assert "payload" not in technical


def test_run_history_and_catalog_are_not_mutated_by_projection(tmp_path: Path) -> None:
    state = _state(tmp_path, RunStatus.INSPECTING)
    storage, run_id = _persist(tmp_path, state=state, events=(RunEvent(run_id=state.run_id, event_type=RunEventType.RUN_STARTED),))
    before_state = storage.read_run_state(run_id).to_dict()
    before_events = tuple(event.to_dict() for event in storage.read_events(run_id))
    EvidenceService(storage).snapshot(run_id)
    assert storage.read_run_state(run_id).to_dict() == before_state
    assert tuple(event.to_dict() for event in storage.read_events(run_id)) == before_events


def test_dto_shapes_are_explicit_allowlists() -> None:
    human = HumanEvidenceDTO("id", "RUNNING")
    technical = TechnicalEvidenceDTO("id", "id", "RUNNING")
    assert set(human.to_dict()) == {
        "execution_id", "status", "current_milestone", "current_activity", "changes",
        "build_summary", "repair_summary", "runtime_validation_summary", "completion_summary", "artifact_summary",
    }
    assert set(technical.to_dict()) == {
        "execution_id", "run_id", "status", "runtime_state", "started_at", "changed_files",
        "build_attempts", "validation_summaries", "runtime_observations", "failure_classification", "artifact_sha256", "evidence_refs",
    }
