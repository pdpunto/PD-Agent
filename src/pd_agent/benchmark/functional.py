"""Benchmark adapter for provider-neutral post-artifact/runtime validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from pd_agent.core import ArtifactResult, ValidationResult, ValidationStage, ValidationStatus, ValidationViolation
from pd_agent.minecraft import MinecraftTestResult, MinecraftTestStatus

from .acceptance import evaluate_required_resources


def _resource_violation_code(entry: Mapping[str, Any]) -> str:
    issues = " ".join(str(item) for item in entry.get("issues", ())).casefold()
    if "missing resource" in issues:
        return "RESOURCE_MISSING"
    if "invalid json" in issues:
        return "RESOURCE_INVALID_JSON"
    if "missing json value" in issues:
        return "JSON_POINTER_MISSING"
    if "json pointer" in issues:
        return "JSON_POINTER_MISMATCH"
    return "RESOURCE_INVALID"


def _target_failure_reason(result: MinecraftTestResult) -> str:
    if result.target_failure_reason:
        return result.target_failure_reason
    if result.runtime_evidence is not None:
        value = result.runtime_evidence.metadata.get("target_failure_reason")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return result.reason


def _is_repairable_target_crash(result: MinecraftTestResult) -> bool:
    reason = _target_failure_reason(result).casefold()
    return any(
        marker in reason
        for marker in ("item id not set", "block id not set", "target initialization exception")
    )


@dataclass(slots=True)
class BenchmarkFunctionalValidator:
    """Run cheap artifact checks and one Minecraft validation per artifact."""

    acceptance_spec: Mapping[str, Any]
    runtime_check: Callable[[ArtifactResult, str], MinecraftTestResult | None] | None = None
    last_results: tuple[ValidationResult, ...] = ()
    last_minecraft_result: MinecraftTestResult | None = None

    def validate(
        self,
        project_root: Path,
        artifact: ArtifactResult,
        contract: Any,
        run_id: str,
    ) -> ValidationResult:
        del project_root, contract
        self.last_minecraft_result = None
        post_artifact = self._validate_artifact(artifact)
        if post_artifact.status is not ValidationStatus.PASS:
            self.last_results = (post_artifact,)
            return post_artifact
        if self.runtime_check is None:
            self.last_results = (post_artifact,)
            return post_artifact

        minecraft_result = self.runtime_check(artifact, run_id)
        self.last_minecraft_result = minecraft_result
        runtime = self._validate_runtime(minecraft_result)
        self.last_results = (post_artifact, runtime)
        return runtime

    def _validate_artifact(self, artifact: ArtifactResult) -> ValidationResult:
        path = Path(artifact.path) if artifact.path is not None else None
        evaluation = evaluate_required_resources(path, self.acceptance_spec)
        if evaluation.passed:
            return ValidationResult(
                stage=ValidationStage.POST_ARTIFACT,
                status=ValidationStatus.PASS,
                summary="artifact requirements passed",
            )
        violations: list[ValidationViolation] = []
        for entry in evaluation.required_resources:
            if entry.get("passed", False):
                continue
            resource_path = str(entry.get("path") or "<unknown>")
            issues = tuple(str(item) for item in entry.get("issues", ()))
            violations.append(
                ValidationViolation(
                    code=_resource_violation_code(entry),
                    requirement=resource_path,
                    observed={"category": _resource_violation_code(entry), "issues": list(issues)},
                    message="; ".join(issues) or f"artifact requirement failed for {resource_path}",
                    evidence_refs=(resource_path,),
                )
            )
        if not violations:
            violations.append(
                ValidationViolation(
                    code="RESOURCE_INVALID",
                    requirement="required artifact resources",
                    observed={"category": "invalid"},
                    message="required artifact resources did not pass",
                )
            )
        return ValidationResult(
            stage=ValidationStage.POST_ARTIFACT,
            status=ValidationStatus.REPAIRABLE_FAIL,
            summary="artifact requirements failed",
            violations=tuple(violations),
            evidence_refs=tuple(ref for violation in violations for ref in violation.evidence_refs),
        )

    def _validate_runtime(self, result: MinecraftTestResult | None) -> ValidationResult:
        if result is None:
            return ValidationResult(
                stage=ValidationStage.RUNTIME,
                status=ValidationStatus.BLOCKED,
                summary="runtime validation produced no result",
                violations=(ValidationViolation(
                    code="RUNTIME_RESULT_MISSING",
                    requirement="runtime observation result",
                    observed={"category": "missing"},
                    message="Minecraft runtime validation produced no result",
                ),),
            )
        evidence = tuple(
            str(value)
            for value in (
                result.evidence_paths.root,
                result.runtime_evidence.harness_result_path if result.runtime_evidence else None,
            )
            if value is not None
        )
        if result.status is MinecraftTestStatus.PASS:
            return ValidationResult(
                stage=ValidationStage.RUNTIME,
                status=ValidationStatus.PASS,
                summary="runtime requirements passed",
                evidence_refs=evidence,
            )
        if result.status in {MinecraftTestStatus.INFRA_ERROR, MinecraftTestStatus.TIMEOUT}:
            status = ValidationStatus.BLOCKED
        elif result.status is MinecraftTestStatus.CRASH:
            status = ValidationStatus.REPAIRABLE_FAIL if _is_repairable_target_crash(result) else ValidationStatus.BLOCKED
        else:
            status = ValidationStatus.REPAIRABLE_FAIL
        specific_reason = _target_failure_reason(result)
        requirement = "runtime observations"
        spec = self.acceptance_spec.get("observation_params") if isinstance(self.acceptance_spec, Mapping) else None
        if isinstance(spec, Mapping):
            identifier = spec.get("identifier")
            kind = spec.get("registry_kind")
            if identifier and kind:
                requirement = f"{kind} registry entry {identifier}"
        code = "REGISTRY_ENTRY_PRESENT" if status is ValidationStatus.REPAIRABLE_FAIL else "RUNTIME_INFRASTRUCTURE"
        violation = ValidationViolation(
            code=code,
            requirement=requirement,
            observed={
                "category": result.status.value,
                "reason": result.reason,
                "target_failure_reason": result.target_failure_reason,
            },
            message=specific_reason or "runtime requirement failed",
            evidence_refs=evidence,
        )
        return ValidationResult(
            stage=ValidationStage.RUNTIME,
            status=status,
            summary="runtime requirements failed" if status is ValidationStatus.REPAIRABLE_FAIL else "runtime validation blocked",
            violations=(violation,),
            evidence_refs=evidence,
        )


__all__ = ["BenchmarkFunctionalValidator"]
