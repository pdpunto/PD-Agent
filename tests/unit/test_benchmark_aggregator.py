from __future__ import annotations

from pd_agent.benchmark import (
    BenchmarkAggregator,
    BenchmarkComparison,
    BenchmarkComparisonStatus,
    BenchmarkConfig,
    BenchmarkExecutionStatus,
    BenchmarkMetrics,
    BenchmarkTaskOutcome,
)
from pd_agent.benchmark.aggregator import render_comparison_markdown
from pd_agent.benchmark.models import BenchmarkMetricSummary
from pd_agent.benchmark.models import BenchmarkRun


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


def _metrics(
    *,
    duration: float | None = None,
    tool_calls: float | None = None,
    builds: float | None = None,
    steps: float | None = None,
    input_tokens: float | None = None,
    output_tokens: float | None = None,
    total_tokens: float | None = None,
    cost: float | None = None,
) -> BenchmarkMetrics:
    return BenchmarkMetrics(
        duration_seconds=duration,
        tool_call_count=tool_calls,
        build_count=builds,
        agent_step_count=steps,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=cost,
    )


def _run(
    *,
    run_id: str,
    task_id: str,
    task_version: str,
    config: BenchmarkConfig,
    repetition_index: int,
    attempt_index: int,
    status: BenchmarkExecutionStatus,
    outcome: BenchmarkTaskOutcome,
    metrics: BenchmarkMetrics | None = None,
) -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_run_id=run_id,
        task_id=task_id,
        task_version=task_version,
        config_id=config.config_id,
        config_hash=config.config_hash(),
        repetition_index=repetition_index,
        attempt_index=attempt_index,
        execution_status=status,
        task_outcome=outcome,
        metrics=metrics,
    )


def test_three_of_three_pass_and_complete_comparison() -> None:
    config_a = _config("cfg-off", seed=1)
    config_b = _config("cfg-on", seed=2)
    runs = [
        _run(run_id="a-1", task_id="B001", task_version="1", config=config_a, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=10, tool_calls=2, builds=1, steps=3, total_tokens=100)),
        _run(run_id="a-2", task_id="B001", task_version="1", config=config_a, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=12, tool_calls=3, builds=1, steps=4, total_tokens=110)),
        _run(run_id="a-3", task_id="B001", task_version="1", config=config_a, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=14, tool_calls=4, builds=1, steps=5, total_tokens=120)),
        _run(run_id="b-1", task_id="B001", task_version="1", config=config_b, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=11, tool_calls=2, builds=1, steps=3, total_tokens=100)),
        _run(run_id="b-2", task_id="B001", task_version="1", config=config_b, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL, metrics=_metrics(duration=13, tool_calls=3, builds=1, steps=4, total_tokens=110)),
        _run(run_id="b-3", task_id="B001", task_version="1", config=config_b, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL, metrics=_metrics(duration=15, tool_calls=4, builds=1, steps=5, total_tokens=120)),
    ]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config_a, config_b),
        target_valid_repetitions=3,
        expected_cells=(("B001", "1", config_a.config_id, config_a.config_hash()), ("B001", "1", config_b.config_id, config_b.config_hash())),
    )

    assert comparison.comparison_status == BenchmarkComparisonStatus.COMPLETE
    assert comparison.runs_expected == 6
    assert comparison.runs_valid == 6
    assert comparison.cell_results[0].valid == 3
    assert comparison.cell_results[0].passed == 3
    assert comparison.cell_results[0].success_rate == 1.0
    assert comparison.aggregate_metadata["macro_success_rates"]["cfg-off:" + config_a.config_hash()]["macro_success_rate"] == 1.0
    assert comparison.aggregate_metadata["macro_success_rates"]["cfg-on:" + config_b.config_hash()]["macro_success_rate"] == 1 / 3
    assert comparison.aggregate_metadata["equal_macro_success_rate"] is False
    assert BenchmarkComparison.from_dict(comparison.to_dict()) == comparison


def test_cell_counts_replacement_and_success_rate() -> None:
    config = _config("cfg-off")
    runs = [
        _run(run_id="r1", task_id="B001", task_version="1", config=config, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=10, tool_calls=2, builds=1, steps=3, total_tokens=100)),
        _run(run_id="r2", task_id="B001", task_version="1", config=config, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.BLOCKED, outcome=BenchmarkTaskOutcome.NOT_EVALUATED),
        _run(run_id="r3", task_id="B001", task_version="1", config=config, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL, metrics=_metrics(duration=14, tool_calls=4, builds=1, steps=5, total_tokens=120)),
        _run(run_id="r4", task_id="B001", task_version="1", config=config, repetition_index=1, attempt_index=4, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=12, tool_calls=3, builds=1, steps=4, total_tokens=110)),
    ]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config,),
        target_valid_repetitions=3,
        expected_cells=(("B001", "1", config.config_id, config.config_hash()),),
    )
    cell = comparison.cell_results[0]

    assert cell.attempted == 4
    assert cell.valid == 3
    assert cell.passed == 2
    assert cell.failed == 1
    assert cell.blocked == 1
    assert cell.invalid == 0
    assert cell.complete
    assert cell.valid and cell.passed / cell.valid == 2 / 3


def test_blocked_and_invalid_do_not_enter_denominator() -> None:
    config = _config("cfg-off")
    runs = [
        _run(run_id="r1", task_id="B001", task_version="1", config=config, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.BLOCKED, outcome=BenchmarkTaskOutcome.NOT_EVALUATED),
        _run(run_id="r2", task_id="B001", task_version="1", config=config, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.INVALID, outcome=BenchmarkTaskOutcome.NOT_EVALUATED),
    ]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config,),
        target_valid_repetitions=3,
        expected_cells=(("B001", "1", config.config_id, config.config_hash()),),
    )
    cell = comparison.cell_results[0]

    assert cell.valid == 0
    assert cell.passed == 0
    assert cell.failed == 0
    assert cell.blocked == 1
    assert cell.invalid == 1
    assert cell.complete is False
    assert comparison.aggregate_metadata["macro_success_rate"] is None
    assert cell.metrics is None


def test_no_cells_is_incomplete() -> None:
    comparison = BenchmarkAggregator().aggregate(
        (),
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(),
        target_valid_repetitions=3,
        expected_cells=(),
    )

    assert comparison.comparison_status == BenchmarkComparisonStatus.INCOMPLETE
    assert comparison.runs_expected == 0
    assert comparison.aggregate_metadata["cell_count"] == 0


def test_missing_metrics_are_not_zero_and_cost_stays_null() -> None:
    config = _config("cfg-off")
    runs = [
        _run(run_id="r1", task_id="B001", task_version="1", config=config, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=10, tool_calls=2, builds=1, steps=3, input_tokens=100, total_tokens=100)),
        _run(run_id="r2", task_id="B001", task_version="1", config=config, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=None),
        _run(run_id="r3", task_id="B001", task_version="1", config=config, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=14, tool_calls=4, builds=1, steps=5, input_tokens=200, total_tokens=200)),
    ]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config,),
        target_valid_repetitions=3,
        expected_cells=(("B001", "1", config.config_id, config.config_hash()),),
    )
    metrics = comparison.cell_results[0].metrics

    assert metrics is not None
    assert metrics.duration_seconds is not None and metrics.duration_seconds.observations == 2
    assert metrics.duration_seconds.median == 12.0
    assert metrics.total_tokens is not None and metrics.total_tokens.observations == 2
    assert metrics.total_tokens.median == 150.0
    assert metrics.cost is None


def test_equal_task_weighting_and_incomplete_task_visible() -> None:
    config = _config("cfg-off")
    runs = [
        _run(run_id="a-1", task_id="B001", task_version="1", config=config, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="a-2", task_id="B001", task_version="1", config=config, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="a-3", task_id="B001", task_version="1", config=config, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="b-1", task_id="B002", task_version="1", config=config, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="b-2", task_id="B002", task_version="1", config=config, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="b-3", task_id="B002", task_version="1", config=config, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
    ]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config,),
        target_valid_repetitions=3,
        expected_cells=(
            ("B001", "1", config.config_id, config.config_hash()),
            ("B002", "1", config.config_id, config.config_hash()),
            ("B003", "1", config.config_id, config.config_hash()),
        ),
    )

    assert comparison.comparison_status == BenchmarkComparisonStatus.INCOMPLETE
    assert comparison.aggregate_metadata["macro_success_rates"][f"{config.config_id}:{config.config_hash()}"]["macro_success_rate"] == 0.5
    assert comparison.aggregate_metadata["macro_success_rates"][f"{config.config_id}:{config.config_hash()}"]["tasks_included"] == 2
    assert any(not cell.complete for cell in comparison.cell_results)


def test_complete_tie_is_complete_and_markdown_has_no_universal_winner() -> None:
    config_a = _config("cfg-off", seed=1)
    config_b = _config("cfg-on", seed=2)
    runs = [
        _run(run_id="a-1", task_id="B001", task_version="1", config=config_a, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="a-2", task_id="B001", task_version="1", config=config_a, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="a-3", task_id="B001", task_version="1", config=config_a, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="b-1", task_id="B001", task_version="1", config=config_b, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="b-2", task_id="B001", task_version="1", config=config_b, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="b-3", task_id="B001", task_version="1", config=config_b, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
    ]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config_a, config_b),
        target_valid_repetitions=3,
        expected_cells=(("B001", "1", config_a.config_id, config_a.config_hash()), ("B001", "1", config_b.config_id, config_b.config_hash())),
    )
    markdown = render_comparison_markdown(comparison)

    assert comparison.comparison_status == BenchmarkComparisonStatus.COMPLETE
    assert comparison.aggregate_metadata["equal_macro_success_rate"] is True
    assert "winner" not in markdown.casefold()
    assert "ganador" not in markdown.casefold()
    assert BenchmarkComparison.from_dict(comparison.to_dict()) == comparison


def test_split_result_stays_complete() -> None:
    off = _config("cfg-off")
    on = _config("cfg-on")
    runs = [
        _run(run_id="a-1", task_id="B001", task_version="1", config=off, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="a-2", task_id="B001", task_version="1", config=off, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="a-3", task_id="B001", task_version="1", config=off, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="b-1", task_id="B001", task_version="1", config=on, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="b-2", task_id="B001", task_version="1", config=on, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="b-3", task_id="B001", task_version="1", config=on, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="c-1", task_id="B002", task_version="1", config=off, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="c-2", task_id="B002", task_version="1", config=off, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="c-3", task_id="B002", task_version="1", config=off, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.FAIL),
        _run(run_id="d-1", task_id="B002", task_version="1", config=on, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="d-2", task_id="B002", task_version="1", config=on, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="d-3", task_id="B002", task_version="1", config=on, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
    ]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(off, on),
        target_valid_repetitions=3,
        expected_cells=(
            ("B001", "1", off.config_id, off.config_hash()),
            ("B001", "1", on.config_id, on.config_hash()),
            ("B002", "1", off.config_id, off.config_hash()),
            ("B002", "1", on.config_id, on.config_hash()),
        ),
    )

    assert comparison.comparison_status == BenchmarkComparisonStatus.COMPLETE
    assert comparison.aggregate_metadata["equal_macro_success_rate"] is True


def test_configs_are_separated_by_config_hash_and_raw_runs_stay_unchanged() -> None:
    config_a = _config("cfg", temperature=0.2)
    config_b = _config("cfg", temperature=0.4)
    runs = [
        _run(run_id="a-1", task_id="B001", task_version="1", config=config_a, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
        _run(run_id="b-1", task_id="B001", task_version="1", config=config_b, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS),
    ]
    before = [run.to_dict() for run in runs]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config_a, config_b),
        target_valid_repetitions=3,
        expected_cells=(("B001", "1", config_a.config_id, config_a.config_hash()), ("B001", "1", config_b.config_id, config_b.config_hash())),
    )

    assert runs[0].to_dict() == before[0]
    assert runs[1].to_dict() == before[1]
    assert len({cell.config_hash for cell in comparison.cell_results}) == 2
    assert comparison.cell_results[0].config_hash != comparison.cell_results[1].config_hash


def test_median_even_and_odd_counts_round_trip() -> None:
    config = _config("cfg-off")
    runs = [
        _run(run_id="r1", task_id="B001", task_version="1", config=config, repetition_index=0, attempt_index=1, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=10, tool_calls=2, builds=1, steps=3, input_tokens=100, total_tokens=100)),
        _run(run_id="r2", task_id="B001", task_version="1", config=config, repetition_index=1, attempt_index=2, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=20, tool_calls=4, builds=1, steps=5, input_tokens=200, total_tokens=200)),
        _run(run_id="r3", task_id="B001", task_version="1", config=config, repetition_index=2, attempt_index=3, status=BenchmarkExecutionStatus.COMPLETED, outcome=BenchmarkTaskOutcome.PASS, metrics=_metrics(duration=30, tool_calls=6, builds=1, steps=7, input_tokens=300, total_tokens=300)),
    ]

    comparison = BenchmarkAggregator().aggregate(
        runs,
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config,),
        target_valid_repetitions=3,
        expected_cells=(("B001", "1", config.config_id, config.config_hash()),),
    )
    metrics = comparison.cell_results[0].metrics

    assert metrics is not None
    assert metrics.duration_seconds == BenchmarkMetricSummary(median=20.0, minimum=10.0, maximum=30.0, observations=3)
    assert metrics.tool_call_count == BenchmarkMetricSummary(median=4.0, minimum=2.0, maximum=6.0, observations=3)
