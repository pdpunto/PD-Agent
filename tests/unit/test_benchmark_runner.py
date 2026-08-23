from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.benchmark import (
    BenchmarkBatchStatus,
    BenchmarkComparisonStatus,
    BenchmarkConfig,
    BenchmarkDataset,
    BenchmarkExecutionRunner,
    BenchmarkExecutionStatus,
    BenchmarkExecutionResumeError,
    BenchmarkFailureCode,
    BenchmarkRun,
    BenchmarkScheduler,
    BenchmarkTask,
    BenchmarkTaskReference,
    BenchmarkTaskOutcome,
    BenchmarkValidationRequirements,
)
from pd_agent.core import ExecutionLimits


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _task() -> BenchmarkTask:
    return BenchmarkTask.from_dict(
        {
            "schema_version": 1,
            "task_id": "B001",
            "task_version": "1",
            "description": "Task",
            "prompt": "Prompt",
            "fixture": {
                "schema_version": 1,
                "fixture_ref": str(Path("tests/fixtures/l11_fabric_fixture").resolve()),
                "fixture_identity": "fixture",
                "identity_algorithm": "sha256-tree-v1",
                "metadata": {},
            },
            "validation": {
                "schema_version": 1,
                "build": True,
                "artifact": True,
                "minecraft": False,
                "source_change": True,
            },
            "acceptance": {
                "schema_version": 1,
                "acceptance_type": "minecraft_harness",
                "spec": {},
                "notes": [],
            },
            "environment": {
                "schema_version": 1,
                "minecraft_version": "1.21.11",
                "loader_version": "0.19.3",
                "loom_version": "1.13.3",
                "yarn_version": "1.21.11+build.6",
                "java_version": "21",
                "fabric_api_version": "0.122.0+1.21.11",
                "extra": {},
            },
            "tags": [],
            "notes": [],
        }
    )


def _config() -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id="cfg-1",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=False,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60},
        knowledge_config={},
        target_repetition_count=1,
    )


def _run(
    *,
    run_id: str,
    task: BenchmarkTask,
    config: BenchmarkConfig,
    repetition_index: int,
    attempt_index: int,
    execution_status: BenchmarkExecutionStatus,
    task_outcome: BenchmarkTaskOutcome,
    failure_code: BenchmarkFailureCode = BenchmarkFailureCode.UNKNOWN,
) -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_run_id=run_id,
        task_id=task.task_id,
        task_version=task.task_version,
        config_id=config.config_id,
        config_hash=config.config_hash(),
        repetition_index=repetition_index,
        attempt_index=attempt_index,
        execution_status=execution_status,
        task_outcome=task_outcome,
        failure_code=failure_code,
    )


@dataclass(frozen=True)
class _Catalog:
    dataset: BenchmarkDataset
    task: BenchmarkTask
    fixture_root: Path

    @property
    def fixture_paths(self):
        return {(self.task.task_id, self.task.task_version): self.fixture_root}

    def dataset_for(self, dataset_id: str, dataset_version: str) -> BenchmarkDataset:
        assert (dataset_id, dataset_version) == (self.dataset.dataset_id, self.dataset.dataset_version)
        return self.dataset

    def task_for(self, task_id: str, task_version: str) -> BenchmarkTask:
        assert (task_id, task_version) == (self.task.task_id, self.task.task_version)
        return self.task


class _FakeExecutor:
    def __init__(
        self,
        task: BenchmarkTask,
        config: BenchmarkConfig,
        *,
        logical_request_count: int = 1,
        first_execution_status: BenchmarkExecutionStatus = BenchmarkExecutionStatus.BLOCKED,
        first_task_outcome: BenchmarkTaskOutcome = BenchmarkTaskOutcome.NOT_EVALUATED,
        later_execution_status: BenchmarkExecutionStatus = BenchmarkExecutionStatus.COMPLETED,
        later_task_outcome: BenchmarkTaskOutcome = BenchmarkTaskOutcome.PASS,
        first_failure_code: BenchmarkFailureCode = BenchmarkFailureCode.UNKNOWN,
        rate_limit_first_call: bool = False,
    ) -> None:
        self.task = task
        self.config = config
        self.logical_request_count = logical_request_count
        self.first_execution_status = first_execution_status
        self.first_task_outcome = first_task_outcome
        self.later_execution_status = later_execution_status
        self.later_task_outcome = later_task_outcome
        self.first_failure_code = first_failure_code
        self.rate_limit_first_call = rate_limit_first_call
        self.calls: list[int] = []

    def execute(self, task, config, attempt, **kwargs):
        self.calls.append(attempt.attempt_index)
        rate_limited = self.rate_limit_first_call and len(self.calls) == 1
        if rate_limited:
            status = BenchmarkExecutionStatus.BLOCKED
            outcome = BenchmarkTaskOutcome.NOT_EVALUATED
        elif attempt.attempt_index == 1:
            status = self.first_execution_status
            outcome = self.first_task_outcome
        else:
            status = self.later_execution_status
            outcome = self.later_task_outcome
        run = _run(
            run_id=f"run-{attempt.attempt_index}",
            task=task,
            config=config,
            repetition_index=attempt.repetition_index,
            attempt_index=attempt.attempt_index,
            execution_status=status,
            task_outcome=outcome,
            failure_code=self.first_failure_code if rate_limited else BenchmarkFailureCode.UNKNOWN,
        )
        return SimpleNamespace(
            benchmark_run=run,
            collection=SimpleNamespace(logical_provider_request_count=self.logical_request_count),
            classification=SimpleNamespace(
                failure_code=self.first_failure_code if rate_limited else BenchmarkFailureCode.UNKNOWN,
                reason="provider rate limit" if rate_limited else "",
            ),
        )


def test_runner_appends_replacement_attempts(tmp_path: Path) -> None:
    task = _task()
    config = _config()
    dataset = BenchmarkDataset(
        dataset_id="ds-1",
        dataset_version="1",
        tasks=(BenchmarkTaskReference(task_id=task.task_id, task_version=task.task_version),),
    )
    catalog = _Catalog(dataset=dataset, task=task, fixture_root=Path("tests/fixtures/l11_fabric_fixture").resolve())
    runner = BenchmarkExecutionRunner(
        executor=_FakeExecutor(task, config),
        scheduler=BenchmarkScheduler(),
        target_valid_repetitions=1,
        max_attempts_per_cell=2,
        scheduling_seed=1,
    )

    batch = runner.run(
        catalog,
        dataset_id="ds-1",
        dataset_version="1",
        configs=(config,),
        execution_root=tmp_path / "executions",
    )

    assert len(batch.runs) == 2
    assert [run.execution_status for run in batch.runs] == [
        BenchmarkExecutionStatus.BLOCKED,
        BenchmarkExecutionStatus.COMPLETED,
    ]
    assert batch.schedule.cells[0].attempted == 2
    assert batch.comparison.comparison_status == BenchmarkComparisonStatus.COMPLETE


def test_runner_does_not_replace_completed_agent_failure(tmp_path: Path) -> None:
    task = _task()
    config = _config()
    dataset = BenchmarkDataset(
        dataset_id="ds-1",
        dataset_version="1",
        tasks=(BenchmarkTaskReference(task_id=task.task_id, task_version=task.task_version),),
    )
    catalog = _Catalog(dataset=dataset, task=task, fixture_root=Path("tests/fixtures/l11_fabric_fixture").resolve())
    runner = BenchmarkExecutionRunner(
        executor=_FakeExecutor(
            task,
            config,
            first_execution_status=BenchmarkExecutionStatus.COMPLETED,
            first_task_outcome=BenchmarkTaskOutcome.FAIL,
            first_failure_code=BenchmarkFailureCode.AGENT_TASK_FAILURE,
        ),
        scheduler=BenchmarkScheduler(),
        target_valid_repetitions=1,
        max_attempts_per_cell=2,
        scheduling_seed=1,
    )

    batch = runner.run(
        catalog,
        dataset_id="ds-1",
        dataset_version="1",
        configs=(config,),
        execution_root=tmp_path / "executions",
    )

    assert len(batch.runs) == 1
    assert batch.runs[0].execution_status == BenchmarkExecutionStatus.COMPLETED
    assert batch.runs[0].task_outcome == BenchmarkTaskOutcome.FAIL
    assert batch.schedule.cells[0].attempted == 1


def test_runner_pauses_before_next_attempt_when_budget_is_insufficient(tmp_path: Path) -> None:
    task = _task()
    config = BenchmarkConfig(
        config_id="cfg-1",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=False,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60},
        execution_limits=ExecutionLimits(max_agent_steps=2, max_tool_calls=50),
        knowledge_config={},
        target_repetition_count=1,
    )
    dataset = BenchmarkDataset(
        dataset_id="ds-1",
        dataset_version="1",
        tasks=(BenchmarkTaskReference(task_id=task.task_id, task_version=task.task_version),),
    )
    catalog = _Catalog(dataset=dataset, task=task, fixture_root=Path("tests/fixtures/l11_fabric_fixture").resolve())
    executor = _FakeExecutor(
        task,
        config,
        logical_request_count=2,
        first_execution_status=BenchmarkExecutionStatus.COMPLETED,
        first_task_outcome=BenchmarkTaskOutcome.PASS,
    )
    runner = BenchmarkExecutionRunner(
        executor=executor,
        scheduler=BenchmarkScheduler(),
        logical_session_cap=3,
        target_valid_repetitions=2,
        max_attempts_per_cell=2,
        scheduling_seed=1,
    )

    batch = runner.run(
        catalog,
        dataset_id="ds-1",
        dataset_version="1",
        configs=(config,),
        execution_root=tmp_path / "executions",
    )

    assert batch.batch_status == BenchmarkBatchStatus.BUDGET_PAUSED
    assert batch.execution_state.batch_status == BenchmarkBatchStatus.BUDGET_PAUSED
    assert batch.execution_state.logical_budget_cap == 3
    assert batch.execution_state.logical_budget_used == 2
    assert batch.execution_state.logical_budget_remaining == 1
    assert batch.execution_state.attempt_reservation == 2
    assert batch.execution_state.next_pending_schedule_item is not None
    assert batch.execution_state.next_pending_schedule_item["attempt_index"] == 2
    assert len(batch.runs) == 1
    assert batch.comparison.comparison_status == BenchmarkComparisonStatus.INCOMPLETE
    assert len(batch.schedule.cells[0].completed_runs) == 1
    assert batch.schedule.cells[0].completed_runs[0].execution_status == BenchmarkExecutionStatus.COMPLETED


def test_runner_rate_limit_pause_preserves_pending_attempt_and_resume_reuses_it(tmp_path: Path) -> None:
    task = _task()
    config = BenchmarkConfig(
        config_id="cfg-1",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=False,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60},
        execution_limits=ExecutionLimits(max_agent_steps=2, max_tool_calls=50),
        knowledge_config={},
        target_repetition_count=1,
    )
    dataset = BenchmarkDataset(
        dataset_id="ds-1",
        dataset_version="1",
        tasks=(BenchmarkTaskReference(task_id=task.task_id, task_version=task.task_version),),
    )
    catalog = _Catalog(dataset=dataset, task=task, fixture_root=Path("tests/fixtures/l11_fabric_fixture").resolve())
    first_executor = _FakeExecutor(
        task,
        config,
        logical_request_count=1,
        first_failure_code=BenchmarkFailureCode.PROVIDER_RATE_LIMIT,
        rate_limit_first_call=True,
    )
    runner = BenchmarkExecutionRunner(
        executor=first_executor,
        scheduler=BenchmarkScheduler(),
        logical_session_cap=10,
        target_valid_repetitions=1,
        max_attempts_per_cell=2,
        scheduling_seed=1,
    )

    paused = runner.run(
        catalog,
        dataset_id="ds-1",
        dataset_version="1",
        configs=(config,),
        execution_root=tmp_path / "executions",
    )

    assert paused.batch_status == BenchmarkBatchStatus.RATE_LIMIT_PAUSED
    assert paused.execution_state.logical_budget_used == 1
    assert paused.execution_state.next_pending_schedule_item["attempt_index"] == 1
    assert paused.schedule.cells[0].completed_runs == []
    assert paused.schedule.cells[0].attempted == 1
    assert paused.comparison.comparison_status == BenchmarkComparisonStatus.INCOMPLETE

    resume_executor = _FakeExecutor(task, config, logical_request_count=1, first_execution_status=BenchmarkExecutionStatus.COMPLETED)
    resumed = BenchmarkExecutionRunner(
        executor=resume_executor,
        scheduler=BenchmarkScheduler(),
        logical_session_cap=10,
        target_valid_repetitions=1,
        max_attempts_per_cell=2,
        scheduling_seed=1,
    ).resume(catalog, execution_dir=paused.execution_root)

    assert resume_executor.calls == [1]
    assert resumed.batch_status == BenchmarkBatchStatus.COMPLETED
    assert len(resumed.schedule.cells[0].completed_runs) == 1
    assert resumed.schedule.cells[0].completed_runs[0].attempt_index == 1
    assert resumed.schedule.cells[0].attempted == 1


def test_runner_resume_continues_exact_next_pending_attempt(tmp_path: Path) -> None:
    task = _task()
    config = BenchmarkConfig(
        config_id="cfg-1",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=False,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60},
        execution_limits=ExecutionLimits(max_agent_steps=2, max_tool_calls=50),
        knowledge_config={},
        target_repetition_count=1,
    )
    dataset = BenchmarkDataset(
        dataset_id="ds-1",
        dataset_version="1",
        tasks=(BenchmarkTaskReference(task_id=task.task_id, task_version=task.task_version),),
    )
    catalog = _Catalog(dataset=dataset, task=task, fixture_root=Path("tests/fixtures/l11_fabric_fixture").resolve())
    runner = BenchmarkExecutionRunner(
        executor=_FakeExecutor(
            task,
            config,
            logical_request_count=2,
            first_execution_status=BenchmarkExecutionStatus.COMPLETED,
            first_task_outcome=BenchmarkTaskOutcome.PASS,
        ),
        scheduler=BenchmarkScheduler(),
        logical_session_cap=3,
        target_valid_repetitions=2,
        max_attempts_per_cell=2,
        scheduling_seed=1,
    )

    paused = runner.run(
        catalog,
        dataset_id="ds-1",
        dataset_version="1",
        configs=(config,),
        execution_root=tmp_path / "executions",
    )

    resume_executor = _FakeExecutor(task, config, logical_request_count=2)
    resumed_runner = BenchmarkExecutionRunner(
        executor=resume_executor,
        scheduler=BenchmarkScheduler(),
        logical_session_cap=3,
        target_valid_repetitions=2,
        max_attempts_per_cell=2,
        scheduling_seed=1,
    )
    resumed = resumed_runner.resume(catalog, execution_dir=paused.execution_root)

    assert resume_executor.calls == [2]
    assert resumed.batch_status == BenchmarkBatchStatus.COMPLETED
    assert resumed.execution_state.batch_status == BenchmarkBatchStatus.COMPLETED
    assert resumed.execution_state.resume_count == 1
    assert resumed.execution_state.session_index == 2
    assert len(resumed.runs) == 2
    assert resumed.comparison.comparison_status == BenchmarkComparisonStatus.COMPLETE
    assert resumed.schedule.cells[0].attempted == 2


def test_runner_resume_on_completed_batch_is_safe_noop(tmp_path: Path) -> None:
    task = _task()
    config = BenchmarkConfig(
        config_id="cfg-1",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=False,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60},
        execution_limits=ExecutionLimits(max_agent_steps=2, max_tool_calls=50),
        knowledge_config={},
        target_repetition_count=1,
    )
    dataset = BenchmarkDataset(
        dataset_id="ds-1",
        dataset_version="1",
        tasks=(BenchmarkTaskReference(task_id=task.task_id, task_version=task.task_version),),
    )
    catalog = _Catalog(dataset=dataset, task=task, fixture_root=Path("tests/fixtures/l11_fabric_fixture").resolve())
    runner = BenchmarkExecutionRunner(
        executor=_FakeExecutor(task, config, logical_request_count=1),
        scheduler=BenchmarkScheduler(),
        logical_session_cap=10,
        target_valid_repetitions=1,
        max_attempts_per_cell=1,
        scheduling_seed=1,
    )

    completed = runner.run(
        catalog,
        dataset_id="ds-1",
        dataset_version="1",
        configs=(config,),
        execution_root=tmp_path / "executions",
    )

    noop_executor = _FakeExecutor(task, config, logical_request_count=1)
    noop_runner = BenchmarkExecutionRunner(
        executor=noop_executor,
        scheduler=BenchmarkScheduler(),
        logical_session_cap=10,
        target_valid_repetitions=1,
        max_attempts_per_cell=1,
        scheduling_seed=1,
    )
    resumed = noop_runner.resume(catalog, execution_dir=completed.execution_root)

    assert noop_executor.calls == []
    assert resumed.batch_status == BenchmarkBatchStatus.COMPLETED
    assert resumed.execution_state.batch_status == BenchmarkBatchStatus.COMPLETED
    assert len(resumed.runs) == 1


def test_runner_resume_rejects_manifest_drift(tmp_path: Path) -> None:
    task = _task()
    config = BenchmarkConfig(
        config_id="cfg-1",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=False,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60},
        execution_limits=ExecutionLimits(max_agent_steps=2, max_tool_calls=50),
        knowledge_config={},
        target_repetition_count=1,
    )
    dataset = BenchmarkDataset(
        dataset_id="ds-1",
        dataset_version="1",
        tasks=(BenchmarkTaskReference(task_id=task.task_id, task_version=task.task_version),),
    )
    catalog = _Catalog(dataset=dataset, task=task, fixture_root=Path("tests/fixtures/l11_fabric_fixture").resolve())
    runner = BenchmarkExecutionRunner(
        executor=_FakeExecutor(task, config, logical_request_count=2),
        scheduler=BenchmarkScheduler(),
        logical_session_cap=3,
        target_valid_repetitions=2,
        max_attempts_per_cell=2,
        scheduling_seed=1,
    )

    batch = runner.run(
        catalog,
        dataset_id="ds-1",
        dataset_version="1",
        configs=(config,),
        execution_root=tmp_path / "executions",
    )
    manifest_path = batch.manifest_path
    payload = manifest_path.read_text(encoding="utf-8")
    manifest_data = json.loads(payload)
    manifest_data["dataset_id"] = "drifted"
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(BenchmarkExecutionResumeError) as excinfo:
        runner.resume(catalog, execution_dir=batch.execution_root)
    assert excinfo.value.code == "RESUME_DRIFT"
