"""Provider-neutral runtime validation orchestration for v0.8 I7."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4

from pd_agent.core import (
    ArtifactIdentity,
    FailureFact,
    FailureFactStatus,
    FabricTaskContract,
    RunState,
    RuntimeAttemptIdentity,
    TaskProgressLedger,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    ValidationViolation,
    validation_contract_revision,
)

from .contracts import (
    MinecraftObservationStatus,
    MinecraftTestResult,
    MinecraftTestSpec,
    MinecraftTestStatus,
    ObservationRequest,
    ObservationResult,
)


class RuntimeOrchestrationStatus(StrEnum):
    REUSED = "REUSED"
    NOT_REQUIRED = "NOT_REQUIRED"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    VALIDATED = "VALIDATED"


@dataclass(frozen=True, slots=True)
class RuntimeValidationSpec:
    validation_requirement_id: str
    validation_revision: str
    observations: tuple[ObservationRequest, ...]
    observation_requirements: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        if not self.validation_requirement_id.strip() or not self.validation_revision.strip():
            raise ValueError("runtime validation identity must not be empty")
        ids = tuple(item.observation_id for item in self.observations)
        if len(set(ids)) != len(ids):
            raise ValueError("observation IDs must be unique")
        mapping = {str(key): tuple(str(value) for value in values) for key, values in self.observation_requirements.items()}
        if set(mapping) != set(ids):
            raise ValueError("every observation must have an explicit requirement mapping")
        known = {value for values in mapping.values() for value in values}
        if any(not values for values in mapping.values()) or any(not value.strip() for value in known):
            raise ValueError("observation requirement mapping must not be empty")
        object.__setattr__(self, "observation_requirements", mapping)

    def to_dict(self) -> dict[str, Any]:
        return {"validation_requirement_id": self.validation_requirement_id, "validation_revision": self.validation_revision, "observations": [item.to_dict() for item in self.observations], "observation_requirements": {key: list(value) for key, value in sorted(self.observation_requirements.items())}}


@dataclass(frozen=True, slots=True)
class RuntimeValidationOutcome:
    status: RuntimeOrchestrationStatus
    validation_result: ValidationResult | None = None
    runtime_identity: RuntimeAttemptIdentity | None = None
    runtime_result: Any | None = None
    observations: tuple[ObservationResult, ...] = ()
    failure_fact: FailureFact | None = None
    reused: bool = False


class MinecraftRunner(Protocol):
    def run(self, spec: MinecraftTestSpec, **kwargs: Any) -> Any:
        """Execute an existing controlled Minecraft harness."""


def runtime_spec_from_requirement(requirement: Any) -> RuntimeValidationSpec:
    """Adapt one Fabric validation requirement without interpreting free text."""

    raw = requirement.to_dict() if hasattr(requirement, "to_dict") else dict(requirement)
    spec = raw.get("spec", {})
    if not isinstance(spec, Mapping):
        raise ValueError("runtime validation spec must be an object")
    raw_observations = spec.get("observations", spec.get("observation_requests"))
    if raw_observations is None:
        raw_observations = (spec,)
    if not isinstance(raw_observations, (list, tuple)) or not raw_observations:
        raise ValueError("runtime spec must declare observations")
    observations: list[ObservationRequest] = []
    mapping: dict[str, tuple[str, ...]] = {}
    default_requirements = tuple(str(item) for item in raw.get("requirement_ids", ()))
    for item in raw_observations:
        if not isinstance(item, Mapping):
            raise ValueError("runtime observation must be an object")
        payload = dict(item)
        requirement_ids = tuple(str(value) for value in payload.pop("requirement_ids", spec.get("requirement_ids", default_requirements)))
        if not requirement_ids:
            raise ValueError("runtime observation requires explicit requirement_ids")
        observation = ObservationRequest.from_dict(payload)
        observations.append(observation)
        mapping[observation.observation_id] = requirement_ids
    return RuntimeValidationSpec(validation_requirement_id=str(raw["validation_requirement_id"]), validation_revision=validation_contract_revision(raw), observations=tuple(observations), observation_requirements=mapping)


class FabricRuntimeOrchestrator:
    """Run explicit runtime observations only for a current artifact."""

    def __init__(self, runner: MinecraftRunner, *, runtime_run_id_prefix: str = "runtime") -> None:
        self.runner = runner
        self.runtime_run_id_prefix = runtime_run_id_prefix

    def validate(
        self,
        *,
        contract: FabricTaskContract,
        run_state: RunState,
        artifact: ArtifactIdentity | None,
        source_revision: str,
        minecraft_spec: MinecraftTestSpec,
        runtime_root: Path | None = None,
    ) -> RuntimeValidationOutcome:
        requirements = tuple(item for item in contract.validation_requirements if item.required and item.kind in {"runtime", "minecraft", "observation"})
        if not requirements:
            return RuntimeValidationOutcome(status=RuntimeOrchestrationStatus.NOT_REQUIRED)
        if artifact is None or run_state.artifact_identity != artifact:
            return RuntimeValidationOutcome(status=RuntimeOrchestrationStatus.BLOCKED)
        build = next((item for item in reversed(run_state.build_identities) if item.build_attempt_id == artifact.producing_build_attempt_id), None)
        if build is None or not artifact.is_current(build, source_revision=source_revision, contract_identity=contract.identity()):
            return RuntimeValidationOutcome(status=RuntimeOrchestrationStatus.BLOCKED)
        plans = tuple(runtime_spec_from_requirement(item) for item in requirements)
        if len(plans) != 1:
            return RuntimeValidationOutcome(status=RuntimeOrchestrationStatus.INVALID)
        plan = plans[0]
        existing = next((item for item in reversed(run_state.runtime_identities) if item.is_current_pass(artifact_identity=artifact.artifact_identity, validation_revision=plan.validation_revision)), None)
        if existing is not None:
            return RuntimeValidationOutcome(status=RuntimeOrchestrationStatus.REUSED, runtime_identity=existing, reused=True)
        run_id = f"{self.runtime_run_id_prefix}-{run_state.run_id}-{uuid4().hex[:8]}"
        kwargs = {"run_id": run_id}
        if runtime_root is not None:
            kwargs["runtime_run_dir"] = runtime_root
        runtime_result = self.runner.run(minecraft_spec, **kwargs)
        observations = self._observations(runtime_result)
        validation, failure = self._validate_observations(plan, observations, runtime_result, artifact, run_id)
        identity = RuntimeAttemptIdentity(runtime_attempt_id=run_id, artifact_identity=artifact.artifact_identity, validation_revision=plan.validation_revision, requirement_ids=tuple(dict.fromkeys(item for values in plan.observation_requirements.values() for item in values)), result_refs=tuple(ref.ref for observation in observations for ref in observation.evidence_refs), status=validation.status.value)
        run_state.runtime_identities = (*run_state.runtime_identities, identity)
        run_state.record_validation_result(validation)
        if failure is not None:
            self._record_failure(run_state, failure)
        self._record_evidence(run_state, plan, validation)
        return RuntimeValidationOutcome(status=RuntimeOrchestrationStatus.VALIDATED, validation_result=validation, runtime_identity=identity, runtime_result=runtime_result, observations=observations, failure_fact=failure)

    def _observations(self, runtime_result: Any) -> tuple[ObservationResult, ...]:
        raw = runtime_result if isinstance(runtime_result, (list, tuple)) else getattr(runtime_result, "observations", None)
        if raw is None and runtime_result is not None:
            metadata = getattr(runtime_result, "metadata", {})
            if isinstance(metadata, Mapping):
                raw = metadata.get("observation_result", ())
        if raw is None and isinstance(runtime_result, Mapping):
            raw = runtime_result.get("observations", ())
            if not raw:
                raw = runtime_result.get("observation_result", ())
        if isinstance(raw, Mapping):
            raw = (raw,)
        return tuple(item if isinstance(item, ObservationResult) else ObservationResult.from_dict(item) for item in (raw or ()))

    def _validate_observations(self, plan: RuntimeValidationSpec, observations: tuple[ObservationResult, ...], runtime_result: Any, artifact: ArtifactIdentity, run_id: str) -> tuple[ValidationResult, FailureFact | None]:
        harness_status = getattr(runtime_result, "status", None)
        if harness_status in {MinecraftTestStatus.CRASH, MinecraftTestStatus.TIMEOUT, MinecraftTestStatus.INFRA_ERROR}:
            result_metadata = getattr(runtime_result, "metadata", {}) or {}
            runtime_evidence = getattr(runtime_result, "runtime_evidence", None)
            evidence_metadata = getattr(runtime_evidence, "metadata", {}) or {}
            target_failure = (
                harness_status is MinecraftTestStatus.CRASH
                and (
                    result_metadata.get("target_startup_failure") is True
                    or evidence_metadata.get("target_startup_failure") is True
                )
            )
            evidence_refs = tuple(
                dict.fromkeys(
                    str(path)
                    for path in (
                        getattr(runtime_evidence, "latest_log_path", None),
                        getattr(runtime_evidence, "harness_result_path", None),
                    )
                    if path is not None
                )
            )
            if target_failure:
                reason = (
                    getattr(runtime_result, "target_failure_reason", None)
                    or result_metadata.get("target_failure_reason")
                    or evidence_metadata.get("target_failure_reason")
                    or getattr(runtime_result, "reason", None)
                    or str(harness_status)
                )
                violation = ValidationViolation(
                    code="RUNTIME_TARGET_STARTUP_FAILURE",
                    requirement=plan.validation_requirement_id,
                    observed={
                        "harness_status": str(harness_status),
                        "target_startup_failure": True,
                        "target_failure_reason": str(reason),
                    },
                    expected="target mod starts and runtime obligation passes",
                    actual=str(reason),
                    message=f"target mod failed during Minecraft startup: {reason}",
                    evidence_refs=evidence_refs,
                    phase="RUNTIME",
                )
                status = ValidationStatus.REPAIRABLE_FAIL
                summary = "target runtime startup failure"
            else:
                violation = ValidationViolation(code="RUNTIME_HARNESS_BLOCKED", requirement=plan.validation_requirement_id, observed={"harness_status": str(harness_status)}, expected="PASS", actual=str(harness_status), message="Minecraft harness did not provide a target result", phase="RUNTIME")
                status = ValidationStatus.BLOCKED
                summary = "runtime harness blocked"
            result = ValidationResult(stage=ValidationStage.RUNTIME, status=status, summary=summary, violations=(violation,), evidence_refs=evidence_refs)
            requirement_ids = tuple(dict.fromkeys(item for values in plan.observation_requirements.values() for item in values))
            return result, FailureFact(failure_id=f"runtime-failure-{run_id}", status=FailureFactStatus.ACTIVE, requirement_ids=requirement_ids, code=violation.code, category="RUNTIME", evidence_refs=evidence_refs)
        expected_ids = set(plan.observation_requirements)
        actual_ids = {item.observation_id for item in observations}
        if actual_ids - expected_ids or expected_ids - actual_ids:
            violation = ValidationViolation(code="RUNTIME_OBSERVATION_MAPPING_INVALID", requirement=plan.validation_requirement_id, observed={"observation_ids": sorted(actual_ids)}, expected=sorted(expected_ids), actual=sorted(actual_ids), message="runtime observation mapping does not match the validation contract", evidence_refs=tuple(ref.ref for item in observations for ref in item.evidence_refs), phase="RUNTIME")
            return ValidationResult(stage=ValidationStage.RUNTIME, status=ValidationStatus.INVALID, summary="runtime observation mapping invalid", violations=(violation,), evidence_refs=violation.evidence_refs), None
        violations: list[ValidationViolation] = []
        observation_evidence_refs = tuple(
            dict.fromkeys(ref.ref for item in observations for ref in item.evidence_refs)
        )
        for observation in observations:
            if observation.status is MinecraftObservationStatus.FAIL:
                violations.append(ValidationViolation(code="RUNTIME_OBSERVATION_MISMATCH", requirement=",".join(plan.observation_requirements[observation.observation_id]), observed={"observation_id": observation.observation_id}, expected=observation.expected, actual=observation.actual, message="runtime observation does not match expected value", evidence_refs=tuple(ref.ref for ref in observation.evidence_refs), phase="RUNTIME", observation_id=observation.observation_id))
            elif observation.status is MinecraftObservationStatus.BLOCKED:
                violations.append(ValidationViolation(code="RUNTIME_BLOCKED", requirement=",".join(plan.observation_requirements[observation.observation_id]), observed={"observation_id": observation.observation_id}, expected=observation.expected, actual=observation.actual, message="runtime observation was blocked", evidence_refs=tuple(ref.ref for ref in observation.evidence_refs), phase="RUNTIME", observation_id=observation.observation_id))
            elif observation.status is MinecraftObservationStatus.INVALID:
                violations.append(ValidationViolation(code="RUNTIME_INVALID_RESULT", requirement=",".join(plan.observation_requirements[observation.observation_id]), observed={"observation_id": observation.observation_id}, expected=observation.expected, actual=observation.actual, message="runtime observation is invalid", evidence_refs=tuple(ref.ref for ref in observation.evidence_refs), phase="RUNTIME", observation_id=observation.observation_id))
        status = ValidationStatus.PASS if not violations else (ValidationStatus.INVALID if any(item.code == "RUNTIME_INVALID_RESULT" for item in violations) else ValidationStatus.BLOCKED if any(item.code.startswith("RUNTIME_BLOCKED") or item.code == "RUNTIME_HARNESS_BLOCKED" for item in violations) else ValidationStatus.REPAIRABLE_FAIL)
        result = ValidationResult(stage=ValidationStage.RUNTIME, status=status, summary="runtime validation passed" if status is ValidationStatus.PASS else "runtime validation failed", violations=tuple(violations), evidence_refs=tuple(dict.fromkeys((*observation_evidence_refs, *(ref for item in violations for ref in item.evidence_refs)))))
        requirement_ids = tuple(dict.fromkeys(item for values in plan.observation_requirements.values() for item in values))
        failure = None if status is ValidationStatus.PASS else FailureFact(failure_id=f"runtime-failure-{run_id}", status=FailureFactStatus.ACTIVE, requirement_ids=requirement_ids, code=violations[0].code, category="RUNTIME", evidence_refs=result.evidence_refs)
        return result, failure

    def _record_failure(self, run_state: RunState, failure: FailureFact) -> None:
        ledger = run_state.progress_ledger
        if ledger is not None:
            run_state.progress_ledger = replace(ledger, failures=(*ledger.failures, failure))

    def _record_evidence(self, run_state: RunState, plan: RuntimeValidationSpec, result: ValidationResult) -> None:
        ledger = run_state.progress_ledger
        if ledger is None:
            return
        refs = tuple(dict.fromkeys((*ledger.validation_evidence_refs, *result.evidence_refs)))
        evidence = dict(ledger.evidence_by_requirement)
        if result.status is ValidationStatus.PASS:
            refs = tuple(dict.fromkeys(ref for ref in result.evidence_refs))
            for requirement_id in {item for values in plan.observation_requirements.values() for item in values}:
                evidence[requirement_id] = tuple(dict.fromkeys((*evidence.get(requirement_id, ()), *refs)))
        run_state.progress_ledger = replace(ledger, validation_evidence_refs=refs, evidence_by_requirement=evidence)


__all__ = ["FabricRuntimeOrchestrator", "RuntimeOrchestrationStatus", "RuntimeValidationOutcome", "RuntimeValidationSpec", "runtime_spec_from_requirement"]
