"""Benchmark foundation package."""

from __future__ import annotations

from .classifier import BenchmarkClassification, BenchmarkClassifier
from .collector import BenchmarkCollection, BenchmarkCollector
from .catalog import BenchmarkCatalog, BenchmarkCatalogError
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
from .workspace import (
    BenchmarkWorkspace,
    BenchmarkWorkspaceError,
    FIXTURE_IDENTITY_ALGORITHM,
    compute_fixture_identity,
    prepare_workspace,
)

__all__ = [
    "BenchmarkClassification",
    "BenchmarkClassifier",
    "BenchmarkCollection",
    "BenchmarkCollector",
    "BenchmarkCatalog",
    "BenchmarkCatalogError",
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
    "BenchmarkWorkspace",
    "BenchmarkWorkspaceError",
    "FIXTURE_IDENTITY_ALGORITHM",
    "compute_fixture_identity",
    "SCHEMA_VERSION",
    "prepare_workspace",
]
