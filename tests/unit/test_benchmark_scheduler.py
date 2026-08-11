from __future__ import annotations

from dataclasses import dataclass

import pytest

from pd_agent.benchmark import (
    BenchmarkConfig,
    BenchmarkExecutionStatus,
    BenchmarkRun,
    BenchmarkScheduler,
    BenchmarkTaskOutcome,
)


@dataclass(frozen=True)
class _Task:
    task_id: str
    task_version: str


def _task(task_id: str) -> _Task:
    return _Task(task_id=task_id, task_version="1")


def _config(config_id: str, *, seed: int = 0, model: str = "gemini-3.1-flash-lite", temperature: float = 0.2) -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id=config_id,
        provider="gemini",
        model=model,
        brain_enabled=config_id.endswith("on"),
        model_config={"temperature": temperature, "seed": seed},
        provider_config={"timeout_seconds": 60},
        knowledge_config={"cache": "warm"},
        target_repetition_count=3,
    )


def _run(
    *,
    run_id: str,
    task: _Task,
    config: BenchmarkConfig,
    repetition_index: int,
    attempt_index: int,
    status: BenchmarkExecutionStatus,
    outcome: BenchmarkTaskOutcome,
) -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_run_id=run_id,
        task_id=task.task_id,
        task_version=task.task_version,
        config_id=config.config_id,
        config_hash=config.config_hash(),
        repetition_index=repetition_index,
        attempt_index=attempt_index,
        execution_status=status,
        task_outcome=outcome,
    )


def test_matrix_size_and_repetition_indexes() -> None:
    tasks = (_task("B001"), _task("B002"), _task("B003"))
    configs = (_config("cfg-off"), _config("cfg-on"))

    schedule = BenchmarkScheduler().create_initial_schedule(
        tasks,
        configs,
        target_valid_repetitions=3,
        max_attempts_per_cell=5,
        scheduling_seed=7,
    )

    assert schedule.cell_count == 6
    assert len(schedule.attempts) == 18
    assert {attempt.repetition_index for attempt in schedule.attempts} == {0, 1, 2}
    for cell in schedule.cells:
        assert [attempt.repetition_index for attempt in cell.planned_attempts] == [0, 1, 2]
        assert [attempt.attempt_index for attempt in cell.planned_attempts] == [1, 2, 3]


def test_same_seed_same_schedule_and_different_seed_may_change_order() -> None:
    tasks = (_task("B001"), _task("B002"), _task("B003"))
    configs = (_config("cfg-off"), _config("cfg-on"))

    scheduler = BenchmarkScheduler()
    schedule_a = scheduler.create_initial_schedule(tasks, configs, target_valid_repetitions=3, max_attempts_per_cell=5, scheduling_seed=11)
    schedule_b = scheduler.create_initial_schedule(tasks, configs, target_valid_repetitions=3, max_attempts_per_cell=5, scheduling_seed=11)
    schedule_c = scheduler.create_initial_schedule(tasks, configs, target_valid_repetitions=3, max_attempts_per_cell=5, scheduling_seed=12)

    assert schedule_a.to_dict() == schedule_b.to_dict()
    assert schedule_a.to_dict() != schedule_c.to_dict()


def test_no_all_off_then_all_on_and_fairness_reasonable() -> None:
    tasks = (_task("B001"), _task("B002"), _task("B003"))
    configs = (_config("cfg-off"), _config("cfg-on"))

    schedule = BenchmarkScheduler().create_initial_schedule(
        tasks,
        configs,
        target_valid_repetitions=3,
        max_attempts_per_cell=5,
        scheduling_seed=21,
    )

    first_six = [attempt.config_id for attempt in schedule.attempts[:6]]
    assert len(set(first_six)) == 2
    assert first_six != sorted(first_six)


def test_blocked_and_invalid_generate_replacement() -> None:
    task = _task("B001")
    config = _config("cfg-off")
    schedule = BenchmarkScheduler().create_initial_schedule(
        (task,),
        (config,),
        target_valid_repetitions=3,
        max_attempts_per_cell=5,
        scheduling_seed=1,
    )

    schedule.record_completed_run(
        _run(
            run_id="run-1",
            task=task,
            config=config,
            repetition_index=0,
            attempt_index=1,
            status=BenchmarkExecutionStatus.BLOCKED,
            outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
        )
    )
    assert schedule.needs_replacement(task.task_id, task.task_version, config.config_id, config.config_hash())
    replacement = schedule.next_replacement(task.task_id, task.task_version, config.config_id, config.config_hash())
    assert replacement is not None
    assert replacement.repetition_index == 0
    assert replacement.attempt_index == 4

    schedule.record_completed_run(
        _run(
            run_id="run-2",
            task=task,
            config=config,
            repetition_index=1,
            attempt_index=2,
            status=BenchmarkExecutionStatus.INVALID,
            outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
        )
    )
    assert schedule.needs_replacement(task.task_id, task.task_version, config.config_id, config.config_hash())


def test_fail_does_not_generate_replacement_and_pass_completes() -> None:
    task = _task("B001")
    config = _config("cfg-off")
    schedule = BenchmarkScheduler().create_initial_schedule((task,), (config,), target_valid_repetitions=3, max_attempts_per_cell=5, scheduling_seed=2)

    schedule.record_completed_run(_run(run_id="run-1", task=task, config=config, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS))
    schedule.record_completed_run(_run(run_id="run-2", task=task, config=config, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL))
    schedule.record_completed_run(_run(run_id="run-3", task=task, config=config, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS))

    assert schedule.complete(task.task_id, task.task_version, config.config_id, config.config_hash())
    assert not schedule.needs_replacement(task.task_id, task.task_version, config.config_id, config.config_hash())
    assert schedule.next_replacement(task.task_id, task.task_version, config.config_id, config.config_hash()) is None


def test_max_attempts_respected_and_previous_attempt_preserved() -> None:
    task = _task("B001")
    config = _config("cfg-off")
    schedule = BenchmarkScheduler().create_initial_schedule((task,), (config,), target_valid_repetitions=3, max_attempts_per_cell=4, scheduling_seed=3)

    snapshot = schedule.attempts[0].to_dict()
    schedule.record_completed_run(_run(run_id="run-1", task=task, config=config, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.BLOCKED, outcome=BenchmarkTaskOutcome.NOT_EVALUATED))
    schedule.record_completed_run(_run(run_id="run-2", task=task, config=config, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.BLOCKED, outcome=BenchmarkTaskOutcome.NOT_EVALUATED))
    schedule.record_completed_run(_run(run_id="run-3", task=task, config=config, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.BLOCKED, outcome=BenchmarkTaskOutcome.NOT_EVALUATED))

    replacement = schedule.next_replacement(task.task_id, task.task_version, config.config_id, config.config_hash())
    assert replacement is not None
    assert schedule.attempts[0].to_dict() == snapshot
    assert schedule.exhausted(task.task_id, task.task_version, config.config_id, config.config_hash())


def test_config_hash_stays_associated_and_distinct_configs_split_cells() -> None:
    tasks = (_task("B001"),)
    config_a = _config("cfg", seed=1, temperature=0.2)
    config_b = _config("cfg", seed=2, temperature=0.4)

    schedule = BenchmarkScheduler().create_initial_schedule(tasks, (config_a, config_b), target_valid_repetitions=3, max_attempts_per_cell=5, scheduling_seed=4)

    hashes = {attempt.config_hash for attempt in schedule.attempts}
    assert hashes == {config_a.config_hash(), config_b.config_hash()}
    assert schedule.cell_count == 2
    assert schedule.cell("B001", "1", "cfg", config_a.config_hash()).config_hash == config_a.config_hash()
    assert schedule.cell("B001", "1", "cfg", config_b.config_hash()).config_hash == config_b.config_hash()
