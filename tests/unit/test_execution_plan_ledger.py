from __future__ import annotations

import json

import pytest

from pd_agent.core import (
    ExecutionPlan,
    ExecutionPlanStep,
    FailureFact,
    FailureFactStatus,
    FabricRequirement,
    FabricTaskContract,
    PlanStepStatus,
    RunState,
    TaskProgressLedger,
)


def _contract() -> FabricTaskContract:
    return FabricTaskContract(
        task_id="demo",
        revision="1",
        goal="implement feature",
        requirements=(
            FabricRequirement(requirement_id="r1", description="source exists"),
            FabricRequirement(requirement_id="r2", description="build passes"),
        ),
    )


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        revision="1",
        steps=(
            ExecutionPlanStep(step_id="s1", intent="edit source", requirement_ids=("r1",)),
            ExecutionPlanStep(step_id="s2", intent="build", requirement_ids=("r2",), status=PlanStepStatus.ACTIVE),
        ),
    )


def test_plan_is_ordered_and_roundtrips_deterministically() -> None:
    plan = _plan()
    plan.validate_against(("r1", "r2"))
    reopened = ExecutionPlan.from_dict(plan.to_dict())
    assert tuple(step.step_id for step in reopened.steps) == ("s1", "s2")
    assert json.dumps(plan.to_dict(), sort_keys=True) == json.dumps(reopened.to_dict(), sort_keys=True)
    assert reopened == plan


def test_plan_revision_and_validation() -> None:
    assert _plan().revision == "1"
    with pytest.raises(ValueError, match="duplicate step"):
        ExecutionPlan(plan_id="p", revision="1", steps=(ExecutionPlanStep(step_id="s", intent="a"), ExecutionPlanStep(step_id="s", intent="b")))
    with pytest.raises(ValueError, match="unknown requirements"):
        ExecutionPlan(plan_id="p", revision="1", steps=(ExecutionPlanStep(step_id="s", intent="a", requirement_ids=("missing",)),)).validate_against(("r1",))


def test_plan_does_not_satisfy_requirements() -> None:
    assert not hasattr(_plan(), "satisfied_requirement_ids")


def test_ledger_derives_pending_and_roundtrips() -> None:
    contract = _contract()
    ledger = TaskProgressLedger(contract_identity=contract.identity(), satisfied_requirement_ids=("r1",), evidence_by_requirement={"r1": ("evidence/r1.json",)})
    ledger.validate_against(("r1", "r2"))
    assert ledger.pending_requirement_ids(("r1", "r2")) == ("r2",)
    assert TaskProgressLedger.from_dict(ledger.to_dict()) == ledger


def test_ledger_rejects_unknown_and_contradictory_progress() -> None:
    with pytest.raises(ValueError, match="unknown"):
        TaskProgressLedger(contract_identity=("t", "1", "f"), satisfied_requirement_ids=("missing",)).validate_against(("r1",))
    with pytest.raises(ValueError, match="unknown"):
        TaskProgressLedger(contract_identity=("t", "1", "f"), evidence_by_requirement={"missing": ("ref",)}).validate_against(("r1",))


def test_failure_history_and_resolution_are_append_only() -> None:
    active = FailureFact(failure_id="f1", status=FailureFactStatus.ACTIVE, requirement_ids=("r1",), code="BUILD_ERROR", category="compilation", evidence_refs=("evidence/f1.json",))
    resolved = FailureFact(failure_id="f1", status=FailureFactStatus.RESOLVED, requirement_ids=("r1",), code="BUILD_ERROR", category="compilation", evidence_refs=active.evidence_refs, resolution_evidence_refs=("evidence/f2.json",))
    ledger = TaskProgressLedger(contract_identity=_contract().identity(), failures=(active, resolved))
    assert len(ledger.failures) == 2
    assert ledger.failures[0].status is FailureFactStatus.ACTIVE
    assert ledger.failures[1].status is FailureFactStatus.RESOLVED


def test_resolved_failure_requires_resolution_evidence_and_heavy_data_is_rejected() -> None:
    with pytest.raises(ValueError, match="resolution evidence"):
        FailureFact(failure_id="f1", status=FailureFactStatus.RESOLVED, requirement_ids=(), code="x", category="y")
    with pytest.raises(ValueError, match="oversized"):
        FailureFact(failure_id="f1", status=FailureFactStatus.ACTIVE, requirement_ids=(), code="x", category="y", evidence_refs=("x" * 513,))


def test_run_state_legacy_and_optional_i2_readback() -> None:
    state = RunState(task="legacy", current_plan="inspect, edit")
    reopened = RunState.from_dict(state.to_dict())
    assert reopened.current_plan == "inspect, edit"
    contract = _contract()
    state.task_contract = contract
    state.execution_plan = _plan()
    state.progress_ledger = TaskProgressLedger(contract_identity=contract.identity())
    restored = RunState.from_dict(state.to_dict())
    assert restored.task_contract == contract
    assert restored.execution_plan == state.execution_plan
    assert restored.progress_ledger == state.progress_ledger


def test_i2_core_isolation() -> None:
    import inspect
    import pd_agent.core.progress as progress

    assert "pd_agent.benchmark" not in inspect.getsource(progress)
