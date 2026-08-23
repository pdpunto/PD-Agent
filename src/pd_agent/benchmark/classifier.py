"""Deterministic benchmark failure classifier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pd_agent.core import BuildResult, RunStatus
from pd_agent.core.errors import BuildError, LimitReachedError, ProviderError
from pd_agent.core.terminal_reasons import is_agent_terminal_failure
from pd_agent.minecraft import MinecraftTestStatus

from .collector import BenchmarkCollection
from .models import (
    BenchmarkExecutionStatus,
    BenchmarkFailureCode,
    BenchmarkFailureOrigin,
    BenchmarkTaskOutcome,
    BenchmarkValidationRequirements,
)


@dataclass(frozen=True, slots=True)
class BenchmarkClassification:
    """Classified benchmark outcome."""

    execution_status: BenchmarkExecutionStatus
    task_outcome: BenchmarkTaskOutcome
    failure_origin: BenchmarkFailureOrigin
    failure_code: BenchmarkFailureCode
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_status": self.execution_status.value,
            "task_outcome": self.task_outcome.value,
            "failure_origin": self.failure_origin.value,
            "failure_code": self.failure_code.value,
            "reason": self.reason,
        }


class BenchmarkClassifier:
    """Map structured evidence to benchmark status codes."""

    def classify(
        self,
        collection: BenchmarkCollection,
        *,
        runtime_error: Exception | None = None,
    ) -> BenchmarkClassification:
        provider_error = runtime_error if isinstance(runtime_error, ProviderError) else None
        if provider_error is not None:
            return self._classify_provider_error(provider_error)

        if isinstance(runtime_error, LimitReachedError) or self._is_limit_reached(collection):
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.BLOCKED,
                task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
                failure_origin=BenchmarkFailureOrigin.BENCHMARK_INFRA,
                failure_code=BenchmarkFailureCode.EXECUTION_LIMIT,
                reason="execution limit reached",
            )

        if isinstance(runtime_error, BuildError):
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.BLOCKED,
                task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
                failure_origin=BenchmarkFailureOrigin.BUILD_ENVIRONMENT,
                failure_code=BenchmarkFailureCode.BUILD_ENV_FAILURE,
                reason=str(runtime_error),
            )

        if self._is_agent_terminal_failure(collection):
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.COMPLETED,
                task_outcome=BenchmarkTaskOutcome.FAIL,
                failure_origin=BenchmarkFailureOrigin.AGENT,
                failure_code=BenchmarkFailureCode.AGENT_TASK_FAILURE,
                reason=f"agent terminal failure: {collection.termination_reason}",
            )

        if collection.inconsistencies:
            return self._invalid("evidence inconsistency")

        if collection.validation_requirements is None:
            requirements = BenchmarkValidationRequirements()
        else:
            requirements = collection.validation_requirements

        if requirements.build and collection.final_build is None:
            return self._invalid("required build evidence missing")
        if requirements.artifact and collection.artifact is None:
            return self._invalid("required artifact evidence missing")
        if requirements.minecraft and collection.minecraft_result is None:
            return self._invalid("required minecraft evidence missing")

        if requirements.build and collection.final_build is not None and not collection.final_build.success:
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.COMPLETED,
                task_outcome=BenchmarkTaskOutcome.FAIL,
                failure_origin=BenchmarkFailureOrigin.AGENT,
                failure_code=BenchmarkFailureCode.AGENT_BUILD_FAILURE,
                reason="final build failed",
            )

        if requirements.artifact and collection.artifact is not None and collection.artifact.classification != "VALID":
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.COMPLETED,
                task_outcome=BenchmarkTaskOutcome.FAIL,
                failure_origin=BenchmarkFailureOrigin.AGENT,
                failure_code=BenchmarkFailureCode.AGENT_BUILD_FAILURE,
                reason=f"artifact classification is {collection.artifact.classification}",
            )

        if requirements.minecraft and collection.minecraft_result is not None:
            minecraft = collection.minecraft_result
            if minecraft.status == MinecraftTestStatus.FAIL:
                return BenchmarkClassification(
                    execution_status=BenchmarkExecutionStatus.COMPLETED,
                    task_outcome=BenchmarkTaskOutcome.FAIL,
                    failure_origin=BenchmarkFailureOrigin.AGENT,
                    failure_code=BenchmarkFailureCode.AGENT_FUNCTIONAL_FAILURE,
                    reason="minecraft behavior failed",
                )
            if minecraft.status == MinecraftTestStatus.CRASH:
                runtime_metadata = (
                    minecraft.runtime_evidence.metadata
                    if minecraft.runtime_evidence is not None
                    else {}
                )
                if runtime_metadata.get("target_startup_failure") is True:
                    return BenchmarkClassification(
                        execution_status=BenchmarkExecutionStatus.COMPLETED,
                        task_outcome=BenchmarkTaskOutcome.FAIL,
                        failure_origin=BenchmarkFailureOrigin.AGENT,
                        failure_code=BenchmarkFailureCode.AGENT_FUNCTIONAL_FAILURE,
                        reason="target mod crashed during Minecraft startup",
                    )
                return BenchmarkClassification(
                    execution_status=BenchmarkExecutionStatus.BLOCKED,
                    task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
                    failure_origin=BenchmarkFailureOrigin.MINECRAFT_HARNESS,
                    failure_code=BenchmarkFailureCode.HARNESS_CRASH,
                    reason="minecraft harness crashed",
                )
            if minecraft.status == MinecraftTestStatus.TIMEOUT:
                return BenchmarkClassification(
                    execution_status=BenchmarkExecutionStatus.BLOCKED,
                    task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
                    failure_origin=BenchmarkFailureOrigin.MINECRAFT_HARNESS,
                    failure_code=BenchmarkFailureCode.HARNESS_TIMEOUT,
                    reason="minecraft harness timed out",
                )
            if minecraft.status == MinecraftTestStatus.INFRA_ERROR:
                return BenchmarkClassification(
                    execution_status=BenchmarkExecutionStatus.BLOCKED,
                    task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
                    failure_origin=BenchmarkFailureOrigin.MINECRAFT_HARNESS,
                    failure_code=BenchmarkFailureCode.HARNESS_INFRA_ERROR,
                    reason="minecraft harness infra error",
                )

        if requirements.source_change and not collection.changed_files:
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.COMPLETED,
                task_outcome=BenchmarkTaskOutcome.FAIL,
                failure_origin=BenchmarkFailureOrigin.AGENT,
                failure_code=BenchmarkFailureCode.AGENT_TASK_FAILURE,
                reason="required source change missing",
            )

        if collection.final_state == RunStatus.LIMIT_REACHED:
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.BLOCKED,
                task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
                failure_origin=BenchmarkFailureOrigin.BENCHMARK_INFRA,
                failure_code=BenchmarkFailureCode.EXECUTION_LIMIT,
                reason="run state reached limit",
            )

        if requirements.minecraft and collection.minecraft_result is not None and not collection.minecraft_result.passed:
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.COMPLETED,
                task_outcome=BenchmarkTaskOutcome.FAIL,
                failure_origin=BenchmarkFailureOrigin.AGENT,
                failure_code=BenchmarkFailureCode.AGENT_FUNCTIONAL_FAILURE,
                reason="minecraft result failed",
            )

        return BenchmarkClassification(
            execution_status=BenchmarkExecutionStatus.COMPLETED,
            task_outcome=BenchmarkTaskOutcome.PASS,
            failure_origin=BenchmarkFailureOrigin.UNKNOWN,
            failure_code=BenchmarkFailureCode.UNKNOWN,
            reason="all required evidence satisfied",
        )

    def _classify_provider_error(self, error: ProviderError) -> BenchmarkClassification:
        kind = (error.kind or "").casefold()
        if kind == "authentication":
            code = BenchmarkFailureCode.PROVIDER_AUTH
        elif kind == "rate_limit":
            code = BenchmarkFailureCode.PROVIDER_RATE_LIMIT
        elif kind == "timeout":
            code = BenchmarkFailureCode.PROVIDER_TIMEOUT
        elif kind == "unavailable":
            code = BenchmarkFailureCode.PROVIDER_UNAVAILABLE
        else:
            code = BenchmarkFailureCode.UNKNOWN

        if kind not in {"authentication", "rate_limit", "timeout", "unavailable"}:
            return BenchmarkClassification(
                execution_status=BenchmarkExecutionStatus.BLOCKED,
                task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
                failure_origin=BenchmarkFailureOrigin.PROVIDER,
                failure_code=code,
                reason=error.message,
            )

        return BenchmarkClassification(
            execution_status=BenchmarkExecutionStatus.BLOCKED,
            task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
            failure_origin=BenchmarkFailureOrigin.PROVIDER,
            failure_code=code,
            reason=error.message,
        )

    def _is_limit_reached(self, collection: BenchmarkCollection) -> bool:
        reason = (collection.termination_reason or "").casefold()
        return "limit" in reason or collection.final_state == RunStatus.LIMIT_REACHED

    def _is_agent_terminal_failure(self, collection: BenchmarkCollection) -> bool:
        return (
            collection.final_state == RunStatus.FAILED
            and is_agent_terminal_failure(collection.termination_reason)
        )

    def _invalid(self, reason: str) -> BenchmarkClassification:
        return BenchmarkClassification(
            execution_status=BenchmarkExecutionStatus.INVALID,
            task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
            failure_origin=BenchmarkFailureOrigin.BENCHMARK_INFRA,
            failure_code=BenchmarkFailureCode.BENCHMARK_EVIDENCE_INVALID,
            reason=reason,
        )
