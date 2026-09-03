"""Thin normal Fabric orchestration boundary for v0.8 I10."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

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
    RunStateError,
    RunStatus,
    TaskProgressLedger,
    compute_source_revision,
    generate_run_id,
)
from pd_agent.project import ProjectInspectionStatus, ProjectInspector
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage
from pd_agent.runtime import AgentRuntime
from pd_agent.tools import ToolExecutor, create_filesystem_tools
from pd_agent.validation import CompletionGate, CompletionResult, ProductiveMinecraftFunctionalValidator


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
    minecraft_runner: Any | None = None
    minecraft_runner_factory: Any | None = None
    runtime_root_factory: Any | None = None
    gradle_user_home: Path | None = None

    def run(
        self,
        requirement: FabricTaskContract | Mapping[str, Any],
        project_root: Path,
        *,
        brain_enabled: bool = True,
        external_context: tuple[Any, ...] = (),
        pending_mutation_targets: tuple[str, ...] = (),
        run_id: UUID | str | None = None,
    ) -> FabricOrchestrationResult:
        contract = self._contract(requirement)
        plan = self._plan(contract)
        ledger = TaskProgressLedger(contract_identity=contract.identity())
        normalized_run_id = self._prepare_run_id(run_id)
        if normalized_run_id is not None and self.reporting is not None:
            self._claim_run_storage(normalized_run_id)
        state = RunState(run_id=normalized_run_id or generate_run_id(), project_root=Path(project_root), task=contract.task_id, task_contract=contract, execution_plan=plan, progress_ledger=ledger)
        if pending_mutation_targets:
            state.set_pending_mutation_targets(tuple(pending_mutation_targets))
        self._emit(state.run_id, RunEventType.CONTRACT_CREATED, {
            "contract_identity": list(contract.identity()),
            "requirement_ids": [item.requirement_id for item in contract.requirements],
        })
        self._emit(state.run_id, RunEventType.PLAN_CREATED, {
            "contract_identity": list(contract.identity()),
            "plan_id": plan.plan_id,
            "plan_revision": plan.revision,
            "requirement_ids": [item.requirement_id for item in contract.requirements],
        })
        if self.reporting is not None:
            self.reporting.write_run_state(state)
        snapshot = self.project_inspector.inspect(Path(project_root))
        if snapshot.status != ProjectInspectionStatus.READY:
            state.state = RunStatus.INSPECTING
            state.state = RunStatus.BLOCKED
            state.termination_reason = "project inspection blocked"
            completion = CompletionGate().evaluate(contract, ledger, state)
            return self._result(state, contract, completion, None)

        state.state = RunStatus.INSPECTING
        knowledge_environment = self._knowledge_environment(contract)
        brain = self.brain_orchestrator or FabricBrainOrchestrator(knowledge_service=self.knowledge_service, context_manager=self.context_manager)
        brain_result = brain.prepare(contract=contract, environment=knowledge_environment, ledger=ledger, run_state=state, trigger=BrainTrigger.PRE_CODE, brain_enabled=brain_enabled, offline=True, project_snapshot=snapshot)
        if brain_result.ledger is not None:
            state.progress_ledger = brain_result.ledger
        # Keep selected knowledge typed until AgentRuntime builds provider messages.
        knowledge_context = tuple(brain_result.selected) if brain_enabled else ()
        executor = self.tool_executor or ToolExecutor(tools=create_filesystem_tools())
        if self.reporting is not None:
            executor.event_sink = self.reporting.event_writer(state.run_id)
        functional_validator = self.functional_validator
        minecraft_runner = self.minecraft_runner
        if minecraft_runner is None and self.minecraft_runner_factory is not None:
            minecraft_runner = self.minecraft_runner_factory(Path(project_root))
        if functional_validator is None and minecraft_runner is not None:
            functional_validator = ProductiveMinecraftFunctionalValidator(
                contract=contract,
                runner=minecraft_runner,
                runtime_root_factory=self.runtime_root_factory,
                gradle_user_home=self.gradle_user_home,
            )
            functional_validator.bind_run_state(state)
        runtime = AgentRuntime(provider=self.provider, tool_executor=executor, build_runner=self.build_runner, artifact_validator=self.artifact_validator, context_manager=self.context_manager, reporting=self.reporting, model_config=self.model_config or {}, pre_build_validator=self.pre_build_validator, functional_validator=functional_validator, validation_contract=self.validation_contract or contract, repair_knowledge_source=self.repair_knowledge_source, repair_knowledge_environment=knowledge_environment)
        state, report = runtime.run(run_state=state, project_snapshot=snapshot, task=contract.goal, external_context=(*external_context, *knowledge_context), limits=self.limits)
        self._reconcile_requirement_progress(state, contract)
        if self.reporting is not None:
            self.reporting.write_run_state(state)
        completion = CompletionGate().evaluate(contract, state.progress_ledger, state)
        self._emit_state_observations(state, contract, completion)
        self._emit(state.run_id, RunEventType.COMPLETION_GATE_EVALUATED, {
            "contract_identity": list(contract.identity()),
            "status": completion.status.value,
            "complete": completion.complete,
            "pending_requirement_ids": list(completion.pending_requirement_ids),
            "active_failure_ids": list(completion.active_failure_ids),
            "missing_validation_ids": list(completion.missing_validation_requirement_ids),
            "stale_validation_ids": list(completion.stale_validation_requirement_ids),
            "blocking_refs": list(completion.invalid_blocking_validation_refs),
            "current_evidence_refs": list(completion.current_evidence_refs),
            "next_disposition": completion.next_disposition,
            "reason": completion.reason,
        })
        report = replace(
            report,
            contract_identity=contract.identity(),
            completion_status=completion.status.value,
            pending_requirement_ids=completion.pending_requirement_ids,
            active_failure_ids=completion.active_failure_ids,
        )
        if self.reporting is not None:
            self.reporting.write_final_report(report)
        return self._result(state, contract, completion, report)

    @staticmethod
    def _knowledge_environment(contract: FabricTaskContract) -> KnowledgeEnvironment:
        constraints = contract.environment_constraints
        return KnowledgeEnvironment(
            minecraft_version=constraints.minecraft_version,
            loader_version=constraints.loader_version,
            loom_version=constraints.extra.get("loom_version"),
            mappings_namespace=constraints.extra.get("mappings_namespace"),
            mappings_version=constraints.yarn_version,
            fabric_api_version=constraints.fabric_api_version,
            java_version=constraints.java_version,
        )

    def _reconcile_requirement_progress(self, state: RunState, contract: FabricTaskContract) -> None:
        """Bind objective files and validator identities to contract requirements."""
        ledger = state.progress_ledger
        if ledger is None:
            return
        satisfied = set(ledger.satisfied_requirement_ids)
        evidence = dict(ledger.evidence_by_requirement)
        source = state.source_revision.revision if state.source_revision is not None else None
        current_source = None
        if state.project_root is not None:
            try:
                current_source = compute_source_revision(state.project_root).revision
            except (OSError, ValueError):
                current_source = None
        current_builds = tuple(
            item for item in state.build_identities
            if source is not None
            and source == current_source
            and item.is_current(source_revision=source, contract_identity=contract.identity())
        )
        current_artifact = None
        if state.artifact_identity is not None and current_builds:
            producing_build = next(
                (item for item in reversed(current_builds)
                 if item.build_attempt_id == state.artifact_identity.producing_build_attempt_id),
                None,
            )
            if (
                producing_build is not None
                and state.artifact_result is not None
                and state.artifact_result.classification == "VALID"
                and state.artifact_identity.is_current(
                    producing_build,
                    source_revision=source,
                    contract_identity=contract.identity(),
                )
            ):
                current_artifact = state.artifact_identity
        for requirement in contract.requirements:
            refs: tuple[str, ...] = ()
            validations = tuple(item for item in contract.validation_requirements if requirement.requirement_id in item.requirement_ids)
            if (
                source is not None
                and source == current_source
                and state.changed_files
                and (requirement.requirement_id in {"source", "source-change"} or "source" in requirement.description.casefold())
            ):
                refs += tuple(state.changed_files)
            for validation in validations:
                kind = validation.kind.casefold()
                if kind in {"build", "compilation"}:
                    refs += tuple(item.result_ref for item in current_builds if item.result_ref)
                elif kind in {"artifact", "jar"}:
                    if "artifact" in requirement.description.casefold() and current_artifact is not None:
                        refs += (f"artifacts/{current_artifact.artifact_identity}",)
                    paths = validation.spec.get("required_paths", ())
                    if state.project_root is not None:
                        refs += tuple(str(path) for path in paths if (state.project_root / path).is_file())
                elif kind in {"runtime", "minecraft", "observation"}:
                    refs += tuple(ref for item in state.runtime_identities if item.status == "PASS" for ref in item.result_refs)
            if not validations and source is not None and source == current_source:
                description = requirement.description.casefold()
                if "recipe" in description:
                    refs = tuple(state.changed_files)
                elif requirement.requirement_id == "build":
                    refs = tuple(item.result_ref for item in current_builds if item.result_ref)
                elif requirement.requirement_id == "artifact" and current_artifact is not None:
                    refs = (f"artifacts/{current_artifact.artifact_identity}",)
            refs = tuple(dict.fromkeys(refs))
            if refs:
                satisfied.add(requirement.requirement_id)
                evidence[requirement.requirement_id] = tuple(dict.fromkeys((*evidence.get(requirement.requirement_id, ()), *refs)))
        state.progress_ledger = replace(ledger, satisfied_requirement_ids=tuple(item.requirement_id for item in contract.requirements if item.requirement_id in satisfied), evidence_by_requirement=evidence)

    def _emit(self, run_id: str, event_type: RunEventType, payload: Mapping[str, Any]) -> None:
        if self.reporting is not None:
            self.reporting.append_event(RunEvent(run_id=run_id, event_type=event_type, payload=dict(payload)))

    def _emit_state_observations(self, state: RunState, contract: FabricTaskContract, completion: CompletionResult) -> None:
        """Persist bounded lifecycle facts; state machines remain elsewhere."""
        ledger = state.progress_ledger
        identity = list(contract.identity())
        if ledger is not None:
            for requirement_id in ledger.satisfied_requirement_ids:
                self._emit(state.run_id, RunEventType.REQUIREMENT_RECONCILED, {
                    "contract_identity": identity,
                    "requirement_id": requirement_id,
                    "status": "SATISFIED",
                    "evidence_refs": list(ledger.evidence_by_requirement.get(requirement_id, ())),
                })
            for failure in ledger.failures:
                event_type = (RunEventType.FAILURE_RESOLVED
                              if failure.status.value == "RESOLVED"
                              else RunEventType.FAILURE_ACTIVE)
                self._emit(state.run_id, event_type, {
                    "contract_identity": identity,
                    "failure_id": failure.failure_id,
                    "status": failure.status.value,
                    "requirement_ids": list(failure.requirement_ids),
                    "code": failure.code,
                    "category": failure.category,
                    "evidence_refs": list(failure.evidence_refs or failure.resolution_evidence_refs),
                })
        for build in state.build_identities:
            self._emit(state.run_id, RunEventType.BUILD_ATTEMPT_RECORDED, {
                "contract_identity": identity,
                "build_attempt_id": build.build_attempt_id,
                "source_revision": build.source_revision,
                "success": build.success,
                "result_ref": build.result_ref,
            })
        for runtime in state.runtime_identities:
            self._emit(state.run_id, RunEventType.RUNTIME_VALIDATION_RECORDED, {
                "contract_identity": identity,
                "runtime_attempt_id": runtime.runtime_attempt_id,
                "artifact_identity": runtime.artifact_identity,
                "validation_revision": runtime.validation_revision,
                "status": runtime.status,
                "evidence_refs": list(runtime.result_refs),
            })
        if any(result.status.value == "REPAIRABLE_FAIL" for result in state.validation_results):
            self._emit(state.run_id, RunEventType.REPAIR_ATTEMPT_RECORDED, {
                "contract_identity": identity,
                "status": "PENDING",
                "validation_count": len(state.validation_results),
            })
        if state.artifact_result is not None:
            self._emit(state.run_id, RunEventType.ARTIFACT_VALIDATED, {
                "contract_identity": identity,
                "artifact_identity": (state.artifact_identity.artifact_identity
                                       if state.artifact_identity else None),
                "classification": state.artifact_result.classification,
            })
        for evidence_ref in completion.stale_validation_requirement_ids:
            self._emit(state.run_id, RunEventType.STALE_EVIDENCE_DETECTED, {
                "contract_identity": identity,
                "evidence_ref": evidence_ref,
            })

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

    def _prepare_run_id(self, run_id: UUID | str | None) -> str | None:
        if run_id is None:
            return None
        try:
            parsed = run_id if isinstance(run_id, UUID) else UUID(str(run_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise RunStateError("preallocated run_id must be a UUIDv4") from exc
        if parsed.version != 4:
            raise RunStateError("preallocated run_id must be a UUIDv4")
        return str(parsed)

    def _claim_run_storage(self, run_id: str) -> None:
        run_root = self.reporting.storage_root / run_id
        if run_root.exists():
            raise RunStateError(f"preallocated run_id already exists: {run_id}")
        try:
            run_root.mkdir(parents=True)
        except (FileExistsError, OSError) as exc:
            raise RunStateError(f"preallocated run_id could not be reserved: {run_id}") from exc

    def _plan(self, contract: FabricTaskContract) -> ExecutionPlan:
        steps = tuple(ExecutionPlanStep(step_id=f"requirement:{item.requirement_id}", intent=item.description, requirement_ids=(item.requirement_id,)) for item in contract.requirements)
        plan = ExecutionPlan(plan_id=f"plan:{contract.task_id}", revision=contract.revision, steps=steps)
        plan.validate_against(tuple(item.requirement_id for item in contract.requirements))
        return plan


NormalFabricOrchestrator = FabricNormalOrchestrator

__all__ = ["FabricNormalOrchestrator", "FabricOrchestrationResult", "FabricOrchestrationStatus", "NormalFabricOrchestrator"]
