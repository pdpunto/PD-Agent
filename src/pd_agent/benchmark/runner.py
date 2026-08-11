"""Benchmark dataset execution runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from pd_agent.core import generate_run_id

from .aggregator import BenchmarkAggregator, render_comparison_markdown
from .executor import BenchmarkExecutionResult, BenchmarkExecutor
from .models import (
    BenchmarkComparison,
    BenchmarkConfig,
    BenchmarkRun,
    BenchmarkTaskReference,
    BenchmarkExecutionStatus,
)
from .scheduler import BenchmarkSchedule, BenchmarkScheduler
from .catalog import BenchmarkCatalog


def _write_json(path: Path, data: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


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
        }


@dataclass(frozen=True, slots=True)
class BenchmarkExecutionBatch:
    """Persisted benchmark batch output."""

    execution_id: str
    execution_root: Path
    manifest: BenchmarkExecutionManifest
    schedule: BenchmarkSchedule
    comparison: BenchmarkComparison
    runs: tuple[BenchmarkRun, ...]
    manifest_path: Path
    schedule_path: Path
    comparison_json_path: Path
    comparison_md_path: Path


@dataclass(slots=True)
class BenchmarkExecutionRunner:
    """Drive a whole benchmark dataset through schedule, executor and aggregator."""

    executor: BenchmarkExecutor
    scheduler: BenchmarkScheduler = field(default_factory=BenchmarkScheduler)
    aggregator: BenchmarkAggregator = field(default_factory=BenchmarkAggregator)
    target_valid_repetitions: int = 3
    max_attempts_per_cell: int = 5
    scheduling_seed: int | None = None

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

        runs: list[BenchmarkRun] = []
        index = 0
        try:
            while index < len(schedule.attempts):
                attempt = schedule.attempts[index]
                task = catalog.task_for(attempt.task_id, attempt.task_version)
                config = self._config_for(configs, attempt.config_id, attempt.config_hash)
                fixture_root = catalog.fixture_paths[(attempt.task_id, attempt.task_version)]
                result = self.executor.execute(
                    task,
                    config,
                    attempt,
                    fixture_root=fixture_root,
                    execution_root=execution_dir,
                    pd_agent_commit=pd_agent_commit,
                    knowledge_needs=knowledge_needs_by_task.get((task.task_id, task.task_version), ()) if knowledge_needs_by_task else None,
                    preserve_workspace=preserve_workspaces,
                )
                runs.append(result.benchmark_run)
                schedule.record_completed_run(result.benchmark_run)
                schedule_path = _write_json(execution_dir / "schedule.json", schedule.to_dict())

                if result.benchmark_run.execution_status in {BenchmarkExecutionStatus.BLOCKED, BenchmarkExecutionStatus.INVALID}:
                    replacement = schedule.next_replacement(
                        attempt.task_id,
                        attempt.task_version,
                        attempt.config_id,
                        attempt.config_hash,
                    )
                    if replacement is not None:
                        schedule_path = _write_json(execution_dir / "schedule.json", schedule.to_dict())
                index += 1
        except Exception:
            _write_json(execution_dir / "schedule.json", schedule.to_dict())
            raise

        comparison = self.aggregator.aggregate(
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
        comparison_json_path = _write_json(execution_dir / "comparison.json", comparison.to_dict())
        comparison_md_path = execution_dir / "comparison.md"
        comparison_md_path.write_text(render_comparison_markdown(comparison), encoding="utf-8")

        return BenchmarkExecutionBatch(
            execution_id=execution_id,
            execution_root=execution_dir,
            manifest=manifest,
            schedule=schedule,
            comparison=comparison,
            runs=tuple(runs),
            manifest_path=manifest_path,
            schedule_path=schedule_path,
            comparison_json_path=comparison_json_path,
            comparison_md_path=comparison_md_path,
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
]
