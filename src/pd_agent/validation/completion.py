"""Stateless, objective completion authority for the v0.8 normal path."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pd_agent.artifacts import ArtifactClassification
from pd_agent.core import (
    FabricTaskContract,
    FailureFactStatus,
    RunState,
    SourceRevision,
    TaskProgressLedger,
    ValidationStatus,
    compute_source_revision,
    validation_contract_revision,
)


class CompletionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CompletionResult:
    status: CompletionStatus
    complete: bool
    pending_requirement_ids: tuple[str, ...] = ()
    active_failure_ids: tuple[str, ...] = ()
    missing_validation_requirement_ids: tuple[str, ...] = ()
    stale_validation_requirement_ids: tuple[str, ...] = ()
    invalid_blocking_validation_refs: tuple[str, ...] = ()
    current_evidence_refs: tuple[str, ...] = ()
    missing_completion_criteria: tuple[str, ...] = ()
    next_disposition: str = "INCOMPLETE"
    reason: str = ""

    @property
    def blocking_validation_refs(self) -> tuple[str, ...]:
        return self.invalid_blocking_validation_refs

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "complete": self.complete,
            "pending_requirement_ids": list(self.pending_requirement_ids),
            "active_failure_ids": list(self.active_failure_ids),
            "missing_validation_requirement_ids": list(self.missing_validation_requirement_ids),
            "stale_validation_requirement_ids": list(self.stale_validation_requirement_ids),
            "invalid_blocking_validation_refs": list(self.invalid_blocking_validation_refs),
            "current_evidence_refs": list(self.current_evidence_refs),
            "missing_completion_criteria": list(self.missing_completion_criteria),
            "next_disposition": self.next_disposition,
            "reason": self.reason,
        }


class CompletionGate:
    """Read-only objective completion evaluation."""

    def evaluate(self, contract: FabricTaskContract, ledger: TaskProgressLedger | None, run_state: RunState) -> CompletionResult:
        required_ids = tuple(item.requirement_id for item in contract.requirements if item.required)
        if ledger is None:
            return CompletionResult(CompletionStatus.INCOMPLETE, False, pending_requirement_ids=required_ids, next_disposition="CONTINUE", reason="progress ledger is missing")
        if ledger.contract_identity != contract.identity():
            return CompletionResult(CompletionStatus.BLOCKED, False, invalid_blocking_validation_refs=("ledger.contract_identity",), next_disposition="BLOCKED", reason="ledger contract identity does not match task contract")

        evidence = set(ledger.evidence_by_requirement)
        satisfied = set(ledger.satisfied_requirement_ids)
        pending = tuple(item for item in required_ids if item not in satisfied or item not in evidence or not ledger.evidence_by_requirement.get(item))
        latest_failures = {item.failure_id: item for item in ledger.failures}
        active = tuple(item.failure_id for item in latest_failures.values() if item.status is FailureFactStatus.ACTIVE and (not item.requirement_ids or set(item.requirement_ids).intersection(required_ids)))
        source = run_state.source_revision.revision if run_state.source_revision is not None else self._read_source_revision(run_state)

        missing: list[str] = []
        stale: list[str] = []
        blocked: list[str] = []
        for requirement in contract.validation_requirements:
            if not requirement.required:
                continue
            validation_state = self._validation_state(requirement, run_state, contract, source)
            if validation_state == "missing":
                missing.append(requirement.validation_requirement_id)
            elif validation_state == "stale":
                stale.append(requirement.validation_requirement_id)
            elif validation_state == "blocked":
                blocked.append(requirement.validation_requirement_id)

        criteria = tuple(contract.completion_criteria)
        missing_criteria = self._missing_criteria(contract, ledger, run_state, satisfied, evidence, source)
        refs = self._current_refs(ledger, run_state, source)
        if blocked:
            return self._result(CompletionStatus.BLOCKED, pending, active, missing, stale, blocked, refs, criteria, "BLOCKED", "required validation is blocked or invalid")
        if active:
            return self._result(CompletionStatus.INCOMPLETE, pending, active, missing, stale, blocked, refs, criteria, "REPAIR", "active failure blocks completion")
        if pending or missing or stale or missing_criteria:
            disposition = "BUILD" if any(item.kind.casefold() in {"build", "compilation"} for item in contract.validation_requirements if item.validation_requirement_id in (*missing, *stale)) else "CONTINUE"
            return self._result(CompletionStatus.INCOMPLETE, pending, active, missing, stale, blocked, refs, missing_criteria, disposition, "required current evidence is incomplete")
        return self._result(CompletionStatus.COMPLETE, (), (), [], [], [], refs, (), "COMPLETE", "all required objective evidence is current")

    def _missing_criteria(
        self,
        contract: FabricTaskContract,
        ledger: TaskProgressLedger,
        state: RunState,
        satisfied: set[str],
        evidence: set[str],
        source: str | None,
    ) -> tuple[str, ...]:
        """Resolve descriptive criteria against their typed obligations."""
        missing: list[str] = []
        requirements = tuple(contract.requirements)
        for criterion in contract.completion_criteria:
            normalized = " ".join(criterion.casefold().replace("_", " ").split())
            matched_requirement = next(
                (
                    item for item in requirements
                    if normalized == item.requirement_id.casefold().replace("_", " ")
                    or normalized in item.description.casefold()
                ),
                None,
            )
            if matched_requirement is not None:
                if matched_requirement.requirement_id not in satisfied or matched_requirement.requirement_id not in evidence:
                    missing.append(criterion)
                continue
            matched_validation = next(
                (
                    item for item in contract.validation_requirements
                    if normalized in {item.validation_requirement_id.casefold().replace("_", " "), item.kind.casefold()}
                ),
                None,
            )
            if matched_validation is None:
                missing.append(criterion)
                continue
            state_value = self._validation_state(matched_validation, state, contract, source)
            if state_value != "pass":
                missing.append(criterion)
        return tuple(missing)

    def _validation_state(self, requirement: Any, state: RunState, contract: FabricTaskContract, source: str | None) -> str:
        kind = str(requirement.kind).casefold()
        if kind in {"build", "compilation"}:
            if source is None:
                return "missing"
            current = any(item.is_current(source_revision=source, contract_identity=contract.identity()) for item in state.build_identities)
            return "pass" if current else ("stale" if state.build_identities else "missing")
        if kind in {"artifact", "jar"}:
            artifact = state.artifact_identity
            if source is None or artifact is None:
                return "missing"
            build = next((item for item in reversed(state.build_identities) if item.build_attempt_id == artifact.producing_build_attempt_id), None)
            if build is None or not artifact.is_current(build, source_revision=source, contract_identity=contract.identity()):
                return "stale"
            return "pass" if state.artifact_result is None or state.artifact_result.classification == ArtifactClassification.VALID.value else "blocked"
        if kind in {"runtime", "minecraft", "observation"}:
            if state.artifact_identity is None:
                return "missing"
            build = next((item for item in reversed(state.build_identities) if item.build_attempt_id == state.artifact_identity.producing_build_attempt_id), None)
            if source is None or build is None or not state.artifact_identity.is_current(build, source_revision=source, contract_identity=contract.identity()):
                return "stale" if state.runtime_identities or state.artifact_identity is not None else "missing"
            revision = validation_contract_revision(requirement)
            applicable = set(requirement.requirement_ids)
            current = any(item.is_current_pass(artifact_identity=state.artifact_identity.artifact_identity, validation_revision=revision) and applicable.intersection(item.requirement_ids) for item in state.runtime_identities)
            return "pass" if current else ("stale" if state.runtime_identities else "missing")
        results = [item for item in state.validation_results if item.stage.value.casefold() == kind]
        if any(item.status in {ValidationStatus.BLOCKED, ValidationStatus.INVALID} for item in results):
            return "blocked"
        return "pass" if any(item.status is ValidationStatus.PASS for item in results) else "missing"

    def _read_source_revision(self, state: RunState) -> str | None:
        if state.project_root is None:
            return None
        try:
            return compute_source_revision(state.project_root).revision
        except (OSError, ValueError):
            return None

    def _current_refs(self, ledger: TaskProgressLedger, state: RunState, source: str | None) -> tuple[str, ...]:
        refs = [ref for values in ledger.evidence_by_requirement.values() for ref in values]
        refs.extend(item.result_ref for item in state.build_identities if item.success and (source is None or item.source_revision == source) and item.result_ref)
        refs.extend(ref for item in state.runtime_identities if item.status == "PASS" for ref in item.result_refs)
        return tuple(dict.fromkeys(refs))

    def _result(self, status: CompletionStatus, pending: tuple[str, ...], active: tuple[str, ...], missing: list[str], stale: list[str], blocked: list[str], refs: tuple[str, ...], criteria: tuple[str, ...], disposition: str, reason: str) -> CompletionResult:
        return CompletionResult(status, status is CompletionStatus.COMPLETE, pending, active, tuple(missing), tuple(stale), tuple(blocked), refs, criteria, disposition, reason)


__all__ = ["CompletionGate", "CompletionResult", "CompletionStatus"]
