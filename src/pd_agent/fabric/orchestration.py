"""Thin normal Fabric orchestration boundary for v0.8 I10."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from pd_agent.artifacts import ArtifactValidator
from pd_agent.brain import BrainTrigger, FabricBrainOrchestrator, KnowledgeEnvironment
from pd_agent.context import ContextManager
from pd_agent.core import (
    AgentResponse,
    ExecutionLimits,
    ExecutionPlan,
    ExecutionPlanStep,
    FabricTaskContract,
    RunState,
    RunStatus,
    TaskProgressLedger,
)
from pd_agent.project import ProjectInspectionStatus, ProjectInspector
from pd_agent.reporting import FinalReport, RunStorage
from pd_agent.runtime import AgentRuntime
from pd_agent.tools import ToolExecutor, create_filesystem_tools
from pd_agent.validation import CompletionGate, CompletionResult


class FabricOrchestrationStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class FabricOrchestrationResult:
    run_id: str
    status: FabricOrchestrationStatus
    contract_identity: tuple[str, str, str]
    completion: CompletionResult
    source_revision: str | None = None
    artifact_identity: str | None = None
    artifact_sha256: str | None = None
    pending_requirement_ids: tuple[str, ...] = ()
    active_failure_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    build_summary: Mapping[str, Any] | None = None
    runtime_summary: Mapping[str, Any] | None = None
    repair_summary: Mapping[str, Any] | None = None
    report: FinalReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "contract_identity": list(self.contract_identity),
            "completion": self.completion.to_dict(),
            "source_revision": self.source_revision,
            "artifact_identity": self.artifact_identity,
            "artifact_sha256": self.artifact_sha256,
            "pending_requirement_ids": list(self.pending_requirement_ids),
            "active_failure_ids": list(self.active_failure_ids),
            "evidence_refs": list(self.evidence_refs),
            "build_summary": dict(self.build_summary or {}),
            "runtime_summary": dict(self.runtime_summary or {}),
            "repair_summary": dict(self.repair_summary or {}),
        }


@dataclass(slots=True)
class FabricNormalOrchestrator:
    """Coordinate existing Fabric components without owning their state machines."""

    provider: Any
    build_runner: Any
    artifact_validator: ArtifactValidator
    context_manager: ContextManager
    project_inspector: ProjectInspector = ProjectInspector()
    tool_executor: ToolExecutor | None = None
    reporting: RunStorage | None = None
    model_config: Mapping[str, Any] | None = None
    limits: ExecutionLimits = ExecutionLimits()
    pre_build_validator: Any | None = None
    functional_validator: Any | None = None
    brain_orchestrator: FabricBrainOrchestrator | None = None
    knowledge_environment: KnowledgeEnvironment = KnowledgeEnvironment()
    knowledge_service: Any | None = None
    validation_contract: Any | None = None
    repair_knowledge_source: Any | None = None
    repair_knowledge_environment: Any | None = None

    def run(
        self,
        requirement: FabricTaskContract | Mapping[str, Any],
        project_root: Path,
        *,
        brain_enabled: bool = True,
        external_context: tuple[Any, ...] = (),
    ) -> FabricOrchestrationResult:
        contract = self._contract(requirement)
        plan = self._plan(contract)
        ledger = TaskProgressLedger(contract_identity=contract.identity())
        state = RunState(project_root=Path(project_root), task=contract.task_id, task_contract=contract, execution_plan=plan, progress_ledger=ledger)
        snapshot = self.project_inspector.inspect(Path(project_root))
        if snapshot.status != ProjectInspectionStatus.READY:
            state.state = RunStatus.INSPECTING
            state.state = RunStatus.BLOCKED
            state.termination_reason = "project inspection blocked"
            completion = CompletionGate().evaluate(contract, ledger, state)
            return self._result(state, contract, completion, None)

        state.state = RunStatus.INSPECTING
        brain = self.brain_orchestrator or FabricBrainOrchestrator(knowledge_service=self.knowledge_service, context_manager=self.context_manager)
        brain_result = brain.prepare(contract=contract, environment=self.knowledge_environment, ledger=ledger, run_state=state, trigger=BrainTrigger.PRE_CODE, brain_enabled=brain_enabled, offline=True, project_snapshot=snapshot)
        if brain_result.ledger is not None:
            state.progress_ledger = brain_result.ledger
        knowledge_context = brain_result.provider_messages if brain_enabled else ()
        executor = self.tool_executor or ToolExecutor(tools=create_filesystem_tools())
        if self.reporting is not None:
            executor.event_sink = self.reporting.event_writer(state.run_id)
        runtime = AgentRuntime(provider=self.provider, tool_executor=executor, build_runner=self.build_runner, artifact_validator=self.artifact_validator, context_manager=self.context_manager, reporting=self.reporting, model_config=self.model_config or {}, pre_build_validator=self.pre_build_validator, functional_validator=self.functional_validator, validation_contract=self.validation_contract, repair_knowledge_source=self.repair_knowledge_source, repair_knowledge_environment=self.repair_knowledge_environment)
        state, report = runtime.run(run_state=state, project_snapshot=snapshot, task=contract.goal, external_context=(*external_context, *knowledge_context), limits=self.limits)
        completion = CompletionGate().evaluate(contract, state.progress_ledger, state)
        return self._result(state, contract, completion, report)

    def _result(self, state: RunState, contract: FabricTaskContract, completion: CompletionResult, report: FinalReport | None) -> FabricOrchestrationResult:
        artifact = state.artifact_identity
        source = state.source_revision.revision if state.source_revision is not None else None
        refs = completion.current_evidence_refs
        status = FabricOrchestrationStatus.BLOCKED if state.state is RunStatus.BLOCKED else FabricOrchestrationStatus(completion.status.value)
        return FabricOrchestrationResult(run_id=state.run_id, status=status, contract_identity=contract.identity(), completion=completion, source_revision=source, artifact_identity=artifact.artifact_identity if artifact else None, artifact_sha256=artifact.sha256 if artifact else None, pending_requirement_ids=completion.pending_requirement_ids, active_failure_ids=completion.active_failure_ids, evidence_refs=refs, build_summary={"attempts": state.build_attempt_count, "results": len(state.build_results)}, runtime_summary={"attempts": len(state.runtime_identities)}, repair_summary={"active_failures": len(completion.active_failure_ids)}, report=report)

    def _contract(self, requirement: FabricTaskContract | Mapping[str, Any]) -> FabricTaskContract:
        if isinstance(requirement, FabricTaskContract):
            return requirement
        if isinstance(requirement, Mapping):
            return FabricTaskContract.from_dict(requirement)
        raise TypeError("requirement must be a FabricTaskContract or contract mapping")

    def _plan(self, contract: FabricTaskContract) -> ExecutionPlan:
        steps = tuple(ExecutionPlanStep(step_id=f"requirement:{item.requirement_id}", intent=item.description, requirement_ids=(item.requirement_id,)) for item in contract.requirements)
        plan = ExecutionPlan(plan_id=f"plan:{contract.task_id}", revision=contract.revision, steps=steps)
        plan.validate_against(tuple(item.requirement_id for item in contract.requirements))
        return plan


NormalFabricOrchestrator = FabricNormalOrchestrator

__all__ = ["FabricNormalOrchestrator", "FabricOrchestrationResult", "FabricOrchestrationStatus", "NormalFabricOrchestrator"]
