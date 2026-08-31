"""Bounded semantic repair and objective failure reconciliation for v0.8 I8."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from pd_agent.build import BuildOrchestrationResult, BuildOrchestrationStatus
from pd_agent.core import (
    ArtifactIdentity,
    FailureFact,
    FailureFactStatus,
    RunState,
    SourceRevision,
    ValidationResult,
    ValidationStatus,
    compute_source_revision,
)
from pd_agent.minecraft import RuntimeOrchestrationStatus, RuntimeValidationOutcome


class RepairStatus(StrEnum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    REPAIRED = "REPAIRED"
    BLOCKED = "BLOCKED"
    STAGNATED = "STAGNATED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RepairTurnInput:
    """Bounded, provider-visible repair input; never raw logs."""

    failure_code: str
    failure_category: str
    requirement_ids: tuple[str, ...]
    expected: Any = None
    actual: Any = None
    phase: str = ""
    evidence_refs: tuple[str, ...] = ()
    source_revision: str = ""
    artifact_identity: str | None = None
    runtime_identity: str | None = None
    knowledge_context: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class RepairTurnResult:
    """Result of one bounded turn, with mutation supplied by ToolExecutor."""

    changed_files: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    provider_result: Any | None = None

    @property
    def mutated(self) -> bool:
        return bool(self.changed_files)


class RepairTurn(Protocol):
    def __call__(self, request: RepairTurnInput) -> RepairTurnResult | Any:
        """Use the existing AgentRuntime/provider-tool machinery once."""


@dataclass(frozen=True, slots=True)
class RepairCycleResult:
    status: RepairStatus
    attempts: int = 0
    source_revision_before: str | None = None
    source_revision_after: str | None = None
    build: BuildOrchestrationResult | None = None
    runtime: RuntimeValidationOutcome | None = None
    resolved_failure_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    reason: str | None = None


class FailureReconciler:
    """Resolve only a failure with matching current objective evidence."""

    def reconcile_build(
        self,
        run_state: RunState,
        failure: FailureFact,
        *,
        build: BuildOrchestrationResult,
        source_revision: str,
    ) -> bool:
        if failure.status is not FailureFactStatus.ACTIVE:
            return False
        if build.status not in {BuildOrchestrationStatus.BUILT, BuildOrchestrationStatus.REUSED}:
            return False
        if build.source_revision != source_revision or build.artifact_identity is None or build.artifact_identity.source_revision != source_revision:
            return False
        if run_state.progress_ledger is None or build.artifact_identity.contract_identity != run_state.progress_ledger.contract_identity:
            return False
        refs = tuple(
            dict.fromkeys(
                ref
                for ref in (
                    build.build_attempt_id,
                    build.artifact_identity.artifact_identity,
                    str(build.build_result.to_dict().get("attempt")) if build.build_result else None,
                )
                if ref is not None
            )
        )
        return self._resolve(run_state, failure, refs)

    def reconcile_runtime(
        self,
        run_state: RunState,
        failure: FailureFact,
        *,
        runtime: RuntimeValidationOutcome,
        artifact: ArtifactIdentity,
        requirement_ids: tuple[str, ...],
        validation_revision: str,
    ) -> bool:
        if failure.status is not FailureFactStatus.ACTIVE:
            return False
        if runtime.status not in {RuntimeOrchestrationStatus.VALIDATED, RuntimeOrchestrationStatus.REUSED}:
            return False
        result = runtime.validation_result
        identity = runtime.runtime_identity
        if result is None or result.status is not ValidationStatus.PASS or identity is None:
            return False
        if identity.artifact_identity != artifact.artifact_identity or identity.validation_revision != validation_revision:
            return False
        if tuple(requirement_ids) != tuple(failure.requirement_ids) or tuple(identity.requirement_ids) != tuple(requirement_ids):
            return False
        return self._resolve(run_state, failure, identity.result_refs)

    def _resolve(self, run_state: RunState, failure: FailureFact, refs: tuple[str, ...]) -> bool:
        refs = tuple(dict.fromkeys(ref for ref in refs if ref))
        if not refs or run_state.progress_ledger is None:
            return False
        ledger = run_state.progress_ledger
        if any(item.failure_id == failure.failure_id and item.status is FailureFactStatus.RESOLVED for item in ledger.failures):
            return True
        resolved = FailureFact(
            failure_id=failure.failure_id,
            status=FailureFactStatus.RESOLVED,
            requirement_ids=failure.requirement_ids,
            code=failure.code,
            category=failure.category,
            evidence_refs=failure.evidence_refs,
            resolution_evidence_refs=refs,
        )
        run_state.progress_ledger = replace(ledger, failures=(*ledger.failures, resolved))
        return True


class FabricRepairOrchestrator:
    """Run at most ``max_cycles`` bounded repair cycles for one active failure."""

    def __init__(self, *, repair_turn: RepairTurn, reconciler: FailureReconciler | None = None, max_cycles: int = 1) -> None:
        if max_cycles < 1:
            raise ValueError("max_cycles must be positive")
        self.repair_turn = repair_turn
        self.reconciler = reconciler or FailureReconciler()
        self.max_cycles = max_cycles
        self._cycles_used = 0

    def repair_build(
        self,
        *,
        run_state: RunState,
        failure: FailureFact,
        project_root: Path,
        build: Callable[[str], BuildOrchestrationResult],
        knowledge_context: tuple[Any, ...] = (),
    ) -> RepairCycleResult:
        if not self._eligible(failure):
            return RepairCycleResult(status=RepairStatus.NOT_ELIGIBLE, reason="failure is not REPAIRABLE")
        self._ensure_failure(run_state, failure)
        if self._cycles_used >= self.max_cycles:
            return RepairCycleResult(status=RepairStatus.BLOCKED, reason="repair cycle limit exhausted")
        self._cycles_used += 1
        return self._cycle(run_state=run_state, failure=failure, project_root=project_root, build=build, knowledge_context=knowledge_context)

    def repair_runtime(
        self,
        *,
        run_state: RunState,
        failure: FailureFact,
        project_root: Path,
        build: Callable[[str], BuildOrchestrationResult],
        runtime: Callable[[ArtifactIdentity, str], RuntimeValidationOutcome],
        requirement_ids: tuple[str, ...],
        validation_revision: str,
        knowledge_context: tuple[Any, ...] = (),
    ) -> RepairCycleResult:
        if not self._eligible(failure):
            return RepairCycleResult(status=RepairStatus.NOT_ELIGIBLE, reason="failure is not REPAIRABLE")
        self._ensure_failure(run_state, failure)
        if self._cycles_used >= self.max_cycles:
            return RepairCycleResult(status=RepairStatus.BLOCKED, reason="repair cycle limit exhausted")
        self._cycles_used += 1
        before = compute_source_revision(project_root).revision
        turn = self._turn(failure, run_state, before, knowledge_context)
        if not turn.mutated:
            return RepairCycleResult(status=RepairStatus.STAGNATED, attempts=1, source_revision_before=before, source_revision_after=before, reason="repair turn produced no FILE_CHANGED")
        after = compute_source_revision(project_root).revision
        if after == before:
            return RepairCycleResult(status=RepairStatus.STAGNATED, attempts=1, source_revision_before=before, source_revision_after=after, reason="source revision unchanged")
        run_state.source_revision = SourceRevision(after)
        built = build(after)
        if built.artifact_identity is None or built.status not in {BuildOrchestrationStatus.BUILT, BuildOrchestrationStatus.REUSED}:
            return RepairCycleResult(status=RepairStatus.FAILED, attempts=1, source_revision_before=before, source_revision_after=after, build=built, reason="repair build did not produce a valid current artifact")
        runtime_outcome = runtime(built.artifact_identity, after)
        resolved = self.reconciler.reconcile_runtime(run_state, failure, runtime=runtime_outcome, artifact=built.artifact_identity, requirement_ids=requirement_ids, validation_revision=validation_revision)
        return RepairCycleResult(status=RepairStatus.REPAIRED if resolved else RepairStatus.FAILED, attempts=1, source_revision_before=before, source_revision_after=after, build=built, runtime=runtime_outcome, resolved_failure_id=failure.failure_id if resolved else None, evidence_refs=turn.evidence_refs, reason=None if resolved else "runtime PASS did not match failure lineage")

    def _cycle(self, *, run_state: RunState, failure: FailureFact, project_root: Path, build: Callable[[str], BuildOrchestrationResult], knowledge_context: tuple[Any, ...]) -> RepairCycleResult:
        before = compute_source_revision(project_root).revision
        turn = self._turn(failure, run_state, before, knowledge_context)
        if not turn.mutated:
            return RepairCycleResult(status=RepairStatus.STAGNATED, attempts=1, source_revision_before=before, source_revision_after=before, reason="repair turn produced no FILE_CHANGED")
        after = compute_source_revision(project_root).revision
        if after == before:
            return RepairCycleResult(status=RepairStatus.STAGNATED, attempts=1, source_revision_before=before, source_revision_after=after, reason="source revision unchanged")
        run_state.source_revision = SourceRevision(after)
        built = build(after)
        resolved = self.reconciler.reconcile_build(run_state, failure, build=built, source_revision=after)
        return RepairCycleResult(status=RepairStatus.REPAIRED if resolved else RepairStatus.FAILED, attempts=1, source_revision_before=before, source_revision_after=after, build=built, resolved_failure_id=failure.failure_id if resolved else None, evidence_refs=turn.evidence_refs, reason=None if resolved else "current build PASS did not resolve failure")

    def _turn(self, failure: FailureFact, run_state: RunState, source_revision: str, context: tuple[Any, ...]) -> RepairTurnResult:
        request = RepairTurnInput(failure_code=failure.code, failure_category=failure.category, requirement_ids=failure.requirement_ids, evidence_refs=failure.evidence_refs, source_revision=source_revision, artifact_identity=run_state.artifact_identity.artifact_identity if run_state.artifact_identity else None, knowledge_context=context)
        result = self.repair_turn(request)
        if isinstance(result, RepairTurnResult):
            return result
        if isinstance(result, Mapping):
            return RepairTurnResult(changed_files=tuple(str(item) for item in result.get("changed_files", ())), evidence_refs=tuple(str(item) for item in result.get("evidence_refs", ())), provider_result=result)
        return RepairTurnResult()

    @staticmethod
    def _eligible(failure: FailureFact) -> bool:
        return failure.status is FailureFactStatus.ACTIVE and failure.category not in {"BLOCKED", "INVALID", "INFRASTRUCTURE", "PROVIDER", "TIMEOUT"}

    @staticmethod
    def _ensure_failure(run_state: RunState, failure: FailureFact) -> None:
        ledger = run_state.progress_ledger
        if ledger is None or any(item.failure_id == failure.failure_id and item.status is FailureFactStatus.ACTIVE for item in ledger.failures):
            return
        run_state.progress_ledger = replace(ledger, failures=(*ledger.failures, failure))


__all__ = ["FabricRepairOrchestrator", "FailureReconciler", "RepairCycleResult", "RepairStatus", "RepairTurnInput", "RepairTurnResult"]
