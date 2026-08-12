"""Benchmark foundation package."""

from __future__ import annotations

from .classifier import BenchmarkClassification, BenchmarkClassifier
from .aggregator import BenchmarkAggregator, render_comparison_markdown
from .collector import BenchmarkCollection, BenchmarkCollector
from .catalog import BenchmarkCatalog, BenchmarkCatalogError
from .executor import BenchmarkExecutionResult, BenchmarkExecutor
from .pacing import BenchmarkPacedProvider, BenchmarkRequestPacer
from .runner import BenchmarkExecutionBatch, BenchmarkExecutionManifest, BenchmarkExecutionRunner
from .scheduler import (
    BenchmarkSchedule,
    BenchmarkScheduleCell,
    BenchmarkScheduledAttempt,
    BenchmarkScheduler,
)
from .models import (
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
    SCHEMA_VERSION,
)
from .workspace import (
    BenchmarkWorkspace,
    BenchmarkWorkspaceError,
    FIXTURE_IDENTITY_ALGORITHM,
    compute_fixture_identity,
    prepare_workspace,
)

__all__ = [
    "BenchmarkClassification",
    "BenchmarkAggregator",
    "BenchmarkClassifier",
    "BenchmarkCollection",
    "BenchmarkCollector",
    "BenchmarkCatalog",
    "BenchmarkCatalogError",
    "render_comparison_markdown",
    "BenchmarkExecutionBatch",
    "BenchmarkExecutionManifest",
    "BenchmarkExecutionResult",
    "BenchmarkExecutionRunner",
    "BenchmarkExecutor",
    "BenchmarkPacedProvider",
    "BenchmarkAcceptanceSpec",
    "BenchmarkAggregateMetrics",
    "BenchmarkComparison",
    "BenchmarkComparisonCell",
    "BenchmarkComparisonStatus",
    "BenchmarkConfig",
    "BenchmarkDataset",
    "BenchmarkEnvironmentRequirements",
    "BenchmarkExecutionStatus",
    "BenchmarkFailureCode",
    "BenchmarkFailureOrigin",
    "BenchmarkFixtureReference",
    "BenchmarkMetricSummary",
    "BenchmarkMetrics",
    "BenchmarkSchemaError",
    "BenchmarkRun",
    "BenchmarkRequestPacer",
    "BenchmarkTask",
    "BenchmarkTaskOutcome",
    "BenchmarkTaskReference",
    "BenchmarkValidationRequirements",
    "BenchmarkSchedule",
    "BenchmarkScheduleCell",
    "BenchmarkScheduledAttempt",
    "BenchmarkScheduler",
    "BenchmarkWorkspace",
    "BenchmarkWorkspaceError",
    "FIXTURE_IDENTITY_ALGORITHM",
    "compute_fixture_identity",
    "SCHEMA_VERSION",
    "prepare_workspace",
]
