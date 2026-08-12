"""Benchmark aggregation and comparison rendering."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from .models import (
    BenchmarkAggregateMetrics,
    BenchmarkComparison,
    BenchmarkComparisonCell,
    BenchmarkComparisonStatus,
    BenchmarkConfig,
    BenchmarkMetricSummary,
    BenchmarkMetrics,
    BenchmarkRun,
    BenchmarkTaskOutcome,
    BenchmarkExecutionStatus,
)


def _cell_key(run: BenchmarkRun) -> tuple[str, str, str, str]:
    return (run.task_id, run.task_version, run.config_id, run.config_hash)


def _metric_summary(values: Sequence[float | int | None]) -> BenchmarkMetricSummary | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return BenchmarkMetricSummary(
        median=float(median(filtered)),
        minimum=min(filtered),
        maximum=max(filtered),
        observations=len(filtered),
    )


def _metric_values(runs: Sequence[BenchmarkRun], attr: str) -> list[float | int | None]:
    values: list[float | int | None] = []
    for run in runs:
        metrics = run.metrics
        if metrics is None:
            values.append(None)
            continue
        values.append(getattr(metrics, attr))
    return values


def _valid_runs(runs: Sequence[BenchmarkRun]) -> list[BenchmarkRun]:
    return [
        run
        for run in runs
        if run.execution_status == BenchmarkExecutionStatus.COMPLETED
        and run.task_outcome in {BenchmarkTaskOutcome.PASS, BenchmarkTaskOutcome.FAIL}
    ]


def _success_rate(passed: int, valid: int) -> float | None:
    if valid <= 0:
        return None
    return passed / valid


def _format_summary(summary: BenchmarkMetricSummary | None) -> str:
    if summary is None:
        return "-"
    return f"{summary.median:g} [{summary.minimum:g}..{summary.maximum:g}] n={summary.observations}"


@dataclass(slots=True)
class _CellAggregate:
    task_id: str
    task_version: str
    config_id: str
    config_hash: str
    runs: list[BenchmarkRun]
    target_valid: int

    def to_cell(self) -> BenchmarkComparisonCell:
        valid_runs = _valid_runs(self.runs)
        passed = sum(1 for run in valid_runs if run.task_outcome == BenchmarkTaskOutcome.PASS)
        failed = sum(1 for run in valid_runs if run.task_outcome == BenchmarkTaskOutcome.FAIL)
        blocked = sum(1 for run in self.runs if run.execution_status == BenchmarkExecutionStatus.BLOCKED)
        invalid = sum(1 for run in self.runs if run.execution_status == BenchmarkExecutionStatus.INVALID)
        valid = passed + failed
        metrics = _aggregate_metrics(valid_runs)
        return BenchmarkComparisonCell(
            task_id=self.task_id,
            task_version=self.task_version,
            config_id=self.config_id,
            config_hash=self.config_hash,
            attempted=len(self.runs),
            valid=valid,
            passed=passed,
            failed=failed,
            blocked=blocked,
            invalid=invalid,
            target_valid=self.target_valid,
            complete=valid >= self.target_valid,
            metrics=metrics,
        )


def _aggregate_metrics(runs: Sequence[BenchmarkRun]) -> BenchmarkAggregateMetrics | None:
    if not runs:
        return None
    duration = _metric_summary([run.metrics.duration_seconds if run.metrics is not None else None for run in runs])
    tool_calls = _metric_summary([run.metrics.tool_call_count if run.metrics is not None else None for run in runs])
    builds = _metric_summary([run.metrics.build_count if run.metrics is not None else None for run in runs])
    steps = _metric_summary([run.metrics.agent_step_count if run.metrics is not None else None for run in runs])
    logical_requests = _metric_summary([run.metrics.logical_provider_request_count if run.metrics is not None else None for run in runs])
    input_tokens = _metric_summary([run.metrics.input_tokens if run.metrics is not None else None for run in runs])
    output_tokens = _metric_summary([run.metrics.output_tokens if run.metrics is not None else None for run in runs])
    total_tokens = _metric_summary([run.metrics.total_tokens if run.metrics is not None else None for run in runs])
    cost = _metric_summary([run.metrics.cost if run.metrics is not None else None for run in runs])
    if all(summary is None for summary in (duration, tool_calls, builds, steps, logical_requests, input_tokens, output_tokens, total_tokens, cost)):
        return None
    return BenchmarkAggregateMetrics(
        duration_seconds=duration,
        tool_call_count=tool_calls,
        build_count=builds,
        agent_step_count=steps,
        logical_provider_request_count=logical_requests,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=cost,
        extra={"observations": len(runs)},
    )


class BenchmarkAggregator:
    """Aggregate benchmark runs into comparison outputs."""

    def aggregate(
        self,
        runs: Sequence[BenchmarkRun],
        *,
        dataset_id: str,
        dataset_version: str,
        configs: Sequence[BenchmarkConfig] = (),
        target_valid_repetitions: int = 3,
        expected_cells: Sequence[tuple[str, str, str, str]] | None = None,
    ) -> BenchmarkComparison:
        grouped: dict[tuple[str, str, str, str], _CellAggregate] = {}
        for run in runs:
            key = _cell_key(run)
            bucket = grouped.get(key)
            if bucket is None:
                bucket = _CellAggregate(
                    task_id=run.task_id,
                    task_version=run.task_version,
                    config_id=run.config_id,
                    config_hash=run.config_hash,
                    runs=[],
                    target_valid=target_valid_repetitions,
                )
                grouped[key] = bucket
            bucket.runs.append(run)

        if expected_cells is not None:
            for task_id, task_version, config_id, config_hash in expected_cells:
                key = (task_id, task_version, config_id, config_hash)
                grouped.setdefault(
                    key,
                    _CellAggregate(
                        task_id=task_id,
                        task_version=task_version,
                        config_id=config_id,
                        config_hash=config_hash,
                        runs=[],
                        target_valid=target_valid_repetitions,
                    ),
                )

        cells = tuple(
            sorted(
                (bucket.to_cell() for bucket in grouped.values()),
                key=lambda cell: (cell.task_id, cell.task_version, cell.config_id, cell.config_hash),
            )
        )
        configs = tuple(configs)
        metadata = self._aggregate_metadata(cells, configs)
        status = self._comparison_status(cells, configs)
        runs_valid = sum(cell.valid for cell in cells)
        runs_blocked = sum(cell.blocked for cell in cells)
        runs_invalid = sum(cell.invalid for cell in cells)
        runs_expected = len(cells) * target_valid_repetitions
        return BenchmarkComparison(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            configs=configs,
            runs_expected=runs_expected,
            runs_valid=runs_valid,
            runs_blocked=runs_blocked,
            runs_invalid=runs_invalid,
            cell_results=cells,
            aggregate_metadata=metadata,
            comparison_status=status,
        )

    def _aggregate_metadata(self, cells: Sequence[BenchmarkComparisonCell], configs: Sequence[BenchmarkConfig]) -> dict[str, Any]:
        complete_cells = [cell for cell in cells if cell.complete]
        incomplete_cells = [cell for cell in cells if not cell.complete]
        task_ids = tuple(dict.fromkeys((cell.task_id for cell in cells)))
        config_keys = tuple(dict.fromkeys((cell.config_id, cell.config_hash) for cell in cells))
        macro_by_config: dict[str, dict[str, Any]] = {}
        for config_id, config_hash in config_keys:
            task_rates: list[float] = []
            task_names: list[str] = []
            for cell in complete_cells:
                if cell.config_id == config_id and cell.config_hash == config_hash and cell.valid > 0:
                    rate = _success_rate(cell.passed, cell.valid)
                    if rate is not None:
                        task_rates.append(rate)
                        task_names.append(cell.task_id)
            macro_by_config[f"{config_id}:{config_hash}"] = {
                "macro_success_rate": (sum(task_rates) / len(task_rates)) if task_rates else None,
                "tasks_included": len(task_rates),
                "task_ids": task_names,
            }
        all_macro_rates = [entry["macro_success_rate"] for entry in macro_by_config.values() if entry["macro_success_rate"] is not None]
        non_none_rates = list(all_macro_rates)
        equal_macro_success_rate = None
        if len(non_none_rates) >= 2:
            baseline = non_none_rates[0]
            equal_macro_success_rate = all(abs(rate - baseline) <= 1e-12 for rate in non_none_rates[1:])
        return {
            "cell_count": len(cells),
            "complete_cell_count": len(complete_cells),
            "incomplete_cell_count": len(incomplete_cells),
            "task_count": len(task_ids),
            "config_count": len(config_keys),
            "macro_success_rates": macro_by_config,
            "macro_success_rate": (sum(all_macro_rates) / len(all_macro_rates)) if all_macro_rates else None,
            "equal_macro_success_rate": equal_macro_success_rate,
        }

    def _comparison_status(self, cells: Sequence[BenchmarkComparisonCell], configs: Sequence[BenchmarkConfig]) -> BenchmarkComparisonStatus:
        if not cells:
            return BenchmarkComparisonStatus.INCOMPLETE
        if any(not cell.complete for cell in cells):
            return BenchmarkComparisonStatus.INCOMPLETE
        return BenchmarkComparisonStatus.COMPLETE

    def render_markdown(self, comparison: BenchmarkComparison) -> str:
        lines: list[str] = []
        lines.append("# Benchmark Comparison")
        lines.append("")
        lines.append(f"- Dataset: `{comparison.dataset_id}` / `{comparison.dataset_version}`")
        lines.append(f"- Status: `{comparison.comparison_status.value}`")
        lines.append(f"- Runs expected: `{comparison.runs_expected}`")
        lines.append(f"- Runs valid: `{comparison.runs_valid}`")
        lines.append(f"- Runs blocked: `{comparison.runs_blocked}`")
        lines.append(f"- Runs invalid: `{comparison.runs_invalid}`")
        if comparison.aggregate_metadata:
            lines.append(f"- Equal macro success rate: `{comparison.aggregate_metadata.get('equal_macro_success_rate')}`")
        lines.append("")
        if comparison.configs:
            lines.append("## Configs")
            for config in comparison.configs:
                lines.append(f"- `{config.config_id}` `{config.config_hash()}` provider=`{config.provider}` model=`{config.model}` brain=`{config.brain_enabled}`")
            lines.append("")
        lines.append("## Cells")
        lines.append("| Task | Config | Attempted | Valid | Pass | Fail | Blocked | Invalid | Target | Complete | Success rate | Duration | Tool calls | Builds | Agent steps | Logical provider requests | Tokens | Cost |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for cell in comparison.cell_results:
            metrics = cell.metrics
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{cell.task_id}` `{cell.task_version}`",
                        f"`{cell.config_id}` `{cell.config_hash}`",
                        str(cell.attempted),
                        str(cell.valid),
                        str(cell.passed),
                        str(cell.failed),
                        str(cell.blocked),
                        str(cell.invalid),
                        str(cell.target_valid),
                        "yes" if cell.complete else "no",
                        "-" if cell.valid == 0 else f"{cell.passed / cell.valid:.3f}",
                        _format_summary(metrics.duration_seconds) if metrics is not None else "-",
                        _format_summary(metrics.tool_call_count) if metrics is not None else "-",
                        _format_summary(metrics.build_count) if metrics is not None else "-",
                        _format_summary(metrics.agent_step_count) if metrics is not None else "-",
                        _format_summary(metrics.logical_provider_request_count) if metrics is not None else "-",
                        _format_summary(metrics.total_tokens) if metrics is not None else "-",
                        _format_summary(metrics.cost) if metrics is not None else "-",
                    ]
                )
                + " |"
            )
        lines.append("")
        lines.append("## Macro summary")
        macro = comparison.aggregate_metadata.get("macro_success_rates", {}) if comparison.aggregate_metadata else {}
        if macro:
            for config_key, entry in macro.items():
                rate = entry.get("macro_success_rate")
                task_count = entry.get("tasks_included")
                lines.append(f"- `{config_key}` macro success rate: `{rate}` across `{task_count}` tasks")
        else:
            lines.append("- No macro summary available")
        lines.append(f"- Incomplete cells: `{comparison.aggregate_metadata.get('incomplete_cell_count', 0) if comparison.aggregate_metadata else 0}`")
        return "\n".join(lines)


def render_comparison_markdown(comparison: BenchmarkComparison) -> str:
    return BenchmarkAggregator().render_markdown(comparison)


__all__ = [
    "BenchmarkAggregator",
    "render_comparison_markdown",
]
