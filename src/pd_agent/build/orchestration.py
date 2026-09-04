"""Small product build/artifact orchestration boundary for v0.8 I5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol
from uuid import uuid4

from pd_agent.artifacts import ArtifactClassification, ArtifactValidator
from pd_agent.core import (
    ArtifactIdentity,
    BuildAttemptIdentity,
    BuildResult,
    FabricTaskContract,
    FailureFact,
    FailureFactStatus,
    RunState,
    ValidationResult,
    ValidationStatus,
    compute_source_revision,
    artifact_identity_from_result,
)
from pd_agent.build.normalization import BuildFailureNormalizer, NormalizedBuildFailure
from pd_agent.build.runner import GradleBuildRunner
from pd_agent.project import ProjectSnapshot
from pd_agent.reporting import RunStorage
from pd_agent.validation import PreBuildWorkspaceValidator


class BuildOrchestrationStatus(StrEnum):
    REUSED = "REUSED"
    PREBUILD_FAILED = "PREBUILD_FAILED"
    BUILT = "BUILT"
    BUILD_FAILED = "BUILD_FAILED"
    ARTIFACT_INVALID = "ARTIFACT_INVALID"
    BLOCKED = "BLOCKED"


class BuildRunner(Protocol):
    def run(self, project_snapshot: ProjectSnapshot, run_state: RunState, limits: Any) -> BuildResult:
        """Run one controlled build."""


@dataclass(frozen=True, slots=True)
class BuildOrchestrationResult:
    status: BuildOrchestrationStatus
    source_revision: str
    build_attempt_id: str | None = None
    build_result: BuildResult | None = None
    artifact_identity: ArtifactIdentity | None = None
    artifact_result: Any | None = None
    normalized_failure: NormalizedBuildFailure | None = None
    prebuild_result: ValidationResult | None = None
    failure_facts: tuple[FailureFact, ...] = ()
    reused_build: bool = False


class FabricBuildOrchestrator:
    """Coordinate one build path without owning runtime or repair orchestration."""

    def __init__(
        self,
        *,
        build_runner: BuildRunner | None = None,
        prebuild_validator: PreBuildWorkspaceValidator | None = None,
        artifact_validator: ArtifactValidator | None = None,
        normalizer: BuildFailureNormalizer | None = None,
        reporting: RunStorage | None = None,
    ) -> None:
        self.build_runner = build_runner or GradleBuildRunner(reporting=reporting)
        self.prebuild_validator = prebuild_validator or PreBuildWorkspaceValidator()
        self.artifact_validator = artifact_validator or ArtifactValidator(reporting=reporting)
        self.normalizer = normalizer or BuildFailureNormalizer()

    def ensure_build(
        self,
        *,
        project_snapshot: ProjectSnapshot,
        run_state: RunState,
        contract: FabricTaskContract,
        limits: Any,
        prebuild_contract: Mapping[str, Any] | None = None,
        source_revision: str | None = None,
        toolchain_identity: str | None = None,
        artifact_required: bool | None = None,
    ) -> BuildOrchestrationResult:
        """Build only when the current successful binding cannot be reused."""

        source = source_revision or compute_source_revision(project_snapshot.project_root).revision
        contract_identity = contract.identity()
        artifact_required = self._artifact_required(contract) if artifact_required is None else artifact_required
        current_build = self._current_build(run_state, source, contract_identity, toolchain_identity)
        current_artifact = self._current_artifact(run_state, current_build, source, contract_identity)
        if current_build is not None and (not artifact_required or current_artifact is not None):
            return BuildOrchestrationResult(status=BuildOrchestrationStatus.REUSED, source_revision=source, build_attempt_id=current_build.build_attempt_id, artifact_identity=current_artifact, artifact_result=run_state.artifact_result, reused_build=True)

        prebuild = None
        if prebuild_contract is not None:
            prebuild = self.prebuild_validator.validate(project_snapshot.project_root, prebuild_contract)
            run_state.record_validation_result(prebuild)
            if prebuild.status is not ValidationStatus.PASS:
                return BuildOrchestrationResult(status=BuildOrchestrationStatus.PREBUILD_FAILED, source_revision=source, prebuild_result=prebuild)

        attempt = run_state.build_attempt_count + 1
        build_attempt_id = f"build-{run_state.run_id}-{attempt}-{uuid4().hex[:8]}"
        try:
            result = self.build_runner.run(project_snapshot, run_state, limits)
        except Exception as exc:
            return BuildOrchestrationResult(status=BuildOrchestrationStatus.BLOCKED, source_revision=source, build_attempt_id=build_attempt_id, normalized_failure=None)

        identity = BuildAttemptIdentity(build_attempt_id=build_attempt_id, source_revision=source, contract_identity=contract_identity, toolchain_identity=toolchain_identity, result_ref=f"builds/{result.attempt}", success=result.success)
        run_state.build_identities = (*run_state.build_identities, identity)
        if not result.success:
            normalized = self.normalizer.normalize(result, source_revision=source, build_attempt_id=build_attempt_id, evidence_refs=(f"builds/{result.attempt}/stderr.log",))
            fact = normalized.to_failure_fact(failure_id=f"build-failure-{result.attempt}") if normalized is not None else None
            if fact is not None:
                self._record_failure(run_state, fact)
            return BuildOrchestrationResult(status=BuildOrchestrationStatus.BUILD_FAILED, source_revision=source, build_attempt_id=build_attempt_id, build_result=result, normalized_failure=normalized, failure_facts=(fact,) if fact else ())

        artifact_result = None
        artifact_identity = None
        if artifact_required:
            artifact_result = self.artifact_validator.validate(
                project_snapshot,
                result,
                run_id=run_state.run_id,
                required_entries=self._required_artifact_entries(contract),
            )
            run_state.artifact_result = artifact_result
            if artifact_result.classification == ArtifactClassification.VALID.value:
                artifact_identity = artifact_identity_from_result(artifact_result, producing_build_attempt_id=build_attempt_id, source_revision=source, contract_identity=contract_identity)
                run_state.artifact_identity = artifact_identity
            else:
                return BuildOrchestrationResult(status=BuildOrchestrationStatus.ARTIFACT_INVALID, source_revision=source, build_attempt_id=build_attempt_id, build_result=result, artifact_result=artifact_result)
        self._resolve_eligible_build_failures(run_state, source, contract_identity, identity)
        return BuildOrchestrationResult(status=BuildOrchestrationStatus.BUILT, source_revision=source, build_attempt_id=build_attempt_id, build_result=result, artifact_identity=artifact_identity, artifact_result=artifact_result)

    def _artifact_required(self, contract: FabricTaskContract) -> bool:
        return any(item.required and item.kind in {"artifact", "jar"} for item in contract.validation_requirements)

    def _required_artifact_entries(self, contract: FabricTaskContract) -> tuple[str, ...] | None:
        entries: list[str] = []
        for validation in contract.validation_requirements:
            if validation.kind.casefold() not in {"artifact", "jar"}:
                continue
            raw_entries = validation.spec.get("required_entries")
            if isinstance(raw_entries, (list, tuple)):
                entries.extend(str(entry) for entry in raw_entries)
            if validation.spec.get("profile") == "vertical_a_resources_v1":
                paths = validation.spec.get("resource_paths", {})
                if isinstance(paths, Mapping):
                    for path in paths.values():
                        if isinstance(path, str) and path:
                            entries.append(path.removeprefix("src/main/resources/"))
        return tuple(entries) if entries else None

    def _current_build(self, run_state: RunState, source: str, contract_identity: tuple[str, str, str], toolchain: str | None) -> BuildAttemptIdentity | None:
        for identity in reversed(run_state.build_identities):
            if identity.is_current(source_revision=source, contract_identity=contract_identity, toolchain_identity=toolchain):
                return identity
        return None

    def _current_artifact(self, run_state: RunState, build: BuildAttemptIdentity | None, source: str, contract_identity: tuple[str, str, str]) -> ArtifactIdentity | None:
        artifact = run_state.artifact_identity
        if artifact is not None and build is not None and artifact.is_current(build, source_revision=source, contract_identity=contract_identity):
            return artifact
        return None

    def _record_failure(self, run_state: RunState, failure: FailureFact) -> None:
        ledger = run_state.progress_ledger
        if ledger is None:
            return
        run_state.progress_ledger = type(ledger)(
            contract_identity=ledger.contract_identity,
            satisfied_requirement_ids=ledger.satisfied_requirement_ids,
            evidence_by_requirement=ledger.evidence_by_requirement,
            failures=(*ledger.failures, failure),
            validation_evidence_refs=ledger.validation_evidence_refs,
            knowledge_correlation=ledger.knowledge_correlation,
            next_safe_disposition=ledger.next_safe_disposition,
        )

    def _resolve_eligible_build_failures(self, run_state: RunState, source: str, contract_identity: tuple[str, str, str], build: BuildAttemptIdentity) -> None:
        ledger = run_state.progress_ledger
        if ledger is None or not build.success or ledger.contract_identity != contract_identity:
            return
        resolved: list[FailureFact] = list(ledger.failures)
        for failure in ledger.failures:
            if failure.status is FailureFactStatus.ACTIVE and failure.category in {"MISSING_SYMBOL", "COMPILATION_ERROR", "SIGNATURE_OR_API_MISMATCH"}:
                resolved.append(FailureFact(failure_id=failure.failure_id, status=FailureFactStatus.RESOLVED, requirement_ids=failure.requirement_ids, code=failure.code, category=failure.category, evidence_refs=failure.evidence_refs, resolution_evidence_refs=(build.result_ref or f"build/{build.build_attempt_id}",)))
        if len(resolved) == len(ledger.failures):
            return
        run_state.progress_ledger = type(ledger)(contract_identity=ledger.contract_identity, satisfied_requirement_ids=ledger.satisfied_requirement_ids, evidence_by_requirement=ledger.evidence_by_requirement, failures=tuple(resolved), validation_evidence_refs=ledger.validation_evidence_refs, knowledge_correlation=ledger.knowledge_correlation, next_safe_disposition=ledger.next_safe_disposition)


__all__ = ["BuildOrchestrationResult", "BuildOrchestrationStatus", "FabricBuildOrchestrator"]
