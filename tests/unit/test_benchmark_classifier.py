from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pd_agent.benchmark import (
    BenchmarkClassification,
    BenchmarkClassifier,
    BenchmarkCollection,
    BenchmarkExecutionStatus,
    BenchmarkFailureCode,
    BenchmarkFailureOrigin,
    BenchmarkTaskOutcome,
    BenchmarkValidationRequirements,
)
from pd_agent.core import ArtifactResult, BuildResult, RunStatus
from pd_agent.core.errors import BuildError, LimitReachedError, ProviderError
from pd_agent.minecraft import MinecraftEvidencePaths, MinecraftTargetMetadata, MinecraftTestResult, MinecraftTestSpec, MinecraftTestStatus


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _collection(
    *,
    build_success: bool = True,
    build_present: bool = True,
    artifact_classification: str = "VALID",
    minecraft_status: MinecraftTestStatus | None = MinecraftTestStatus.PASS,
    changed_files: tuple[str, ...] = ("src/main/java/dev/p/A.java",),
    requirements: BenchmarkValidationRequirements | None = None,
    inconsistencies: tuple[str, ...] = (),
    final_state: RunStatus | None = None,
    termination_reason: str | None = None,
) -> BenchmarkCollection:
    run_id = "11111111-1111-4111-8111-111111111111"
    build = BuildResult(
        attempt=1,
        command_display="gradlew build",
        cwd=Path("C:/dev/project"),
        started_at=_utc("2026-08-11T10:00:10"),
        duration_seconds=2.0,
        exit_code=0 if build_success else 1,
        stdout_log="ok" if build_success else "fail",
        stderr_log="" if build_success else "boom",
    )
    artifact = ArtifactResult(
        path=Path("C:/dev/project/build/libs/mod.jar"),
        size=10,
        timestamp=_utc("2026-08-11T10:00:11"),
        classification=artifact_classification,
        metadata={},
    )
    minecraft_result = None
    if minecraft_status is not None:
        minecraft_result = MinecraftTestResult(
            run_id=run_id,
            status=minecraft_status,
            reason="ok",
            spec=MinecraftTestSpec(
                target_jar=Path("C:/dev/project/build/libs/mod.jar"),
                target_mod_id="pdagentl11",
                minecraft_version="1.21.11",
                loader_version="0.19.3",
                test_id="test",
                timeout_seconds=30,
            ),
            target=MinecraftTargetMetadata(
                path=Path("C:/dev/project/build/libs/mod.jar"),
                size_bytes=10,
                sha256="abc",
                mod_id="pdagentl11",
                minecraft_version="1.21.11",
                loader_version="0.19.3",
                java_version="21",
            ),
            evidence_paths=MinecraftEvidencePaths(root=Path("C:/dev/project/evidence/minecraft/run-1")),
        )
    return BenchmarkCollection(
        run_id=run_id,
        final_state=final_state,
        termination_reason=termination_reason,
        build_attempts=(build,),
        final_build=build if build_present else None,
        artifact=artifact if artifact_classification != "MISSING" else None,
        changed_files=changed_files,
        validation_requirements=requirements
        or BenchmarkValidationRequirements(build=True, artifact=True, minecraft=True, source_change=True),
        minecraft_result=minecraft_result,
        inconsistencies=inconsistencies,
    )


def test_classifier_success() -> None:
    classification = BenchmarkClassifier().classify(_collection())

    assert classification == BenchmarkClassification(
        execution_status=BenchmarkExecutionStatus.COMPLETED,
        task_outcome=BenchmarkTaskOutcome.PASS,
        failure_origin=BenchmarkFailureOrigin.UNKNOWN,
        failure_code=BenchmarkFailureCode.UNKNOWN,
        reason="all required evidence satisfied",
    )


@pytest.mark.parametrize(
    "error, origin, code",
    [
        (ProviderError("auth", kind="authentication"), BenchmarkFailureOrigin.PROVIDER, BenchmarkFailureCode.PROVIDER_AUTH),
        (ProviderError("rate", kind="rate_limit"), BenchmarkFailureOrigin.PROVIDER, BenchmarkFailureCode.PROVIDER_RATE_LIMIT),
        (ProviderError("timeout", kind="timeout"), BenchmarkFailureOrigin.PROVIDER, BenchmarkFailureCode.PROVIDER_TIMEOUT),
        (ProviderError("down", kind="unavailable"), BenchmarkFailureOrigin.PROVIDER, BenchmarkFailureCode.PROVIDER_UNAVAILABLE),
    ],
)
def test_classifier_provider_blocks(error: ProviderError, origin: BenchmarkFailureOrigin, code: BenchmarkFailureCode) -> None:
    classification = BenchmarkClassifier().classify(_collection(), runtime_error=error)

    assert classification.execution_status == BenchmarkExecutionStatus.BLOCKED
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == origin
    assert classification.failure_code == code


def test_classifier_unknown_provider_error_stays_unknown() -> None:
    classification = BenchmarkClassifier().classify(_collection(), runtime_error=ProviderError("boom", kind="weird"))

    assert classification.execution_status == BenchmarkExecutionStatus.BLOCKED
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == BenchmarkFailureOrigin.PROVIDER
    assert classification.failure_code == BenchmarkFailureCode.UNKNOWN


def test_classifier_build_environment_block() -> None:
    classification = BenchmarkClassifier().classify(_collection(), runtime_error=BuildError("Gradle Wrapper absent"))

    assert classification.execution_status == BenchmarkExecutionStatus.BLOCKED
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == BenchmarkFailureOrigin.BUILD_ENVIRONMENT
    assert classification.failure_code == BenchmarkFailureCode.BUILD_ENV_FAILURE


def test_classifier_execution_limit_block() -> None:
    classification = BenchmarkClassifier().classify(_collection(), runtime_error=LimitReachedError("max_agent_steps reached"))

    assert classification.execution_status == BenchmarkExecutionStatus.BLOCKED
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == BenchmarkFailureOrigin.BENCHMARK_INFRA
    assert classification.failure_code == BenchmarkFailureCode.EXECUTION_LIMIT


def test_classifier_build_failure_is_agent_fail() -> None:
    classification = BenchmarkClassifier().classify(_collection(build_success=False))

    assert classification.execution_status == BenchmarkExecutionStatus.COMPLETED
    assert classification.task_outcome == BenchmarkTaskOutcome.FAIL
    assert classification.failure_origin == BenchmarkFailureOrigin.AGENT
    assert classification.failure_code == BenchmarkFailureCode.AGENT_BUILD_FAILURE


def test_classifier_minecraft_failure_is_agent_fail() -> None:
    classification = BenchmarkClassifier().classify(_collection(minecraft_status=MinecraftTestStatus.FAIL))

    assert classification.execution_status == BenchmarkExecutionStatus.COMPLETED
    assert classification.task_outcome == BenchmarkTaskOutcome.FAIL
    assert classification.failure_origin == BenchmarkFailureOrigin.AGENT
    assert classification.failure_code == BenchmarkFailureCode.AGENT_FUNCTIONAL_FAILURE


def test_classifier_missing_required_artifact_is_not_pass() -> None:
    collection = _collection(artifact_classification="MISSING")
    classification = BenchmarkClassifier().classify(collection)

    assert classification.execution_status == BenchmarkExecutionStatus.INVALID
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == BenchmarkFailureOrigin.BENCHMARK_INFRA
    assert classification.failure_code == BenchmarkFailureCode.BENCHMARK_EVIDENCE_INVALID


def test_classifier_missing_required_build_is_not_pass() -> None:
    collection = _collection(build_present=False)
    classification = BenchmarkClassifier().classify(collection)

    assert classification.execution_status == BenchmarkExecutionStatus.INVALID
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == BenchmarkFailureOrigin.BENCHMARK_INFRA
    assert classification.failure_code == BenchmarkFailureCode.BENCHMARK_EVIDENCE_INVALID


def test_classifier_terminal_tool_rejection_is_agent_failure_before_evidence_gates() -> None:
    collection = _collection(
        build_present=False,
        artifact_classification="MISSING",
        minecraft_status=None,
        final_state=RunStatus.FAILED,
        termination_reason="tool rejected",
    )
    classification = BenchmarkClassifier().classify(collection)

    assert classification.execution_status == BenchmarkExecutionStatus.COMPLETED
    assert classification.task_outcome == BenchmarkTaskOutcome.FAIL
    assert classification.failure_origin == BenchmarkFailureOrigin.AGENT
    assert classification.failure_code == BenchmarkFailureCode.AGENT_TASK_FAILURE
    assert "tool rejected" in classification.reason


def test_classifier_missing_required_minecraft_is_not_pass() -> None:
    collection = _collection(minecraft_status=None)
    classification = BenchmarkClassifier().classify(collection)

    assert classification.execution_status == BenchmarkExecutionStatus.INVALID
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == BenchmarkFailureOrigin.BENCHMARK_INFRA
    assert classification.failure_code == BenchmarkFailureCode.BENCHMARK_EVIDENCE_INVALID


def test_classifier_task_failure_without_source_change() -> None:
    collection = _collection(changed_files=())
    classification = BenchmarkClassifier().classify(collection)

    assert classification.execution_status == BenchmarkExecutionStatus.COMPLETED
    assert classification.task_outcome == BenchmarkTaskOutcome.FAIL
    assert classification.failure_origin == BenchmarkFailureOrigin.AGENT
    assert classification.failure_code == BenchmarkFailureCode.AGENT_TASK_FAILURE


def test_classifier_inconsistency_is_invalid() -> None:
    collection = _collection(inconsistencies=("run_id_mismatch",))
    classification = BenchmarkClassifier().classify(collection)

    assert classification.execution_status == BenchmarkExecutionStatus.INVALID
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == BenchmarkFailureOrigin.BENCHMARK_INFRA
    assert classification.failure_code == BenchmarkFailureCode.BENCHMARK_EVIDENCE_INVALID


def test_classifier_other_failed_reason_is_not_generic_agent_failure() -> None:
    collection = _collection(
        build_present=False,
        artifact_classification="MISSING",
        minecraft_status=None,
        final_state=RunStatus.FAILED,
        termination_reason="no-op",
    )
    classification = BenchmarkClassifier().classify(collection)

    assert classification.execution_status == BenchmarkExecutionStatus.INVALID
    assert classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert classification.failure_origin == BenchmarkFailureOrigin.BENCHMARK_INFRA
    assert classification.failure_code == BenchmarkFailureCode.BENCHMARK_EVIDENCE_INVALID
