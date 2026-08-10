"""Benchmark foundation package."""

from __future__ import annotations

from .models import (
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
    BenchmarkMetrics,
    BenchmarkSchemaError,
    BenchmarkRun,
    BenchmarkTask,
    BenchmarkTaskOutcome,
    BenchmarkTaskReference,
    BenchmarkValidationRequirements,
    SCHEMA_VERSION,
)

__all__ = [
    "BenchmarkAcceptanceSpec",
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
    "BenchmarkMetrics",
    "BenchmarkSchemaError",
    "BenchmarkRun",
    "BenchmarkTask",
    "BenchmarkTaskOutcome",
    "BenchmarkTaskReference",
    "BenchmarkValidationRequirements",
    "SCHEMA_VERSION",
]
