from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from pd_agent.benchmark import (
    BenchmarkAggregateMetrics,
    BenchmarkAcceptanceSpec,
    BenchmarkComparison,
    BenchmarkComparisonCell,
    BenchmarkComparisonStatus,
    BenchmarkConfig,
    BenchmarkDataset,
    BenchmarkEnvironmentRequirements,
    BenchmarkExecutionStatus,
    BenchmarkFailureCode,
    BenchmarkFailureOrigin,
    BenchmarkFixtureReference,
    BenchmarkMetricSummary,
    BenchmarkMetrics,
    BenchmarkSchemaError,
    BenchmarkRun,
    BenchmarkTask,
    BenchmarkTaskOutcome,
    BenchmarkTaskReference,
    BenchmarkValidationRequirements,
)
from pd_agent.core import ExecutionLimits


def _task_reference(task_id: str = "B001", task_version: str = "1") -> BenchmarkTaskReference:
    return BenchmarkTaskReference(task_id=task_id, task_version=task_version)


def _fixture_reference() -> BenchmarkFixtureReference:
    return BenchmarkFixtureReference(
        fixture_ref="tests/fixtures/l11_fabric_fixture",
        fixture_identity="sha256:fixture-123",
        identity_algorithm="sha256",
        metadata={"source": "fixture"},
    )


def _validation() -> BenchmarkValidationRequirements:
    return BenchmarkValidationRequirements(build=True, artifact=True, minecraft=True, source_change=True)


def _acceptance() -> BenchmarkAcceptanceSpec:
    return BenchmarkAcceptanceSpec(
        acceptance_type="minecraft_harness",
        spec={"expected": "registry lookup"},
        notes=("baseline",),
    )


def _environment() -> BenchmarkEnvironmentRequirements:
    return BenchmarkEnvironmentRequirements(
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        loom_version="1.13.3",
        yarn_version="1.21.11+build.6",
        java_version="21",
        fabric_api_version="0.122.0+1.21.11",
        extra={"platform": "fabric"},
    )


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="B001",
        task_version="1",
        description="Registry lookup",
        prompt="Use registry lookup for diamond block.",
        fixture=_fixture_reference(),
        validation=_validation(),
        acceptance=_acceptance(),
        environment=_environment(),
        tags=("fabric", "brain", "version-sensitive"),
        notes=("primary",),
    )


def _config(
    *,
    config_id: str = "cfg-a",
    brain_enabled: bool = True,
    provider: str = "gemini",
    model: str = "gemini-3.1-flash-lite",
    model_config: dict[str, object] | None = None,
    provider_config: dict[str, object] | None = None,
    knowledge_config: dict[str, object] | None = None,
    target_repetition_count: int = 3,
) -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id=config_id,
        provider=provider,
        model=model,
        brain_enabled=brain_enabled,
        model_config=model_config or {"temperature": 0.2, "top_p": 0.95},
        provider_config=provider_config or {"timeout_seconds": 60},
        execution_limits=ExecutionLimits(max_agent_steps=25, max_tool_calls=50),
        knowledge_config=knowledge_config or {"cache": "warm"},
        target_repetition_count=target_repetition_count,
        notes=("stable",),
    )


def test_round_trip_main_models() -> None:
    dataset = BenchmarkDataset(
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        tasks=(_task_reference(),),
        description="Benchmark dataset",
        tags=("fabric", "brain"),
    )
    task = _task()
    config = _config()
    metrics = BenchmarkMetrics(
        duration_seconds=12.5,
        tool_call_count=3,
        build_count=2,
        agent_step_count=4,
        logical_provider_request_count=5,
        input_tokens=11,
        cached_input_tokens=2,
        output_tokens=7,
        reasoning_or_thinking_tokens=3,
        tool_use_prompt_tokens=4,
        total_tokens=18,
        cost=0.25,
        extra={"provider": "gemini"},
    )
    aggregate_metrics = BenchmarkAggregateMetrics(
        duration_seconds=BenchmarkMetricSummary(median=12.5, minimum=12.5, maximum=12.5, observations=1),
        tool_call_count=BenchmarkMetricSummary(median=3.0, minimum=3.0, maximum=3.0, observations=1),
        build_count=BenchmarkMetricSummary(median=2.0, minimum=2.0, maximum=2.0, observations=1),
        agent_step_count=BenchmarkMetricSummary(median=4.0, minimum=4.0, maximum=4.0, observations=1),
        logical_provider_request_count=BenchmarkMetricSummary(median=5.0, minimum=5.0, maximum=5.0, observations=1),
        input_tokens=BenchmarkMetricSummary(median=11.0, minimum=11.0, maximum=11.0, observations=1),
        cached_input_tokens=BenchmarkMetricSummary(median=2.0, minimum=2.0, maximum=2.0, observations=1),
        output_tokens=BenchmarkMetricSummary(median=7.0, minimum=7.0, maximum=7.0, observations=1),
        reasoning_or_thinking_tokens=BenchmarkMetricSummary(median=3.0, minimum=3.0, maximum=3.0, observations=1),
        tool_use_prompt_tokens=BenchmarkMetricSummary(median=4.0, minimum=4.0, maximum=4.0, observations=1),
        total_tokens=BenchmarkMetricSummary(median=18.0, minimum=18.0, maximum=18.0, observations=1),
        cost=BenchmarkMetricSummary(median=0.25, minimum=0.25, maximum=0.25, observations=1),
        extra={"observations": 1},
    )
    run = BenchmarkRun(
        benchmark_run_id="run-001",
        task_id=task.task_id,
        task_version=task.task_version,
        config_id=config.config_id,
        config_hash=config.config_hash(),
        repetition_index=0,
        attempt_index=1,
        pd_agent_commit="18ba103a978c8199cf944fac1cb25091471e415d",
        fixture_hash="sha256:fixture-123",
        environment_snapshot={"minecraft_version": "1.21.11", "java_version": "21"},
        underlying_run_id="underlying-001",
        started_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 10, 12, 1, tzinfo=timezone.utc),
        duration_seconds=60.0,
        execution_status=BenchmarkExecutionStatus.COMPLETED,
        task_outcome=BenchmarkTaskOutcome.PASS,
        failure_origin=BenchmarkFailureOrigin.AGENT,
        failure_code=BenchmarkFailureCode.AGENT_TASK_FAILURE,
        metrics=metrics,
        evidence_refs=("evidence/run.json", "evidence/build.log"),
        notes=("ok",),
    )
    cell = BenchmarkComparisonCell(
        task_id=task.task_id,
        task_version=task.task_version,
        config_id=config.config_id,
        config_hash=config.config_hash(),
        attempted=3,
        valid=3,
        passed=2,
        failed=1,
        blocked=0,
        invalid=0,
        target_valid=3,
        complete=True,
        metrics=aggregate_metrics,
        notes=("cell",),
    )
    comparison = BenchmarkComparison(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        configs=(config,),
        runs_expected=3,
        runs_valid=3,
        runs_blocked=0,
        runs_invalid=0,
        cell_results=(cell,),
        aggregate_metadata={"macro_success_rate": 1.0},
        comparison_status=BenchmarkComparisonStatus.COMPLETE,
        notes=("summary",),
    )

    assert BenchmarkDataset.from_dict(dataset.to_dict()) == dataset
    assert BenchmarkTaskReference.from_dict(_task_reference().to_dict()) == _task_reference()
    assert BenchmarkFixtureReference.from_dict(_fixture_reference().to_dict()) == _fixture_reference()
    assert BenchmarkValidationRequirements.from_dict(_validation().to_dict()) == _validation()
    assert BenchmarkAcceptanceSpec.from_dict(_acceptance().to_dict()) == _acceptance()
    assert BenchmarkEnvironmentRequirements.from_dict(_environment().to_dict()) == _environment()
    assert BenchmarkTask.from_dict(task.to_dict()) == task
    assert BenchmarkConfig.from_dict(config.to_dict()) == config
    assert BenchmarkMetrics.from_dict(metrics.to_dict()) == metrics
    assert BenchmarkMetricSummary.from_dict(aggregate_metrics.duration_seconds.to_dict()) == aggregate_metrics.duration_seconds
    assert BenchmarkAggregateMetrics.from_dict(aggregate_metrics.to_dict()) == aggregate_metrics
    assert BenchmarkRun.from_dict(run.to_dict()) == run
    assert BenchmarkComparisonCell.from_dict(cell.to_dict()) == cell
    assert BenchmarkComparison.from_dict(comparison.to_dict()) == comparison


def test_enums_cover_expected_values() -> None:
    assert BenchmarkExecutionStatus.COMPLETED.value == "COMPLETED"
    assert BenchmarkExecutionStatus.BLOCKED.value == "BLOCKED"
    assert BenchmarkExecutionStatus.INVALID.value == "INVALID"
    assert BenchmarkTaskOutcome.PASS.value == "PASS"
    assert BenchmarkTaskOutcome.FAIL.value == "FAIL"
    assert BenchmarkTaskOutcome.NOT_EVALUATED.value == "NOT_EVALUATED"
    assert BenchmarkFailureOrigin.UNKNOWN.value == "UNKNOWN"
    assert BenchmarkFailureCode.BENCHMARK_CONTAMINATION.value == "BENCHMARK_CONTAMINATION"
    assert BenchmarkComparisonStatus.INCOMPLETE.value == "INCOMPLETE"


@pytest.mark.parametrize(
    "model_name, factory",
    [
        ("BenchmarkDataset", lambda: BenchmarkDataset.from_dict({**_dataset_payload(), "schema_version": 2})),
        ("BenchmarkTask", lambda: BenchmarkTask.from_dict({**_task().to_dict(), "schema_version": 2})),
        ("BenchmarkConfig", lambda: BenchmarkConfig.from_dict({**_config().to_dict(), "schema_version": 2})),
        ("BenchmarkRun", lambda: BenchmarkRun.from_dict({**_run_payload(), "schema_version": 2})),
        ("BenchmarkComparison", lambda: BenchmarkComparison.from_dict({**_comparison_payload(), "schema_version": 2})),
    ],
)
def test_schema_rejection(model_name: str, factory) -> None:
    with pytest.raises(BenchmarkSchemaError):
        factory()


def test_config_hash_is_stable_and_order_insensitive() -> None:
    config_a = _config(
        model_config={"top_p": 0.95, "temperature": 0.2},
        provider_config={"timeout_seconds": 60, "retries": 2},
        knowledge_config={"cache": "warm", "offline": True},
    )
    config_b = _config(
        model_config={"temperature": 0.2, "top_p": 0.95},
        provider_config={"retries": 2, "timeout_seconds": 60},
        knowledge_config={"offline": True, "cache": "warm"},
    )

    assert config_a.config_hash() == config_b.config_hash()


def test_config_hash_preserves_public_token_counts() -> None:
    config = _config(
        model_config={"max_tokens": 4096, "max_output_tokens": 1024, "input_tokens": 12},
        provider_config={"input_token_limit": 2048, "retry_after_seconds": 5},
        knowledge_config={"output_tokens": 128, "offline": True},
    )

    payload = config.to_dict()

    assert payload["model_config"]["max_tokens"] == 4096
    assert payload["model_config"]["max_output_tokens"] == 1024
    assert payload["model_config"]["input_tokens"] == 12
    assert payload["provider_config"]["input_token_limit"] == 2048
    assert payload["knowledge_config"]["output_tokens"] == 128


def test_config_hash_changes_for_semantic_differences() -> None:
    off = _config(config_id="cfg-off", brain_enabled=False)
    on = _config(config_id="cfg-on", brain_enabled=True)
    provider_changed = _config(provider="openai")

    assert off.config_hash() != on.config_hash()
    assert off.config_hash() != provider_changed.config_hash()


def test_config_hash_changes_when_public_token_limits_change() -> None:
    low = _config(model_config={"max_output_tokens": 1024, "temperature": 0.2})
    high = _config(model_config={"max_output_tokens": 2048, "temperature": 0.2})

    assert low.config_hash() != high.config_hash()


def test_config_hash_ignores_secrets_and_runtime_noise() -> None:
    public = _config(
        model_config={"temperature": 0.2, "nested": {"visible": "ok"}},
        provider_config={"timeout_seconds": 60},
        knowledge_config={"offline": True, "nested": {"visible": "ok"}},
    )
    noisy = _config(
        config_id="different-config-id",
        model_config={"temperature": 0.2, "api_key": "secret-123", "nested": {"access_token": "secret-456", "visible": "ok"}},
        provider_config={"timeout_seconds": 60, "secret": "hidden"},
        knowledge_config={"offline": True, "access_token": "secret-789", "nested": {"visible": "ok", "client_secret": "secret-789"}},
    )

    assert noisy.to_dict()["model_config"]["nested"] == {"visible": "ok"}
    assert "secret-123" not in json.dumps(noisy.to_dict(), ensure_ascii=False)
    assert "secret-456" not in json.dumps(noisy.to_dict(), ensure_ascii=False)
    assert "secret-789" not in json.dumps(noisy.to_dict(), ensure_ascii=False)
    assert noisy.config_hash() == public.config_hash()


def test_config_hash_is_unchanged_by_runtime_identifiers() -> None:
    base = _config(config_id="cfg-base")
    changed_identity = _config(config_id="cfg-other", target_repetition_count=3)

    assert base.config_hash() == changed_identity.config_hash()


def test_optional_values_survive_round_trip() -> None:
    config = BenchmarkConfig(
        config_id="cfg-none",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=False,
        model_config={},
        provider_config={},
        execution_limits=None,
        knowledge_config={},
        target_repetition_count=1,
        notes=(),
    )
    run = BenchmarkRun(
        benchmark_run_id="run-none",
        task_id="B002",
        task_version="1",
        config_id=config.config_id,
        config_hash=config.config_hash(),
        repetition_index=1,
        execution_status=BenchmarkExecutionStatus.BLOCKED,
        task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
        failure_origin=BenchmarkFailureOrigin.PROVIDER,
        failure_code=BenchmarkFailureCode.PROVIDER_TIMEOUT,
        environment_snapshot={},
        evidence_refs=(),
    )
    comparison = BenchmarkComparison(
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config,),
        runs_expected=0,
        runs_valid=0,
        runs_blocked=0,
        runs_invalid=0,
        cell_results=(),
        aggregate_metadata={},
        comparison_status=BenchmarkComparisonStatus.INCONCLUSIVE,
        notes=(),
    )

    assert BenchmarkConfig.from_dict(config.to_dict()).execution_limits is None
    assert BenchmarkRun.from_dict(run.to_dict()).started_at is None
    assert BenchmarkRun.from_dict(run.to_dict()).finished_at is None
    assert BenchmarkRun.from_dict(run.to_dict()).metrics is None
    assert BenchmarkComparison.from_dict(comparison.to_dict()).cell_results == ()


def test_comparison_and_run_do_not_depend_on_runtime_objects() -> None:
    task = _task()
    config = _config()
    run = BenchmarkRun(
        benchmark_run_id="run-runtime-free",
        task_id=task.task_id,
        task_version=task.task_version,
        config_id=config.config_id,
        config_hash=config.config_hash(),
        repetition_index=2,
        pd_agent_commit="18ba103a978c8199cf944fac1cb25091471e415d",
        fixture_hash="sha256:fixture-123",
        environment_snapshot={"python_version": "3.13.13", "java_version": "21"},
        underlying_run_id="underlying-runtime-free",
        execution_status=BenchmarkExecutionStatus.COMPLETED,
        task_outcome=BenchmarkTaskOutcome.FAIL,
        failure_origin=BenchmarkFailureOrigin.AGENT,
        failure_code=BenchmarkFailureCode.AGENT_BUILD_FAILURE,
        evidence_refs=("run.json", "final-report.json"),
    )
    comparison = BenchmarkComparison(
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config,),
        runs_expected=3,
        runs_valid=2,
        runs_blocked=1,
        runs_invalid=0,
        cell_results=(
        BenchmarkComparisonCell(
                task_id=task.task_id,
                task_version=task.task_version,
                config_id=config.config_id,
                config_hash=config.config_hash(),
                attempted=3,
                valid=2,
                passed=1,
                failed=1,
                blocked=1,
                invalid=0,
                target_valid=3,
                complete=False,
            ),
        ),
        aggregate_metadata={"status": "synthetic"},
        comparison_status=BenchmarkComparisonStatus.INCOMPLETE,
    )

    encoded = json.dumps({"run": run.to_dict(), "comparison": comparison.to_dict()}, ensure_ascii=False)
    decoded = json.loads(encoded)

    assert decoded["run"]["underlying_run_id"] == "underlying-runtime-free"
    assert decoded["comparison"]["comparison_status"] == "INCOMPLETE"
    assert decoded["comparison"]["cell_results"][0]["attempted"] == 3


def _dataset_payload() -> dict[str, object]:
    return BenchmarkDataset(
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        tasks=(_task_reference(),),
        description="Benchmark dataset",
        tags=("fabric", "brain"),
    ).to_dict()


def _run_payload() -> dict[str, object]:
    config = _config()
    run = BenchmarkRun(
        benchmark_run_id="run-001",
        task_id="B001",
        task_version="1",
        config_id=config.config_id,
        config_hash=config.config_hash(),
        repetition_index=0,
        execution_status=BenchmarkExecutionStatus.COMPLETED,
        task_outcome=BenchmarkTaskOutcome.PASS,
        failure_origin=BenchmarkFailureOrigin.UNKNOWN,
        failure_code=BenchmarkFailureCode.UNKNOWN,
        environment_snapshot={},
    )
    return run.to_dict()


def _comparison_payload() -> dict[str, object]:
    config = _config()
    comparison = BenchmarkComparison(
        dataset_id="pd-agent-fabric-brain",
        dataset_version="0.4.1",
        configs=(config,),
        runs_expected=3,
        runs_valid=3,
        runs_blocked=0,
        runs_invalid=0,
        cell_results=(),
        aggregate_metadata={},
        comparison_status=BenchmarkComparisonStatus.COMPLETE,
    )
    return comparison.to_dict()
