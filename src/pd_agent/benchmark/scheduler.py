"""Deterministic benchmark scheduling with replacement policy."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .models import BenchmarkConfig, BenchmarkExecutionStatus, BenchmarkRun, BenchmarkTaskOutcome, SCHEMA_VERSION


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _stable_int(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _key(task_id: str, task_version: str, config_id: str, config_hash: str) -> tuple[str, str, str, str]:
    return (task_id, task_version, config_id, config_hash)


@dataclass(slots=True, kw_only=True)
class BenchmarkScheduledAttempt:
    """One planned benchmark attempt."""

    schema_version: int = SCHEMA_VERSION
    scheduled_attempt_id: str
    task_id: str
    task_version: str
    config_id: str
    config_hash: str
    repetition_index: int
    attempt_index: int
    scheduling_position: int
    replacement: bool = False
    replacement_for_attempt_index: int | None = None

    def __post_init__(self) -> None:
        self.scheduled_attempt_id = _required_text(self.scheduled_attempt_id, field_name="scheduled_attempt_id")
        self.task_id = _required_text(self.task_id, field_name="task_id")
        self.task_version = _required_text(self.task_version, field_name="task_version")
        self.config_id = _required_text(self.config_id, field_name="config_id")
        self.config_hash = _required_text(self.config_hash, field_name="config_hash")
        self.repetition_index = int(self.repetition_index)
        self.attempt_index = int(self.attempt_index)
        self.scheduling_position = int(self.scheduling_position)
        if self.replacement_for_attempt_index is not None:
            self.replacement_for_attempt_index = int(self.replacement_for_attempt_index)

    @property
    def cell_key(self) -> tuple[str, str, str, str]:
        return _key(self.task_id, self.task_version, self.config_id, self.config_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scheduled_attempt_id": self.scheduled_attempt_id,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "config_id": self.config_id,
            "config_hash": self.config_hash,
            "repetition_index": self.repetition_index,
            "attempt_index": self.attempt_index,
            "scheduling_position": self.scheduling_position,
            "replacement": self.replacement,
            "replacement_for_attempt_index": self.replacement_for_attempt_index,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkScheduledAttempt":
        if int(data.get("schema_version", SCHEMA_VERSION)) != SCHEMA_VERSION:
            raise ValueError("unsupported BenchmarkScheduledAttempt schema_version")
        return cls(
            scheduled_attempt_id=str(data["scheduled_attempt_id"]),
            task_id=str(data["task_id"]),
            task_version=str(data["task_version"]),
            config_id=str(data["config_id"]),
            config_hash=str(data["config_hash"]),
            repetition_index=int(data["repetition_index"]),
            attempt_index=int(data["attempt_index"]),
            scheduling_position=int(data["scheduling_position"]),
            replacement=bool(data.get("replacement", False)),
            replacement_for_attempt_index=data.get("replacement_for_attempt_index"),
        )


@dataclass(slots=True)
class BenchmarkScheduleCell:
    """State for one task/config cell."""

    schema_version: int = SCHEMA_VERSION
    task_id: str = ""
    task_version: str = ""
    config_id: str = ""
    config_hash: str = ""
    target_valid_repetitions: int = 1
    max_attempts_per_cell: int = 1
    planned_attempts: list[BenchmarkScheduledAttempt] = field(default_factory=list)
    completed_runs: list[BenchmarkRun] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.task_id = _required_text(self.task_id, field_name="task_id")
        self.task_version = _required_text(self.task_version, field_name="task_version")
        self.config_id = _required_text(self.config_id, field_name="config_id")
        self.config_hash = _required_text(self.config_hash, field_name="config_hash")
        self.target_valid_repetitions = int(self.target_valid_repetitions)
        self.max_attempts_per_cell = int(self.max_attempts_per_cell)
        if self.target_valid_repetitions <= 0:
            raise ValueError("target_valid_repetitions must be positive")
        if self.max_attempts_per_cell < self.target_valid_repetitions:
            raise ValueError("max_attempts_per_cell must be >= target_valid_repetitions")

    @property
    def key(self) -> tuple[str, str, str, str]:
        return _key(self.task_id, self.task_version, self.config_id, self.config_hash)

    @property
    def attempted(self) -> int:
        return len(self.planned_attempts)

    @property
    def valid(self) -> int:
        return sum(
            1
            for run in self.completed_runs
            if run.execution_status == BenchmarkExecutionStatus.COMPLETED
            and run.task_outcome in {BenchmarkTaskOutcome.PASS, BenchmarkTaskOutcome.FAIL}
        )

    @property
    def passed(self) -> int:
        return sum(1 for run in self.completed_runs if run.execution_status == BenchmarkExecutionStatus.COMPLETED and run.task_outcome == BenchmarkTaskOutcome.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for run in self.completed_runs if run.execution_status == BenchmarkExecutionStatus.COMPLETED and run.task_outcome == BenchmarkTaskOutcome.FAIL)

    @property
    def blocked(self) -> int:
        return sum(1 for run in self.completed_runs if run.execution_status == BenchmarkExecutionStatus.BLOCKED)

    @property
    def invalid(self) -> int:
        return sum(1 for run in self.completed_runs if run.execution_status == BenchmarkExecutionStatus.INVALID)

    @property
    def complete(self) -> bool:
        return self.valid >= self.target_valid_repetitions

    @property
    def exhausted(self) -> bool:
        return not self.complete and self.attempted >= self.max_attempts_per_cell

    def unresolved_repetitions(self) -> tuple[int, ...]:
        resolved = {
            run.repetition_index
            for run in self.completed_runs
            if run.execution_status == BenchmarkExecutionStatus.COMPLETED
        }
        ordered = [index for index in range(self.target_valid_repetitions) if index not in resolved]
        return tuple(ordered)

    def needs_replacement(self) -> bool:
        return bool(self.unresolved_repetitions()) and not self.complete and not self.exhausted

    def record_completed_run(self, run: BenchmarkRun) -> None:
        if _key(run.task_id, run.task_version, run.config_id, run.config_hash) != self.key:
            raise ValueError("run does not belong to this schedule cell")
        if run.repetition_index < 0:
            raise ValueError("repetition_index must be non-negative")
        self.completed_runs.append(run)

    def next_replacement(self) -> BenchmarkScheduledAttempt | None:
        if not self.needs_replacement():
            return None
        repetition_index = self.unresolved_repetitions()[0]
        attempt_index = len(self.planned_attempts) + 1
        scheduling_position = self.planned_attempts[-1].scheduling_position + 1 if self.planned_attempts else 1
        replacement_for = max(
            (
                attempt.attempt_index
                for attempt in self.planned_attempts
                if attempt.repetition_index == repetition_index
            ),
            default=attempt_index - 1,
        )
        attempt = BenchmarkScheduledAttempt(
            scheduled_attempt_id=f"{self.task_id}:{self.task_version}:{self.config_id}:{self.config_hash}:{repetition_index}:{attempt_index}",
            task_id=self.task_id,
            task_version=self.task_version,
            config_id=self.config_id,
            config_hash=self.config_hash,
            repetition_index=repetition_index,
            attempt_index=attempt_index,
            scheduling_position=scheduling_position,
            replacement=True,
            replacement_for_attempt_index=replacement_for,
        )
        self.planned_attempts.append(attempt)
        return attempt

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "config_id": self.config_id,
            "config_hash": self.config_hash,
            "target_valid_repetitions": self.target_valid_repetitions,
            "max_attempts_per_cell": self.max_attempts_per_cell,
            "planned_attempts": [attempt.to_dict() for attempt in self.planned_attempts],
            "completed_runs": [run.to_dict() for run in self.completed_runs],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkScheduleCell":
        if int(data.get("schema_version", SCHEMA_VERSION)) != SCHEMA_VERSION:
            raise ValueError("unsupported BenchmarkScheduleCell schema_version")
        return cls(
            task_id=str(data["task_id"]),
            task_version=str(data["task_version"]),
            config_id=str(data["config_id"]),
            config_hash=str(data.get("config_hash", data["config_id"])),
            target_valid_repetitions=int(data.get("target_valid_repetitions", 1)),
            max_attempts_per_cell=int(data.get("max_attempts_per_cell", 1)),
            planned_attempts=[BenchmarkScheduledAttempt.from_dict(dict(item)) for item in data.get("planned_attempts", [])],
            completed_runs=[BenchmarkRun.from_dict(dict(item)) for item in data.get("completed_runs", [])],
        )


@dataclass(slots=True)
class BenchmarkSchedule:
    """Serializable schedule plus live replacement state."""

    schema_version: int = SCHEMA_VERSION
    target_valid_repetitions: int = 1
    max_attempts_per_cell: int = 1
    scheduling_seed: int | None = None
    attempts: list[BenchmarkScheduledAttempt] = field(default_factory=list)
    cells: list[BenchmarkScheduleCell] = field(default_factory=list)
    _cell_index: dict[tuple[str, str, str, str], BenchmarkScheduleCell] = field(
        init=False,
        repr=False,
        compare=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        self.target_valid_repetitions = int(self.target_valid_repetitions)
        self.max_attempts_per_cell = int(self.max_attempts_per_cell)
        if self.target_valid_repetitions <= 0:
            raise ValueError("target_valid_repetitions must be positive")
        if self.max_attempts_per_cell < self.target_valid_repetitions:
            raise ValueError("max_attempts_per_cell must be >= target_valid_repetitions")
        self.cells = list(self.cells)
        self.attempts = list(self.attempts)
        self._cell_index: dict[tuple[str, str, str, str], BenchmarkScheduleCell] = {cell.key: cell for cell in self.cells}

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    def cell(self, task_id: str, task_version: str, config_id: str, config_hash: str) -> BenchmarkScheduleCell:
        return self._cell_index[_key(task_id, task_version, config_id, config_hash)]

    def record_completed_run(self, run: BenchmarkRun) -> None:
        self.cell(run.task_id, run.task_version, run.config_id, run.config_hash).record_completed_run(run)

    def needs_replacement(self, task_id: str, task_version: str, config_id: str, config_hash: str) -> bool:
        return self.cell(task_id, task_version, config_id, config_hash).needs_replacement()

    def next_replacement(self, task_id: str, task_version: str, config_id: str, config_hash: str) -> BenchmarkScheduledAttempt | None:
        attempt = self.cell(task_id, task_version, config_id, config_hash).next_replacement()
        if attempt is not None:
            self.attempts.append(attempt)
        return attempt

    def exhausted(self, task_id: str, task_version: str, config_id: str, config_hash: str) -> bool:
        return self.cell(task_id, task_version, config_id, config_hash).exhausted

    def complete(self, task_id: str, task_version: str, config_id: str, config_hash: str) -> bool:
        return self.cell(task_id, task_version, config_id, config_hash).complete

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target_valid_repetitions": self.target_valid_repetitions,
            "max_attempts_per_cell": self.max_attempts_per_cell,
            "scheduling_seed": self.scheduling_seed,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "cells": [cell.to_dict() for cell in self.cells],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkSchedule":
        if int(data.get("schema_version", SCHEMA_VERSION)) != SCHEMA_VERSION:
            raise ValueError("unsupported BenchmarkSchedule schema_version")
        return cls(
            target_valid_repetitions=int(data.get("target_valid_repetitions", 1)),
            max_attempts_per_cell=int(data.get("max_attempts_per_cell", 1)),
            scheduling_seed=data.get("scheduling_seed"),
            attempts=[BenchmarkScheduledAttempt.from_dict(dict(item)) for item in data.get("attempts", [])],
            cells=[BenchmarkScheduleCell.from_dict(dict(item)) for item in data.get("cells", [])],
        )


class BenchmarkScheduler:
    """Create reproducible interleaved benchmark schedules."""

    def create_initial_schedule(
        self,
        tasks: Sequence[Any],
        configs: Sequence[BenchmarkConfig],
        *,
        target_valid_repetitions: int = 3,
        max_attempts_per_cell: int = 5,
        scheduling_seed: int | None = None,
    ) -> BenchmarkSchedule:
        if target_valid_repetitions <= 0:
            raise ValueError("target_valid_repetitions must be positive")
        if max_attempts_per_cell < target_valid_repetitions:
            raise ValueError("max_attempts_per_cell must be >= target_valid_repetitions")

        tasks = tuple(tasks)
        configs = tuple(configs)
        cells: dict[tuple[str, str, str, str], BenchmarkScheduleCell] = {}
        attempts: list[BenchmarkScheduledAttempt] = []
        scheduling_position = 0

        for repetition_index in range(target_valid_repetitions):
            ordered_tasks = self._ordered_tasks(tasks, scheduling_seed, repetition_index)
            for task in ordered_tasks:
                ordered_configs = self._ordered_configs(configs, task, scheduling_seed, repetition_index)
                for config in ordered_configs:
                    scheduling_position += 1
                    config_hash = config.config_hash()
                    cell_key = _key(task.task_id, task.task_version, config.config_id, config_hash)
                    cell = cells.get(cell_key)
                    if cell is None:
                        cell = BenchmarkScheduleCell(
                            task_id=task.task_id,
                            task_version=task.task_version,
                            config_id=config.config_id,
                            config_hash=config_hash,
                            target_valid_repetitions=target_valid_repetitions,
                            max_attempts_per_cell=max_attempts_per_cell,
                        )
                        cells[cell_key] = cell
                    attempt = BenchmarkScheduledAttempt(
                        scheduled_attempt_id=f"{task.task_id}:{task.task_version}:{config.config_id}:{config_hash}:{repetition_index}:{repetition_index + 1}",
                        task_id=task.task_id,
                        task_version=task.task_version,
                        config_id=config.config_id,
                        config_hash=config_hash,
                        repetition_index=repetition_index,
                        attempt_index=repetition_index + 1,
                        scheduling_position=scheduling_position,
                        replacement=False,
                    )
                    attempts.append(attempt)
                    cell.planned_attempts.append(attempt)

        return BenchmarkSchedule(
            target_valid_repetitions=target_valid_repetitions,
            max_attempts_per_cell=max_attempts_per_cell,
            scheduling_seed=scheduling_seed,
            attempts=attempts,
            cells=list(cells.values()),
        )

    def _ordered_tasks(self, tasks: Sequence[Any], scheduling_seed: int | None, repetition_index: int) -> tuple[Any, ...]:
        seed = scheduling_seed if scheduling_seed is not None else 0
        return tuple(
            sorted(
                tasks,
                key=lambda task: _stable_int(seed, repetition_index, getattr(task, "task_id", repr(task)), getattr(task, "task_version", "")),
            )
        )

    def _ordered_configs(
        self,
        configs: Sequence[BenchmarkConfig],
        task: Any,
        scheduling_seed: int | None,
        repetition_index: int,
    ) -> tuple[BenchmarkConfig, ...]:
        seed = scheduling_seed if scheduling_seed is not None else 0
        ordered = sorted(
            configs,
            key=lambda config: _stable_int(seed, getattr(task, "task_id", repr(task)), getattr(task, "task_version", ""), config.config_id, config.config_hash()),
        )
        if _stable_int(seed, getattr(task, "task_id", repr(task)), repetition_index) % 2:
            ordered = list(reversed(ordered))
        return tuple(ordered)


__all__ = [
    "BenchmarkSchedule",
    "BenchmarkScheduleCell",
    "BenchmarkScheduledAttempt",
    "BenchmarkScheduler",
]
