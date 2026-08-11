from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pd_agent.benchmark import (
    BenchmarkComparisonStatus,
    BenchmarkConfig,
    BenchmarkDataset,
    BenchmarkExecutionRunner,
    BenchmarkExecutionStatus,
    BenchmarkRun,
    BenchmarkScheduler,
    BenchmarkTask,
    BenchmarkTaskReference,
    BenchmarkTaskOutcome,
    BenchmarkValidationRequirements,
)


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
    def __init__(self, task: BenchmarkTask, config: BenchmarkConfig) -> None:
        self.task = task
        self.config = config
        self.calls: list[int] = []

    def execute(self, task, config, attempt, **kwargs):
        self.calls.append(attempt.attempt_index)
        if attempt.attempt_index == 1:
            status = BenchmarkExecutionStatus.BLOCKED
            outcome = BenchmarkTaskOutcome.NOT_EVALUATED
        else:
            status = BenchmarkExecutionStatus.COMPLETED
            outcome = BenchmarkTaskOutcome.PASS
        run = _run(
            run_id=f"run-{attempt.attempt_index}",
            task=task,
            config=config,
            repetition_index=attempt.repetition_index,
            attempt_index=attempt.attempt_index,
            execution_status=status,
            task_outcome=outcome,
        )
        return type("Result", (), {"benchmark_run": run})()


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
