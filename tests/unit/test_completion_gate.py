from __future__ import annotations

from datetime import datetime, timezone

from pd_agent.core import (
    ArtifactIdentity,
    ArtifactResult,
    BuildAttemptIdentity,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    FailureFact,
    FailureFactStatus,
    RunState,
    SourceRevision,
    TaskProgressLedger,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    validation_contract_revision,
)
from pd_agent.validation import CompletionGate


SHA = "a" * 64


def _contract(*, validations: tuple[FabricValidationRequirement, ...] = (), criteria: tuple[str, ...] = (), optional: bool = False) -> FabricTaskContract:
    return FabricTaskContract(
        task_id="task",
        revision="1",
        goal="complete a Fabric task",
        requirements=(
            FabricRequirement(requirement_id="r1", description="source", required=not optional),
            FabricRequirement(requirement_id="r2", description="optional", required=False),
        ),
        completion_criteria=criteria,
        validation_requirements=validations,
    )


def _state(contract: FabricTaskContract, *, satisfied: tuple[str, ...] = ("r1",), refs: tuple[str, ...] = ("evidence/r1.json",)) -> RunState:
    return RunState(progress_ledger=TaskProgressLedger(contract_identity=contract.identity(), satisfied_requirement_ids=satisfied, evidence_by_requirement={item: refs for item in satisfied}))


def _validation(kind: str, *, required: bool = True, requirement_ids: tuple[str, ...] = ("r1",)) -> FabricValidationRequirement:
    return FabricValidationRequirement(validation_requirement_id=f"v-{kind}", requirement_ids=requirement_ids, kind=kind, required=required)


def _build(contract: FabricTaskContract, *, source: str = SHA, success: bool = True) -> BuildAttemptIdentity:
    return BuildAttemptIdentity(build_attempt_id="build-1", source_revision=source, contract_identity=contract.identity(), success=success, result_ref="builds/1")


def test_all_required_evidence_is_complete() -> None:
    contract = _contract()
    state = _state(contract)
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.status.value == "COMPLETE"
    assert result.complete is True
    assert result.to_dict()["status"] == "COMPLETE"


def test_pending_required_requirement_is_incomplete() -> None:
    contract = _contract()
    state = _state(contract, satisfied=())
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.status.value == "INCOMPLETE"
    assert result.pending_requirement_ids == ("r1",)
    assert result.next_disposition == "CONTINUE"


def test_optional_pending_requirement_does_not_block() -> None:
    contract = _contract(optional=True)
    state = _state(contract, satisfied=())
    assert CompletionGate().evaluate(contract, state.progress_ledger, state).status.value == "COMPLETE"


def test_active_failure_blocks_and_resolved_history_does_not() -> None:
    contract = _contract()
    state = _state(contract)
    failure = FailureFact(failure_id="f1", status=FailureFactStatus.ACTIVE, requirement_ids=("r1",), code="BUILD", category="BUILD", evidence_refs=("failure/1.json",))
    state.progress_ledger = TaskProgressLedger(contract_identity=contract.identity(), satisfied_requirement_ids=("r1",), evidence_by_requirement={"r1": ("evidence/r1.json",)}, failures=(failure,))
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.complete is False and result.active_failure_ids == ("f1",)
    resolved = FailureFact(failure_id="f1", status=FailureFactStatus.RESOLVED, requirement_ids=("r1",), code="BUILD", category="BUILD", evidence_refs=failure.evidence_refs, resolution_evidence_refs=("builds/2",))
    state.progress_ledger = TaskProgressLedger(contract_identity=contract.identity(), satisfied_requirement_ids=("r1",), evidence_by_requirement={"r1": ("evidence/r1.json",)}, failures=(resolved,))
    assert CompletionGate().evaluate(contract, state.progress_ledger, state).complete is True


def test_missing_ledger_and_legacy_completed_state_cannot_complete() -> None:
    contract = _contract()
    state = RunState(state="COMPLETED")
    result = CompletionGate().evaluate(contract, None, state)
    assert result.complete is False and result.pending_requirement_ids == ("r1",)


def test_contract_identity_mismatch_is_blocked() -> None:
    contract = _contract()
    other = _contract(criteria=("different",))
    state = _state(other)
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.status.value == "BLOCKED"
    assert result.invalid_blocking_validation_refs == ("ledger.contract_identity",)


def test_build_requires_current_successful_identity() -> None:
    requirement = _validation("build")
    contract = _contract(validations=(requirement,))
    state = _state(contract)
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.missing_validation_requirement_ids == ("v-build",)
    state.build_identities = (_build(contract, source=SHA, success=True),)
    state.source_revision = SourceRevision(SHA)
    assert CompletionGate().evaluate(contract, state.progress_ledger, state).complete is True


def test_stale_build_and_artifact_are_not_current() -> None:
    build_req = _validation("build")
    artifact_req = _validation("artifact")
    contract = _contract(validations=(build_req, artifact_req))
    state = _state(contract)
    state.source_revision = SourceRevision("b" * 64)
    state.build_identities = (_build(contract, source=SHA),)
    state.artifact_identity = ArtifactIdentity(artifact_identity=SHA, sha256=SHA, producing_build_attempt_id="build-1", source_revision=SHA, contract_identity=contract.identity())
    state.artifact_result = ArtifactResult(path=None, size=1, timestamp=datetime.now(timezone.utc), classification="VALID")
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.stale_validation_requirement_ids == ("v-build", "v-artifact")


def test_build_or_artifact_alone_does_not_satisfy_requirement() -> None:
    requirement = _validation("build")
    contract = _contract(validations=(requirement,))
    state = _state(contract, satisfied=())
    state.source_revision = SourceRevision(SHA)
    state.build_identities = (_build(contract),)
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.complete is False and result.pending_requirement_ids == ("r1",)


def test_runtime_requires_current_artifact_and_validation_revision() -> None:
    requirement = _validation("runtime")
    contract = _contract(validations=(requirement,))
    state = _state(contract)
    state.source_revision = SourceRevision(SHA)
    state.build_identities = (_build(contract),)
    state.artifact_identity = ArtifactIdentity(artifact_identity=SHA, sha256=SHA, producing_build_attempt_id="build-1", source_revision=SHA, contract_identity=contract.identity())
    result = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert result.missing_validation_requirement_ids == ("v-runtime",)


def test_current_runtime_pass_is_accepted() -> None:
    requirement = _validation("runtime")
    contract = _contract(validations=(requirement,))
    state = _state(contract)
    state.source_revision = __import__("pd_agent.core", fromlist=["SourceRevision"]).SourceRevision(SHA)
    state.build_identities = (_build(contract),)
    state.artifact_identity = ArtifactIdentity(artifact_identity=SHA, sha256=SHA, producing_build_attempt_id="build-1", source_revision=SHA, contract_identity=contract.identity())
    from pd_agent.core import RuntimeAttemptIdentity
    state.runtime_identities = (RuntimeAttemptIdentity(runtime_attempt_id="runtime-1", artifact_identity=SHA, validation_revision=validation_contract_revision(requirement), requirement_ids=("r1",), result_refs=("runtime/pass.json",), status="PASS"),)
    assert CompletionGate().evaluate(contract, state.progress_ledger, state).complete is True


def test_blocked_invalid_and_failed_validation_fail_closed() -> None:
    for status in (ValidationStatus.BLOCKED, ValidationStatus.INVALID, ValidationStatus.REPAIRABLE_FAIL):
        requirement = _validation("pre_build")
        contract = _contract(validations=(requirement,))
        state = _state(contract)
        state.validation_results = (ValidationResult(stage=ValidationStage.PRE_BUILD, status=status, summary="validation"),)
        result = CompletionGate().evaluate(contract, state.progress_ledger, state)
        assert result.status.value == ("BLOCKED" if status in {ValidationStatus.BLOCKED, ValidationStatus.INVALID} else "INCOMPLETE")


def test_unknown_completion_criteria_are_incomplete_and_deterministic() -> None:
    contract = _contract(criteria=("criterion-a",))
    state = _state(contract)
    first = CompletionGate().evaluate(contract, state.progress_ledger, state)
    second = CompletionGate().evaluate(contract, state.progress_ledger, state)
    assert first == second
    assert first.missing_completion_criteria == ("criterion-a",)


def test_serialization_is_lightweight_and_no_benchmark_dependency() -> None:
    contract = _contract()
    state = _state(contract)
    payload = CompletionGate().evaluate(contract, state.progress_ledger, state).to_dict()
    assert "logs" not in str(payload).casefold()
    assert set(payload) >= {"status", "complete", "pending_requirement_ids", "active_failure_ids"}
