"""Benchmark dataset execution runner."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from pd_agent.core import ExecutionLimits, generate_run_id

from .aggregator import BenchmarkAggregator, render_comparison_markdown
from .executor import BenchmarkExecutionResult, BenchmarkExecutor
from .models import (
    BenchmarkBatchStatus,
    BenchmarkComparison,
    BenchmarkConfig,
    BenchmarkRun,
    BenchmarkTaskReference,
    BenchmarkExecutionStatus,
    BenchmarkFailureCode,
    BenchmarkExecutionState,
    BenchmarkRecoveryState,
)
from .scheduler import BenchmarkSchedule, BenchmarkScheduledAttempt, BenchmarkScheduler
from .catalog import BenchmarkCatalog
from pd_agent.experimental import (
    LUNA_ECONOMIC_SCHEMA_VERSION,
    LUNA_EXPERIMENTAL_HARD_BUDGET_USD,
    LUNA_PER_ATTEMPT_HARD_BUDGET_USD,
    LunaBudgetGuard,
    LunaEconomicState,
    LunaEconomicStateStore,
    DispatchRecord,
    DISPATCH_STARTED,
    RESPONSE_MISSING,
    UNCERTAIN_CONSUMED,
)
from pd_agent.core import AgentMessage, AgentRequest
from pd_agent.providers import (
    RecoveryCoordinator,
    RECOVERY_BUDGET_BLOCKED,
    RECOVERY_DISPATCH_UNCERTAIN,
    RECOVERY_EXISTING_RESPONSE,
    RECOVERY_IDENTITY_INVALID,
    RECOVERY_LIMIT_EXHAUSTED,
    RECOVERY_PRE_DISPATCH_FAILED,
    RECOVERY_PROVIDER_FAILURE,
    RECOVERY_RECONCILIATION_UNSUPPORTED,
    RECOVERY_REISSUE_SUCCEEDED,
)


def _write_json(path: Path, data: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    return path


def _load_json(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return data


class BenchmarkExecutionResumeError(ValueError):
    """Raised when a resume request cannot be satisfied safely."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _attempt_key(
    task_id: str,
    task_version: str,
    config_id: str,
    config_hash: str,
    repetition_index: int,
    attempt_index: int,
) -> tuple[str, str, str, str, int, int]:
    return (task_id, task_version, config_id, config_hash, int(repetition_index), int(attempt_index))


def _attempt_key_from_attempt(attempt: BenchmarkScheduledAttempt) -> tuple[str, str, str, str, int, int]:
    return _attempt_key(
        attempt.task_id,
        attempt.task_version,
        attempt.config_id,
        attempt.config_hash,
        attempt.repetition_index,
        attempt.attempt_index,
    )


def _attempt_key_from_run(run: BenchmarkRun) -> tuple[str, str, str, str, int, int]:
    return _attempt_key(
        run.task_id,
        run.task_version,
        run.config_id,
        run.config_hash,
        run.repetition_index,
        run.attempt_index,
    )


def _completed_attempt_keys(schedule: BenchmarkSchedule) -> set[tuple[str, str, str, str, int, int]]:
    return {_attempt_key_from_run(run) for cell in schedule.cells for run in cell.completed_runs}


def _completed_runs(schedule: BenchmarkSchedule) -> tuple[BenchmarkRun, ...]:
    runs: list[BenchmarkRun] = []
    for attempt in schedule.attempts:
        cell = schedule.cell(attempt.task_id, attempt.task_version, attempt.config_id, attempt.config_hash)
        for run in cell.completed_runs:
            if _attempt_key_from_run(run) == _attempt_key_from_attempt(attempt):
                runs.append(run)
                break
    return tuple(runs)


def _next_pending_attempt(
    schedule: BenchmarkSchedule,
    completed_keys: set[tuple[str, str, str, str, int, int]],
    *,
    start_index: int = 0,
) -> BenchmarkScheduledAttempt | None:
    for attempt in schedule.attempts[start_index:]:
        if _attempt_key_from_attempt(attempt) not in completed_keys:
            return attempt
    return None


@dataclass(frozen=True, slots=True)
class BenchmarkExecutionManifest:
    """Execution manifest for one benchmark batch."""

    execution_id: str
    dataset_id: str
    dataset_version: str
    dataset_tasks: tuple[BenchmarkTaskReference, ...]
    configs: tuple[BenchmarkConfig, ...]
    target_valid_repetitions: int
    max_attempts_per_cell: int
    scheduling_seed: int | None
    pd_agent_commit: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    economic_schema_version: int | None = None
    global_economic_ceiling_usd: str | None = None
    attempt_economic_ceiling_usd: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "execution_id": self.execution_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_tasks": [task.to_dict() for task in self.dataset_tasks],
            "configs": [config.to_dict() for config in self.configs],
            "target_valid_repetitions": self.target_valid_repetitions,
            "max_attempts_per_cell": self.max_attempts_per_cell,
            "scheduling_seed": self.scheduling_seed,
            "pd_agent_commit": self.pd_agent_commit,
            "created_at": self.created_at.isoformat(),
            "economic_schema_version": self.economic_schema_version,
            "global_economic_ceiling_usd": self.global_economic_ceiling_usd,
            "attempt_economic_ceiling_usd": self.attempt_economic_ceiling_usd,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkExecutionManifest":
        if int(data.get("schema_version", 1)) != 1:
            raise ValueError("unsupported BenchmarkExecutionManifest schema_version")
        return cls(
            execution_id=str(data["execution_id"]),
            dataset_id=str(data["dataset_id"]),
            dataset_version=str(data["dataset_version"]),
            dataset_tasks=tuple(BenchmarkTaskReference.from_dict(dict(item)) for item in data.get("dataset_tasks", [])),
            configs=tuple(BenchmarkConfig.from_dict(dict(item)) for item in data.get("configs", [])),
            target_valid_repetitions=int(data.get("target_valid_repetitions", 3)),
            max_attempts_per_cell=int(data.get("max_attempts_per_cell", 5)),
            scheduling_seed=data.get("scheduling_seed"),
            pd_agent_commit=data.get("pd_agent_commit"),
            created_at=datetime.fromisoformat(str(data.get("created_at", datetime.now(timezone.utc).isoformat()))),
            economic_schema_version=(int(data["economic_schema_version"]) if data.get("economic_schema_version") is not None else None),
            global_economic_ceiling_usd=data.get("global_economic_ceiling_usd"),
            attempt_economic_ceiling_usd=data.get("attempt_economic_ceiling_usd"),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkExecutionBatch:
    """Persisted benchmark batch output."""

    execution_id: str
    execution_root: Path
    batch_status: BenchmarkBatchStatus
    manifest: BenchmarkExecutionManifest
    schedule: BenchmarkSchedule
    execution_state: BenchmarkExecutionState
    comparison: BenchmarkComparison
    runs: tuple[BenchmarkRun, ...]
    manifest_path: Path
    schedule_path: Path
    execution_state_path: Path
    comparison_json_path: Path
    comparison_md_path: Path


@dataclass(frozen=True, slots=True)
class BenchmarkRecoveryReconstruction:
    """Validated restart snapshot; reconstruction never calls a provider."""

    execution_state: BenchmarkExecutionState
    economic_state: LunaEconomicState | None
    pending_physical_request_ids: tuple[str, ...] = ()
    legacy: bool = False


@dataclass(slots=True)
class BenchmarkExecutionRunner:
    """Drive a whole benchmark dataset through schedule, executor and aggregator."""

    executor: BenchmarkExecutor
    scheduler: BenchmarkScheduler = field(default_factory=BenchmarkScheduler)
    aggregator: BenchmarkAggregator = field(default_factory=BenchmarkAggregator)
    logical_session_cap: int = 400
    target_valid_repetitions: int = 3
    max_attempts_per_cell: int = 5
    scheduling_seed: int | None = None
    recovery_coordinator: RecoveryCoordinator | None = None

    def __post_init__(self) -> None:
        if self.logical_session_cap <= 0:
            raise ValueError("logical_session_cap must be positive")

    def reconstruct_execution(self, execution_dir: Path) -> BenchmarkRecoveryReconstruction:
        """Load and validate durable state without dispatching or rewriting it."""

        execution_dir = Path(execution_dir).resolve(strict=True)
        state_path = execution_dir / "execution_state.json"
        manifest_path = execution_dir / "manifest.json"
        economic_path = execution_dir / "economic-state.json"
        try:
            manifest = BenchmarkExecutionManifest.from_dict(_load_json(manifest_path))
            execution_state = BenchmarkExecutionState.from_dict(_load_json(state_path))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise BenchmarkExecutionResumeError("malformed durable execution state", code="RECONSTRUCTION_INVALID_STATE") from exc
        if execution_state.execution_id != manifest.execution_id or execution_dir.name != manifest.execution_id:
            raise BenchmarkExecutionResumeError("execution identity mismatch during reconstruction", code="RECONSTRUCTION_DRIFT")
        if manifest.economic_schema_version is None:
            return BenchmarkRecoveryReconstruction(execution_state=execution_state, economic_state=None, legacy=True)
        try:
            economic_store = LunaEconomicStateStore.load(economic_path)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise BenchmarkExecutionResumeError("malformed durable economic state", code="RECONSTRUCTION_ECONOMIC_STATE") from exc
        economic = economic_store.state
        if economic.execution_id != manifest.execution_id:
            raise BenchmarkExecutionResumeError("economic execution identity mismatch", code="RECONSTRUCTION_DRIFT")
        records = {}
        for physical_id, raw in economic.dispatch_records.items():
            try:
                record = DispatchRecord.from_dict(raw)
            except (TypeError, ValueError) as exc:
                raise BenchmarkExecutionResumeError("malformed dispatch record", code="RECONSTRUCTION_DISPATCH_STATE") from exc
            if str(physical_id) != record.physical_request_id:
                raise BenchmarkExecutionResumeError("duplicate or mismatched physical dispatch identity", code="RECONSTRUCTION_DISPATCH_STATE")
            if record.reservation_id is not None:
                ledger = economic.ledger.get(record.reservation_id)
                if not isinstance(ledger, Mapping):
                    raise BenchmarkExecutionResumeError("dispatch reservation is missing", code="RECONSTRUCTION_LEDGER_STATE")
                if ledger.get("attempt_id") != record.logical_attempt_id:
                    raise BenchmarkExecutionResumeError("dispatch logical attempt mismatch", code="RECONSTRUCTION_LEDGER_STATE")
                if record.dispatch_state == DISPATCH_STARTED and ledger.get("status") != UNCERTAIN_CONSUMED and record.functional_state == RESPONSE_MISSING:
                    raise BenchmarkExecutionResumeError("response-missing dispatch is not economically uncertain", code="RECONSTRUCTION_LEDGER_STATE")
            records[record.physical_request_id] = record
        children: dict[str, list[DispatchRecord]] = {}
        for record in records.values():
            if record.recovery_of is None:
                continue
            parent = records.get(record.recovery_of)
            if parent is None or record.recovery_generation != parent.recovery_generation + 1:
                raise BenchmarkExecutionResumeError("invalid recovery parent or generation", code="RECONSTRUCTION_RECOVERY_STATE")
            if record.logical_attempt_id != parent.logical_attempt_id:
                raise BenchmarkExecutionResumeError("recovery logical attempt mismatch", code="RECONSTRUCTION_RECOVERY_STATE")
            children.setdefault(parent.physical_request_id, []).append(record)
        if any(len(items) > 1 for items in children.values()):
            raise BenchmarkExecutionResumeError("duplicate recovery generation", code="RECONSTRUCTION_RECOVERY_STATE")
        if execution_state.recovery_state is not None:
            try:
                recovery_state = BenchmarkRecoveryState.from_dict(dict(execution_state.recovery_state))
            except (TypeError, ValueError, KeyError) as exc:
                raise BenchmarkExecutionResumeError("malformed recovery state", code="RECONSTRUCTION_RECOVERY_STATE") from exc
            original = records.get(recovery_state.original_physical_request_id)
            if original is None or original.logical_attempt_id != recovery_state.logical_attempt_id:
                raise BenchmarkExecutionResumeError("recovery state references unknown dispatch", code="RECONSTRUCTION_RECOVERY_STATE")
            if recovery_state.recovery_physical_request_id is not None:
                recovery = records.get(recovery_state.recovery_physical_request_id)
                if recovery is None or recovery.recovery_of != original.physical_request_id:
                    raise BenchmarkExecutionResumeError("recovery state physical identity mismatch", code="RECONSTRUCTION_RECOVERY_STATE")
        pending = tuple(
            record.physical_request_id
            for record in records.values()
            if record.dispatch_state == DISPATCH_STARTED
            and record.functional_state == RESPONSE_MISSING
            and economic.ledger.get(record.reservation_id or "", {}).get("status") == UNCERTAIN_CONSUMED
        )
        return BenchmarkRecoveryReconstruction(
            execution_state=execution_state,
            economic_state=economic,
            pending_physical_request_ids=pending,
            legacy=False,
        )

    def _budget_guard(self) -> LunaBudgetGuard | None:
        provider = getattr(self.executor, "provider", None)
        if provider is None:
            return None
        while hasattr(provider, "provider"):
            provider = provider.provider
        guard = getattr(provider, "budget_guard", None)
        return guard if isinstance(guard, LunaBudgetGuard) else None

    def _configure_new_economic_state(self, *, execution_id: str, execution_dir: Path) -> LunaBudgetGuard | None:
        guard = self._budget_guard()
        if guard is None:
            return None
        guard.state.execution_id = execution_id
        guard.state_store = LunaEconomicStateStore(guard.state, path=execution_dir / "economic-state.json")
        guard.state_store.persist()
        return guard

    def _restore_economic_state(self, *, execution_dir: Path, execution_id: str) -> LunaBudgetGuard | None:
        guard = self._budget_guard()
        if guard is None:
            return None
        economic_path = execution_dir / "economic-state.json"
        if not economic_path.exists():
            raise BenchmarkExecutionResumeError("missing dual-budget economic state", code="RESUME_ECONOMIC_SCHEMA")
        try:
            store = LunaEconomicStateStore.load(economic_path)
        except (OSError, ValueError, TypeError) as exc:
            raise BenchmarkExecutionResumeError("incompatible dual-budget economic state", code="RESUME_ECONOMIC_SCHEMA") from exc
        if store.state.execution_id != execution_id:
            raise BenchmarkExecutionResumeError("economic execution identity drift detected", code="RESUME_DRIFT")
        if store.state.reconciliation_state != "CLEAR" and not self._has_modern_recovery_evidence(store.state):
            raise BenchmarkExecutionResumeError(
                "economic state contains unreconciled post-dispatch consumption",
                code="RESUME_ECONOMIC_UNCERTAIN",
            )
        guard.state = store.state
        guard.state_store = store
        return guard

    @staticmethod
    def _has_modern_recovery_evidence(state: LunaEconomicState) -> bool:
        """Return true only for a complete R1-R5 response-missing record."""

        for raw in state.dispatch_records.values():
            try:
                record = DispatchRecord.from_dict(raw)
            except (TypeError, ValueError):
                continue
            ledger = state.ledger.get(record.reservation_id or "")
            if (
                record.dispatch_state == DISPATCH_STARTED
                and record.functional_state == RESPONSE_MISSING
                and isinstance(ledger, Mapping)
                and ledger.get("status") == UNCERTAIN_CONSUMED
            ):
                return True
        return False

    def _economic_state_payload(self) -> Mapping[str, Any] | None:
        guard = self._budget_guard()
        return guard.state.to_dict() if guard is not None else None

    def _pending_recovery_record(
        self,
        *,
        attempt: BenchmarkScheduledAttempt,
    ) -> DispatchRecord | None:
        guard = self._budget_guard()
        if guard is None:
            return None
        matches: list[DispatchRecord] = []
        for raw in guard.state.dispatch_records.values():
            try:
                record = DispatchRecord.from_dict(raw)
            except (TypeError, ValueError):
                continue
            ledger = guard.state.ledger.get(record.reservation_id or "")
            if (
                record.logical_attempt_id == attempt.scheduled_attempt_id
                and record.dispatch_state == DISPATCH_STARTED
                and record.functional_state == RESPONSE_MISSING
                and isinstance(ledger, Mapping)
                and ledger.get("status") == UNCERTAIN_CONSUMED
            ):
                matches.append(record)
        if len(matches) > 1:
            raise BenchmarkExecutionResumeError(
                "multiple uncertain dispatches match one logical attempt",
                code="RESUME_RECOVERY_IDENTITY",
            )
        return matches[0] if matches else None

    def _recovery_request(
        self,
        *,
        task: Any,
        config: BenchmarkConfig,
    ) -> AgentRequest:
        """Build the bounded recovery request without changing scheduler identity."""

        return AgentRequest(
            messages=(AgentMessage(role="user", content=task.prompt),),
            model_config=dict(config.model_config),
        )

    def _recover_pending(
        self,
        *,
        record: DispatchRecord,
        task: Any,
        config: BenchmarkConfig,
        attempt: BenchmarkScheduledAttempt,
        execution_dir: Path,
        pd_agent_commit: str | None,
        fixture_root: Path,
        knowledge_needs: Sequence[Any] | None,
        preserve_workspaces: bool,
    ) -> tuple[BenchmarkExecutionResult | None, Mapping[str, Any]]:
        provider = getattr(self.executor, "provider", None)
        coordinator = self.recovery_coordinator
        if coordinator is None and provider is not None:
            coordinator = RecoveryCoordinator(
                provider,
                budget_guard=self._budget_guard(),
            )
        if coordinator is None:
            return None, {
                "status": RECOVERY_RECONCILIATION_UNSUPPORTED,
                "reason": "recovery coordinator is unavailable",
                "original_physical_request_id": record.physical_request_id,
                "logical_attempt_id": record.logical_attempt_id,
            }
        outcome = coordinator.recover(record, self._recovery_request(task=task, config=config))
        evidence = outcome.to_dict()
        evidence.pop("response", None)
        evidence.update(
            {
                "recovery_state_schema_version": 1,
                "terminal_state": "PAUSED",
                "continuation_status": "NOT_ATTEMPTED",
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if outcome.status not in {RECOVERY_EXISTING_RESPONSE, RECOVERY_REISSUE_SUCCEEDED}:
            return None, evidence

        continuation = getattr(self.executor, "continue_recovered_response", None)
        if not callable(continuation):
            evidence = {
                **evidence,
                "continuation": "unavailable",
                "reason": "executor cannot continue a recovered AgentResponse",
            }
            evidence["reason"] = evidence["reason"]
            return None, evidence
        result = continuation(
            outcome.response,
            task,
            config,
            attempt,
            fixture_root=fixture_root,
            execution_root=execution_dir,
            pd_agent_commit=pd_agent_commit,
            knowledge_needs=knowledge_needs,
            preserve_workspace=preserve_workspaces,
            recovery=evidence,
        )
        if not isinstance(result, BenchmarkExecutionResult):
            evidence = {
                **evidence,
                "continuation": "invalid",
                "reason": "executor returned no benchmark result for recovered response",
            }
            return None, evidence
        evidence["terminal_state"] = "RECOVERED"
        evidence["continuation_status"] = "COMPLETED"
        return result, evidence

    def _paused_batch(
        self,
        *,
        batch_status: BenchmarkBatchStatus,
        reason: str,
        logical_requests_used: int,
        reservation: int,
        attempt: BenchmarkScheduledAttempt,
        current_state: BenchmarkExecutionState,
        schedule: BenchmarkSchedule,
        dataset: Any,
        configs: Sequence[BenchmarkConfig],
        tasks: Sequence[Any],
        manifest: BenchmarkExecutionManifest,
        execution_dir: Path,
        manifest_path: Path,
        schedule_path: Path,
        execution_state_path: Path,
    ) -> BenchmarkExecutionBatch:
        state = BenchmarkExecutionState(
            execution_id=manifest.execution_id,
            batch_status=batch_status,
            logical_budget_cap=self.logical_session_cap,
            logical_budget_used=logical_requests_used,
            logical_budget_remaining=max(self.logical_session_cap - logical_requests_used, 0),
            attempt_reservation=reservation,
            pause_reason=reason,
            paused_at=datetime.now(timezone.utc),
            next_pending_schedule_item=attempt.to_dict(),
            session_id=current_state.session_id,
            session_index=current_state.session_index,
            resume_count=current_state.resume_count,
            recovery_state=current_state.recovery_state,
        )
        _write_json(schedule_path, schedule.to_dict())
        execution_state_path = self._write_execution_state(execution_state_path, state)
        comparison = self._aggregate_comparison(
            _completed_runs(schedule), dataset=dataset, configs=configs, tasks=tasks,
        )
        comparison_json_path = _write_json(execution_dir / "comparison.json", comparison.to_dict())
        comparison_md_path = execution_dir / "comparison.md"
        comparison_md_path.write_text(render_comparison_markdown(comparison), encoding="utf-8")
        return BenchmarkExecutionBatch(
            execution_id=manifest.execution_id,
            execution_root=execution_dir,
            batch_status=batch_status,
            manifest=manifest,
            schedule=schedule,
            execution_state=state,
            comparison=comparison,
            runs=_completed_runs(schedule),
            manifest_path=manifest_path,
            schedule_path=schedule_path,
            execution_state_path=execution_state_path,
            comparison_json_path=comparison_json_path,
            comparison_md_path=comparison_md_path,
        )

    def _write_execution_state(self, path: Path, state: BenchmarkExecutionState) -> Path:
        payload = state.to_dict()
        economic = self._economic_state_payload()
        if economic is not None:
            payload["economic_state"] = dict(economic)
        if state.recovery_state is not None:
            payload["recovery_state"] = dict(state.recovery_state)
        return _write_json(path, payload)

    def _economic_pause_reason(self, result: BenchmarkExecutionResult) -> str | None:
        collection_metadata = getattr(result.collection, "provider_metadata", None) or {}
        provider_error = collection_metadata.get("provider_error") if isinstance(collection_metadata, Mapping) else None
        if isinstance(provider_error, Mapping) and provider_error.get("kind") == "budget_blocked":
            # Collection evidence intentionally keeps the stable error kind even
            # when provider-specific details are redacted or unavailable.
            return "ECONOMIC_BUDGET_BLOCKED"
        details = provider_error.get("details", {}) if isinstance(provider_error, Mapping) else {}
        reason = details.get("abort_reason") if isinstance(details, Mapping) else None
        if reason in {"BUDGET_BLOCKED", "ECONOMIC_STATE_PERSISTENCE_FAILED", "ECONOMIC_STATE_UNCERTAIN", "UNKNOWN_BILLABLE_USAGE"}:
            return "ECONOMIC_BUDGET_BLOCKED" if reason == "BUDGET_BLOCKED" else f"ECONOMIC_{reason}"
        guard = self._budget_guard()
        if guard is not None and guard.state.reconciliation_state != "CLEAR":
            return "ECONOMIC_STATE_UNCERTAIN"
        return None

    def run(
        self,
        catalog: BenchmarkCatalog,
        *,
        dataset_id: str,
        dataset_version: str,
        configs: Sequence[BenchmarkConfig],
        execution_root: Path,
        pd_agent_commit: str | None = None,
        knowledge_needs_by_task: Mapping[tuple[str, str], Sequence[Any]] | None = None,
        preserve_workspaces: bool = False,
    ) -> BenchmarkExecutionBatch:
        execution_root = Path(execution_root).resolve(strict=False)
        execution_root.mkdir(parents=True, exist_ok=True)
        execution_id = generate_run_id()
        execution_dir = execution_root / execution_id
        execution_dir.mkdir(parents=True, exist_ok=False)
        economic_guard = self._configure_new_economic_state(execution_id=execution_id, execution_dir=execution_dir)

        dataset = catalog.dataset_for(dataset_id, dataset_version)
        tasks = tuple(catalog.task_for(ref.task_id, ref.task_version) for ref in dataset.tasks)
        manifest = BenchmarkExecutionManifest(
            execution_id=execution_id,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            dataset_tasks=dataset.tasks,
            configs=tuple(configs),
            target_valid_repetitions=self.target_valid_repetitions,
            max_attempts_per_cell=self.max_attempts_per_cell,
            scheduling_seed=self.scheduling_seed,
            pd_agent_commit=pd_agent_commit,
            economic_schema_version=LUNA_ECONOMIC_SCHEMA_VERSION if economic_guard is not None else None,
            global_economic_ceiling_usd=str(LUNA_EXPERIMENTAL_HARD_BUDGET_USD) if economic_guard is not None else None,
            attempt_economic_ceiling_usd=str(LUNA_PER_ATTEMPT_HARD_BUDGET_USD) if economic_guard is not None else None,
        )
        manifest_path = _write_json(execution_dir / "manifest.json", manifest.to_dict())

        schedule = self.scheduler.create_initial_schedule(
            tasks,
            configs,
            target_valid_repetitions=self.target_valid_repetitions,
            max_attempts_per_cell=self.max_attempts_per_cell,
            scheduling_seed=self.scheduling_seed,
        )
        schedule_path = _write_json(execution_dir / "schedule.json", schedule.to_dict())
        execution_state = self._initial_execution_state(
            execution_id=execution_id,
            schedule=schedule,
            session_index=1,
            resume_count=0,
            batch_status=BenchmarkBatchStatus.RUNNING,
            next_pending_schedule_item=_next_pending_attempt(schedule, set()),
            logical_budget_used=0,
            attempt_reservation=self._attempt_reservation_for(configs[0]),
        )
        execution_state_path = self._write_execution_state(execution_dir / "execution_state.json", execution_state)

        return self._drive_batch(
            catalog,
            dataset=dataset,
            tasks=tasks,
            configs=tuple(configs),
            execution_dir=execution_dir,
            manifest=manifest,
            schedule=schedule,
            manifest_path=manifest_path,
            schedule_path=schedule_path,
            execution_state=execution_state,
            execution_state_path=execution_state_path,
            pd_agent_commit=pd_agent_commit,
            knowledge_needs_by_task=knowledge_needs_by_task,
            preserve_workspaces=preserve_workspaces,
            resume_mode=False,
        )

    def resume(
        self,
        catalog: BenchmarkCatalog,
        *,
        execution_dir: Path,
        pd_agent_commit: str | None = None,
        knowledge_needs_by_task: Mapping[tuple[str, str], Sequence[Any]] | None = None,
        preserve_workspaces: bool = False,
    ) -> BenchmarkExecutionBatch:
        execution_dir = Path(execution_dir).resolve(strict=True)
        # Reconstruction is a read-only gate. It must succeed before resume
        # can reach scheduler/provider code.
        self.reconstruct_execution(execution_dir)
        manifest_path = execution_dir / "manifest.json"
        schedule_path = execution_dir / "schedule.json"
        execution_state_path = execution_dir / "execution_state.json"
        if not manifest_path.exists() or not schedule_path.exists() or not execution_state_path.exists():
            raise BenchmarkExecutionResumeError(
                f"missing execution manifest/schedule/state in {execution_dir}",
                code="RESUME_INVALID_STATE",
            )

        manifest = BenchmarkExecutionManifest.from_dict(_load_json(manifest_path))
        schedule = BenchmarkSchedule.from_dict(_load_json(schedule_path))
        execution_state = BenchmarkExecutionState.from_dict(_load_json(execution_state_path))
        if execution_state.execution_id != manifest.execution_id or execution_dir.name != manifest.execution_id:
            raise BenchmarkExecutionResumeError(
                "resume execution directory does not match persisted execution identity",
                code="RESUME_INVALID_STATE",
            )
        manifest_has_openai = any(config.provider.casefold() == "openai" for config in manifest.configs)
        if manifest_has_openai and manifest.economic_schema_version is None:
            raise BenchmarkExecutionResumeError("dual-budget economic schema is required", code="RESUME_ECONOMIC_SCHEMA")
        if manifest.economic_schema_version is not None:
            if manifest.economic_schema_version != LUNA_ECONOMIC_SCHEMA_VERSION:
                raise BenchmarkExecutionResumeError("unsupported economic schema version", code="RESUME_ECONOMIC_SCHEMA")
            self._restore_economic_state(execution_dir=execution_dir, execution_id=manifest.execution_id)

        try:
            dataset = catalog.dataset_for(manifest.dataset_id, manifest.dataset_version)
            tasks = tuple(catalog.task_for(ref.task_id, ref.task_version) for ref in dataset.tasks)
        except AssertionError as exc:
            raise BenchmarkExecutionResumeError("dataset drift detected", code="RESUME_DRIFT") from exc
        self._validate_resume_state(
            catalog,
            manifest=manifest,
            schedule=schedule,
            execution_state=execution_state,
            tasks=tasks,
            pd_agent_commit=pd_agent_commit,
        )
        return self._drive_batch(
            catalog,
            dataset=dataset,
            tasks=tasks,
            configs=manifest.configs,
            execution_dir=execution_dir,
            manifest=manifest,
            schedule=schedule,
            manifest_path=manifest_path,
            schedule_path=schedule_path,
            execution_state=execution_state,
            execution_state_path=execution_state_path,
            pd_agent_commit=pd_agent_commit,
            knowledge_needs_by_task=knowledge_needs_by_task,
            preserve_workspaces=preserve_workspaces,
            resume_mode=True,
        )

    def _drive_batch(
        self,
        catalog: BenchmarkCatalog,
        *,
        dataset,
        tasks: Sequence[Any],
        configs: Sequence[BenchmarkConfig],
        execution_dir: Path,
        manifest: BenchmarkExecutionManifest,
        schedule: BenchmarkSchedule,
        manifest_path: Path,
        schedule_path: Path,
        execution_state: BenchmarkExecutionState,
        execution_state_path: Path,
        pd_agent_commit: str | None,
        knowledge_needs_by_task: Mapping[tuple[str, str], Sequence[Any]] | None,
        preserve_workspaces: bool,
        resume_mode: bool,
    ) -> BenchmarkExecutionBatch:
        completed_keys = _completed_attempt_keys(schedule)
        logical_requests_used = 0
        current_state = execution_state
        current_session_index = execution_state.session_index
        current_resume_count = execution_state.resume_count
        if resume_mode and execution_state.batch_status != BenchmarkBatchStatus.COMPLETED:
            current_session_index = execution_state.session_index + 1
            current_resume_count = execution_state.resume_count + 1
            next_pending = _next_pending_attempt(schedule, completed_keys)
            current_state = BenchmarkExecutionState(
                execution_id=execution_state.execution_id,
                batch_status=BenchmarkBatchStatus.RUNNING,
                logical_budget_cap=self.logical_session_cap,
                logical_budget_used=0,
                logical_budget_remaining=self.logical_session_cap,
                attempt_reservation=execution_state.attempt_reservation,
                pause_reason=None,
                paused_at=None,
                next_pending_schedule_item=next_pending.to_dict() if next_pending is not None else None,
                session_id=generate_run_id(),
                session_index=current_session_index,
                resume_count=current_resume_count,
                recovery_state=execution_state.recovery_state,
            )
            execution_state_path = self._write_execution_state(execution_state_path, current_state)

        if not self._has_pending_attempt(schedule, completed_keys):
            if current_state.batch_status != BenchmarkBatchStatus.COMPLETED:
                current_state = BenchmarkExecutionState(
                    execution_id=current_state.execution_id,
                    batch_status=BenchmarkBatchStatus.COMPLETED,
                    logical_budget_cap=self.logical_session_cap,
                    logical_budget_used=logical_requests_used,
                    logical_budget_remaining=max(self.logical_session_cap - logical_requests_used, 0),
                    attempt_reservation=current_state.attempt_reservation,
                    pause_reason=None,
                    paused_at=None,
                    next_pending_schedule_item=None,
                    session_id=current_state.session_id,
                    session_index=current_state.session_index,
                    resume_count=current_state.resume_count,
                    recovery_state=current_state.recovery_state,
                )
                execution_state_path = self._write_execution_state(execution_state_path, current_state)
            comparison = self._aggregate_comparison(
                _completed_runs(schedule),
                dataset=dataset,
                configs=configs,
                tasks=tasks,
            )
            comparison_json_path = _write_json(execution_dir / "comparison.json", comparison.to_dict())
            comparison_md_path = execution_dir / "comparison.md"
            comparison_md_path.write_text(render_comparison_markdown(comparison), encoding="utf-8")
            return BenchmarkExecutionBatch(
                execution_id=manifest.execution_id,
                execution_root=execution_dir,
                batch_status=BenchmarkBatchStatus.COMPLETED,
                manifest=manifest,
                schedule=schedule,
                execution_state=current_state,
                comparison=comparison,
                runs=_completed_runs(schedule),
                manifest_path=manifest_path,
                schedule_path=schedule_path,
                execution_state_path=execution_state_path,
                comparison_json_path=comparison_json_path,
                comparison_md_path=comparison_md_path,
            )

        index = 0
        recovery_checked = False
        try:
            while index < len(schedule.attempts):
                attempt = schedule.attempts[index]
                attempt_key = _attempt_key_from_attempt(attempt)
                if attempt_key in completed_keys:
                    index += 1
                    continue

                task = catalog.task_for(attempt.task_id, attempt.task_version)
                config = self._config_for(configs, attempt.config_id, attempt.config_hash)
                reservation = self._attempt_reservation_for(config)
                remaining = max(self.logical_session_cap - logical_requests_used, 0)
                if remaining < reservation:
                    pause_reason = (
                        f"logical budget remaining {remaining} is below attempt reservation {reservation}"
                    )
                    current_state = BenchmarkExecutionState(
                        execution_id=manifest.execution_id,
                        batch_status=BenchmarkBatchStatus.BUDGET_PAUSED,
                        logical_budget_cap=self.logical_session_cap,
                        logical_budget_used=logical_requests_used,
                        logical_budget_remaining=remaining,
                        attempt_reservation=reservation,
                        pause_reason=pause_reason,
                        paused_at=datetime.now(timezone.utc),
                        next_pending_schedule_item=attempt.to_dict(),
                        session_id=current_state.session_id,
                        session_index=current_state.session_index,
                        resume_count=current_state.resume_count,
                        recovery_state=current_state.recovery_state,
                    )
                    execution_state_path = self._write_execution_state(execution_state_path, current_state)
                    comparison = self._aggregate_comparison(
                        _completed_runs(schedule),
                        dataset=dataset,
                        configs=configs,
                        tasks=tasks,
                    )
                    comparison_json_path = _write_json(execution_dir / "comparison.json", comparison.to_dict())
                    comparison_md_path = execution_dir / "comparison.md"
                    comparison_md_path.write_text(render_comparison_markdown(comparison), encoding="utf-8")
                    return BenchmarkExecutionBatch(
                        execution_id=manifest.execution_id,
                        execution_root=execution_dir,
                        batch_status=BenchmarkBatchStatus.BUDGET_PAUSED,
                        manifest=manifest,
                        schedule=schedule,
                        execution_state=current_state,
                        comparison=comparison,
                        runs=_completed_runs(schedule),
                        manifest_path=manifest_path,
                        schedule_path=schedule_path,
                        execution_state_path=execution_state_path,
                        comparison_json_path=comparison_json_path,
                        comparison_md_path=comparison_md_path,
                    )

                fixture_root = catalog.fixture_paths[(attempt.task_id, attempt.task_version)]
                economic_guard = self._budget_guard()
                if economic_guard is not None:
                    economic_guard.begin_attempt(attempt.scheduled_attempt_id)
                requested_needs = (
                    knowledge_needs_by_task.get((task.task_id, task.task_version), ())
                    if knowledge_needs_by_task else None
                )
                recovery_record = (
                    self._pending_recovery_record(attempt=attempt)
                    if resume_mode and not recovery_checked
                    else None
                )
                if resume_mode and not recovery_checked:
                    recovery_checked = True
                    if self._budget_guard() is not None and self._budget_guard().state.reconciliation_state != "CLEAR" and recovery_record is None:
                        return self._paused_batch(
                            batch_status=BenchmarkBatchStatus.BUDGET_PAUSED,
                            reason="recovery evidence does not match the pending logical attempt",
                            logical_requests_used=logical_requests_used,
                            reservation=reservation,
                            attempt=attempt,
                            current_state=current_state,
                            schedule=schedule,
                            dataset=dataset,
                            configs=configs,
                            tasks=tasks,
                            manifest=manifest,
                            execution_dir=execution_dir,
                            manifest_path=manifest_path,
                            schedule_path=schedule_path,
                            execution_state_path=execution_state_path,
                        )
                recovery_state = current_state.recovery_state
                if recovery_record is not None:
                    result, recovery_state = self._recover_pending(
                        record=recovery_record,
                        task=task,
                        config=config,
                        attempt=attempt,
                        execution_dir=execution_dir,
                        pd_agent_commit=pd_agent_commit,
                        fixture_root=fixture_root,
                        knowledge_needs=requested_needs,
                        preserve_workspaces=preserve_workspaces,
                    )
                    current_state = BenchmarkExecutionState(
                        execution_id=current_state.execution_id,
                        batch_status=BenchmarkBatchStatus.RUNNING,
                        logical_budget_cap=self.logical_session_cap,
                        logical_budget_used=logical_requests_used,
                        logical_budget_remaining=max(self.logical_session_cap - logical_requests_used, 0),
                        attempt_reservation=reservation,
                        pause_reason=None,
                        paused_at=None,
                        next_pending_schedule_item=attempt.to_dict(),
                        session_id=current_state.session_id,
                        session_index=current_state.session_index,
                        resume_count=current_state.resume_count,
                        recovery_state=recovery_state,
                    )
                    execution_state_path = self._write_execution_state(execution_state_path, current_state)
                    if result is None:
                        status = (
                            BenchmarkBatchStatus.BUDGET_PAUSED
                            if recovery_state.get("status") in {RECOVERY_BUDGET_BLOCKED, RECOVERY_DISPATCH_UNCERTAIN}
                            else BenchmarkBatchStatus.BUDGET_PAUSED
                        )
                        return self._paused_batch(
                            batch_status=status,
                            reason=str(recovery_state.get("reason") or recovery_state.get("status") or "recovery blocked"),
                            logical_requests_used=logical_requests_used,
                            reservation=reservation,
                            attempt=attempt,
                            current_state=current_state,
                            schedule=schedule,
                            dataset=dataset,
                            configs=configs,
                            tasks=tasks,
                            manifest=manifest,
                            execution_dir=execution_dir,
                            manifest_path=manifest_path,
                            schedule_path=schedule_path,
                            execution_state_path=execution_state_path,
                        )
                else:
                    result = self.executor.execute(
                        task,
                        config,
                        attempt,
                        fixture_root=fixture_root,
                        execution_root=execution_dir,
                        pd_agent_commit=pd_agent_commit,
                        knowledge_needs=requested_needs,
                        preserve_workspace=preserve_workspaces,
                    )
                logical_requests_used += max(
                    self._logical_request_count_from_result(result),
                    0,
                )
                economic_pause_reason = self._economic_pause_reason(result)
                if economic_pause_reason is not None:
                    current_state = BenchmarkExecutionState(
                        execution_id=manifest.execution_id,
                        batch_status=BenchmarkBatchStatus.BUDGET_PAUSED,
                        logical_budget_cap=self.logical_session_cap,
                        logical_budget_used=logical_requests_used,
                        logical_budget_remaining=max(self.logical_session_cap - logical_requests_used, 0),
                        attempt_reservation=reservation,
                        pause_reason=economic_pause_reason,
                        paused_at=datetime.now(timezone.utc),
                        next_pending_schedule_item=attempt.to_dict(),
                        session_id=current_state.session_id,
                        session_index=current_state.session_index,
                        resume_count=current_state.resume_count,
                        recovery_state=current_state.recovery_state,
                    )
                    schedule_path = _write_json(execution_dir / "schedule.json", schedule.to_dict())
                    execution_state_path = self._write_execution_state(execution_state_path, current_state)
                    comparison = self._aggregate_comparison(
                        _completed_runs(schedule), dataset=dataset, configs=configs, tasks=tasks,
                    )
                    comparison_json_path = _write_json(execution_dir / "comparison.json", comparison.to_dict())
                    comparison_md_path = execution_dir / "comparison.md"
                    comparison_md_path.write_text(render_comparison_markdown(comparison), encoding="utf-8")
                    return BenchmarkExecutionBatch(
                        execution_id=manifest.execution_id,
                        execution_root=execution_dir,
                        batch_status=BenchmarkBatchStatus.BUDGET_PAUSED,
                        manifest=manifest,
                        schedule=schedule,
                        execution_state=current_state,
                        comparison=comparison,
                        runs=_completed_runs(schedule),
                        manifest_path=manifest_path,
                        schedule_path=schedule_path,
                        execution_state_path=execution_state_path,
                        comparison_json_path=comparison_json_path,
                        comparison_md_path=comparison_md_path,
                    )
                if self._is_rate_limit_result(result):
                    current_state = BenchmarkExecutionState(
                        execution_id=manifest.execution_id,
                        batch_status=BenchmarkBatchStatus.RATE_LIMIT_PAUSED,
                        logical_budget_cap=self.logical_session_cap,
                        logical_budget_used=logical_requests_used,
                        logical_budget_remaining=max(self.logical_session_cap - logical_requests_used, 0),
                        attempt_reservation=reservation,
                        pause_reason=result.classification.reason,
                        paused_at=datetime.now(timezone.utc),
                        next_pending_schedule_item=attempt.to_dict(),
                        session_id=current_state.session_id,
                        session_index=current_state.session_index,
                        resume_count=current_state.resume_count,
                    )
                    schedule_path = _write_json(execution_dir / "schedule.json", schedule.to_dict())
                    execution_state_path = self._write_execution_state(execution_state_path, current_state)
                    comparison = self._aggregate_comparison(
                        _completed_runs(schedule),
                        dataset=dataset,
                        configs=configs,
                        tasks=tasks,
                    )
                    comparison_json_path = _write_json(execution_dir / "comparison.json", comparison.to_dict())
                    comparison_md_path = execution_dir / "comparison.md"
                    comparison_md_path.write_text(render_comparison_markdown(comparison), encoding="utf-8")
                    return BenchmarkExecutionBatch(
                        execution_id=manifest.execution_id,
                        execution_root=execution_dir,
                        batch_status=BenchmarkBatchStatus.RATE_LIMIT_PAUSED,
                        manifest=manifest,
                        schedule=schedule,
                        execution_state=current_state,
                        comparison=comparison,
                        runs=_completed_runs(schedule),
                        manifest_path=manifest_path,
                        schedule_path=schedule_path,
                        execution_state_path=execution_state_path,
                        comparison_json_path=comparison_json_path,
                        comparison_md_path=comparison_md_path,
                    )
                if economic_guard is not None:
                    economic_guard.end_attempt()
                schedule.record_completed_run(result.benchmark_run)
                completed_keys.add(attempt_key)
                if result.benchmark_run.execution_status in {BenchmarkExecutionStatus.BLOCKED, BenchmarkExecutionStatus.INVALID}:
                    replacement = schedule.next_replacement(
                        attempt.task_id,
                        attempt.task_version,
                        attempt.config_id,
                        attempt.config_hash,
                    )
                    if replacement is not None:
                        completed_keys.discard(_attempt_key_from_attempt(replacement))
                schedule_path = _write_json(execution_dir / "schedule.json", schedule.to_dict())
                current_state = BenchmarkExecutionState(
                    execution_id=manifest.execution_id,
                    batch_status=BenchmarkBatchStatus.RUNNING,
                    logical_budget_cap=self.logical_session_cap,
                    logical_budget_used=logical_requests_used,
                    logical_budget_remaining=max(self.logical_session_cap - logical_requests_used, 0),
                    attempt_reservation=reservation,
                    pause_reason=None,
                    paused_at=None,
                    next_pending_schedule_item=(
                        _next_pending_attempt(schedule, completed_keys, start_index=index + 1)
                        or None
                    ).to_dict()
                    if _next_pending_attempt(schedule, completed_keys, start_index=index + 1) is not None
                    else None,
                    session_id=current_state.session_id,
                    session_index=current_state.session_index,
                    resume_count=current_state.resume_count,
                    recovery_state=current_state.recovery_state,
                )
                execution_state_path = self._write_execution_state(execution_state_path, current_state)
                index += 1
        except Exception:
            current_state = BenchmarkExecutionState(
                execution_id=manifest.execution_id,
                batch_status=BenchmarkBatchStatus.RUNNING,
                logical_budget_cap=self.logical_session_cap,
                logical_budget_used=logical_requests_used,
                logical_budget_remaining=max(self.logical_session_cap - logical_requests_used, 0),
                attempt_reservation=current_state.attempt_reservation,
                pause_reason=None,
                paused_at=None,
                next_pending_schedule_item=(
                    _next_pending_attempt(schedule, completed_keys, start_index=index)
                    or None
                ).to_dict()
                if _next_pending_attempt(schedule, completed_keys, start_index=index) is not None
                else None,
                session_id=current_state.session_id,
                session_index=current_state.session_index,
                resume_count=current_state.resume_count,
                recovery_state=current_state.recovery_state,
            )
            _write_json(schedule_path, schedule.to_dict())
            self._write_execution_state(execution_state_path, current_state)
            raise

        current_state = BenchmarkExecutionState(
            execution_id=manifest.execution_id,
            batch_status=BenchmarkBatchStatus.COMPLETED,
            logical_budget_cap=self.logical_session_cap,
            logical_budget_used=logical_requests_used,
            logical_budget_remaining=max(self.logical_session_cap - logical_requests_used, 0),
            attempt_reservation=current_state.attempt_reservation,
            pause_reason=None,
            paused_at=None,
            next_pending_schedule_item=None,
            session_id=current_state.session_id,
            session_index=current_state.session_index,
            resume_count=current_state.resume_count,
            recovery_state=current_state.recovery_state,
        )
        execution_state_path = self._write_execution_state(execution_state_path, current_state)
        comparison = self._aggregate_comparison(
            _completed_runs(schedule),
            dataset=dataset,
            configs=configs,
            tasks=tasks,
        )
        comparison_json_path = _write_json(execution_dir / "comparison.json", comparison.to_dict())
        comparison_md_path = execution_dir / "comparison.md"
        comparison_md_path.write_text(render_comparison_markdown(comparison), encoding="utf-8")

        return BenchmarkExecutionBatch(
            execution_id=manifest.execution_id,
            execution_root=execution_dir,
            batch_status=BenchmarkBatchStatus.COMPLETED,
            manifest=manifest,
            schedule=schedule,
            execution_state=current_state,
            comparison=comparison,
            runs=_completed_runs(schedule),
            manifest_path=manifest_path,
            schedule_path=schedule_path,
            execution_state_path=execution_state_path,
            comparison_json_path=comparison_json_path,
            comparison_md_path=comparison_md_path,
        )

    def _aggregate_comparison(
        self,
        runs: Sequence[BenchmarkRun],
        *,
        dataset,
        configs: Sequence[BenchmarkConfig],
        tasks: Sequence[Any],
    ) -> BenchmarkComparison:
        return self.aggregator.aggregate(
            runs,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            configs=tuple(configs),
            target_valid_repetitions=self.target_valid_repetitions,
            expected_cells=tuple(
                (task.task_id, task.task_version, config.config_id, config.config_hash())
                for task in tasks
                for config in configs
            ),
        )

    def _has_pending_attempt(
        self,
        schedule: BenchmarkSchedule,
        completed_keys: set[tuple[str, str, str, str, int, int]],
    ) -> bool:
        return _next_pending_attempt(schedule, completed_keys) is not None

    def _initial_execution_state(
        self,
        *,
        execution_id: str,
        schedule: BenchmarkSchedule,
        session_index: int,
        resume_count: int,
        batch_status: BenchmarkBatchStatus,
        next_pending_schedule_item: BenchmarkScheduledAttempt | None,
        logical_budget_used: int,
        attempt_reservation: int,
    ) -> BenchmarkExecutionState:
        return BenchmarkExecutionState(
            execution_id=execution_id,
            batch_status=batch_status,
            logical_budget_cap=self.logical_session_cap,
            logical_budget_used=logical_budget_used,
            logical_budget_remaining=max(self.logical_session_cap - logical_budget_used, 0),
            attempt_reservation=attempt_reservation,
            pause_reason=None,
            paused_at=None,
            next_pending_schedule_item=next_pending_schedule_item.to_dict() if next_pending_schedule_item is not None else None,
            session_id=generate_run_id(),
            session_index=session_index,
            resume_count=resume_count,
        )

    def _validate_resume_state(
        self,
        catalog: BenchmarkCatalog,
        *,
        manifest: BenchmarkExecutionManifest,
        schedule: BenchmarkSchedule,
        execution_state: BenchmarkExecutionState,
        tasks: Sequence[Any],
        pd_agent_commit: str | None,
    ) -> None:
        if manifest.dataset_id != catalog.dataset_for(manifest.dataset_id, manifest.dataset_version).dataset_id:
            raise BenchmarkExecutionResumeError("dataset id drift detected", code="RESUME_DRIFT")
        if manifest.dataset_version != catalog.dataset_for(manifest.dataset_id, manifest.dataset_version).dataset_version:
            raise BenchmarkExecutionResumeError("dataset version drift detected", code="RESUME_DRIFT")
        if manifest.target_valid_repetitions != schedule.target_valid_repetitions:
            raise BenchmarkExecutionResumeError("target_valid_repetitions drift detected", code="RESUME_DRIFT")
        if manifest.max_attempts_per_cell != schedule.max_attempts_per_cell:
            raise BenchmarkExecutionResumeError("max_attempts_per_cell drift detected", code="RESUME_DRIFT")
        if manifest.scheduling_seed != schedule.scheduling_seed:
            raise BenchmarkExecutionResumeError("scheduling_seed drift detected", code="RESUME_DRIFT")
        expected_config_hashes = {config.config_hash() for config in manifest.configs}
        if not expected_config_hashes:
            raise BenchmarkExecutionResumeError("resume manifest has no configs", code="RESUME_INVALID_STATE")
        schedule_config_hashes = {cell.config_hash for cell in schedule.cells}
        if schedule_config_hashes != expected_config_hashes:
            raise BenchmarkExecutionResumeError("config hash drift detected", code="RESUME_DRIFT")
        expected_cells = {
            (task.task_id, task.task_version, config.config_id, config.config_hash())
            for task in tasks
            for config in manifest.configs
        }
        schedule_cells = {
            (cell.task_id, cell.task_version, cell.config_id, cell.config_hash)
            for cell in schedule.cells
        }
        if schedule_cells != expected_cells:
            raise BenchmarkExecutionResumeError("canonical schedule drift detected", code="RESUME_DRIFT")
        completed_keys = _completed_attempt_keys(schedule)
        next_pending = _next_pending_attempt(schedule, completed_keys)
        state_next_pending = execution_state.next_pending_schedule_item
        if next_pending is None:
            if execution_state.batch_status not in {
                BenchmarkBatchStatus.COMPLETED,
                BenchmarkBatchStatus.BUDGET_PAUSED,
                BenchmarkBatchStatus.RATE_LIMIT_PAUSED,
                BenchmarkBatchStatus.RUNNING,
            }:
                raise BenchmarkExecutionResumeError("invalid resume state", code="RESUME_INVALID_STATE")
            return
        if state_next_pending is None:
            raise BenchmarkExecutionResumeError("missing next pending schedule item in resume state", code="RESUME_INVALID_STATE")
        if str(state_next_pending.get("scheduled_attempt_id")) != next_pending.scheduled_attempt_id:
            raise BenchmarkExecutionResumeError("next pending schedule item drift detected", code="RESUME_DRIFT")
        if execution_state.execution_id != manifest.execution_id:
            raise BenchmarkExecutionResumeError("execution identity drift detected", code="RESUME_DRIFT")
        if pd_agent_commit is not None and manifest.pd_agent_commit is not None and pd_agent_commit != manifest.pd_agent_commit:
            raise BenchmarkExecutionResumeError("pd_agent_commit drift detected", code="RESUME_DRIFT")

    def _attempt_reservation_for(self, config: BenchmarkConfig) -> int:
        limits = config.execution_limits
        if isinstance(limits, ExecutionLimits):
            return limits.max_agent_steps
        if limits is None:
            return ExecutionLimits().max_agent_steps
        if isinstance(limits, Mapping):
            return ExecutionLimits.from_dict(dict(limits)).max_agent_steps
        raise TypeError("benchmark execution_limits must be an ExecutionLimits or mapping")

    def _logical_request_count_from_result(self, result: BenchmarkExecutionResult) -> int:
        for source in (getattr(result, "collection", None), getattr(result, "run_state", None)):
            if source is None:
                continue
            value = getattr(source, "logical_provider_request_count", None)
            if isinstance(value, int):
                return value
        return 0

    def _is_rate_limit_result(self, result: BenchmarkExecutionResult) -> bool:
        return (
            getattr(result.benchmark_run, "failure_code", None) == BenchmarkFailureCode.PROVIDER_RATE_LIMIT
            or getattr(getattr(result, "classification", None), "failure_code", None)
            == BenchmarkFailureCode.PROVIDER_RATE_LIMIT
        )

    def _config_for(
        self,
        configs: Sequence[BenchmarkConfig],
        config_id: str,
        config_hash: str,
    ) -> BenchmarkConfig:
        for config in configs:
            if config.config_id == config_id and config.config_hash() == config_hash:
                return config
        raise ValueError(f"missing config for {config_id}:{config_hash}")


__all__ = [
    "BenchmarkExecutionBatch",
    "BenchmarkExecutionManifest",
    "BenchmarkExecutionRunner",
    "BenchmarkExecutionResumeError",
]
