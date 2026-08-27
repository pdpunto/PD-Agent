"""Normal-run Brain preparation for Fabric tasks, provider-neutral and bounded."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import hashlib
import json
from typing import Any, Iterable, Mapping

from pd_agent.core import FabricTaskContract, RunState, TaskProgressLedger, ValidationViolation

from .models import KnowledgeEnvironment, KnowledgeNeed
from .precode import PreCodeKnowledgeNeedDeriver
from .retrieval import KnowledgeService
from .semantic_repair import SemanticRepairKnowledgeNeedDeriver


class BrainTrigger(StrEnum):
    PRE_CODE = "PRE_CODE"
    MATERIAL_PROJECT_DISCOVERY = "MATERIAL_PROJECT_DISCOVERY"
    BUILD_FAILURE = "BUILD_FAILURE"
    RUNTIME_FAILURE = "RUNTIME_FAILURE"
    PENDING_REQUIREMENT = "PENDING_REQUIREMENT"


@dataclass(frozen=True, slots=True)
class BrainOrchestrationResult:
    trigger: BrainTrigger
    brain_enabled: bool
    needs: tuple[KnowledgeNeed, ...] = ()
    retrieval_results: tuple[Any, ...] = ()
    selected: tuple[Any, ...] = ()
    context_bundle: Any | None = None
    provider_messages: tuple[Any, ...] = ()
    traces: tuple[Any, ...] = ()
    deduplicated: bool = False
    degraded: bool = False
    ledger: TaskProgressLedger | None = None

    @property
    def retrieved_count(self) -> int:
        return sum(len(getattr(result, "items", ())) for result in self.retrieval_results)

    @property
    def selected_count(self) -> int:
        return sum(len(getattr(selection, "selected_items", ())) for selection in self.selected)

    @property
    def injected_context_item_ids(self) -> tuple[str, ...]:
        if self.context_bundle is None:
            return ()
        return tuple(str(item.metadata.get("knowledge_item_id", item.label or "")) for item in self.context_bundle.items if item.source == "knowledge")


class FabricBrainOrchestrator:
    """Prepare bounded knowledge context for a normal Fabric run."""

    def __init__(
        self,
        *,
        knowledge_service: KnowledgeService | None = None,
        context_manager: Any | None = None,
        precode_deriver: PreCodeKnowledgeNeedDeriver | None = None,
        repair_deriver: SemanticRepairKnowledgeNeedDeriver | None = None,
        selector: Any | None = None,
        selection_budget_bytes: int = 8_192,
    ) -> None:
        if selection_budget_bytes <= 0:
            raise ValueError("selection_budget_bytes must be positive")
        from pd_agent.context import ContextManager, KnowledgeSelector

        self.knowledge_service = knowledge_service or KnowledgeService()
        self.context_manager = context_manager or ContextManager()
        self.precode_deriver = precode_deriver or PreCodeKnowledgeNeedDeriver(max_needs=8)
        self.repair_deriver = repair_deriver or SemanticRepairKnowledgeNeedDeriver(max_needs=4)
        self.selector = selector or KnowledgeSelector()
        self.selection_budget_bytes = selection_budget_bytes
        self._seen: set[tuple[str, str, str, str | None]] = set()

    def prepare(
        self,
        *,
        contract: FabricTaskContract,
        environment: KnowledgeEnvironment,
        ledger: TaskProgressLedger | None = None,
        run_state: RunState | None = None,
        trigger: BrainTrigger = BrainTrigger.PRE_CODE,
        failure: ValidationViolation | None = None,
        brain_enabled: bool = True,
        offline: bool = True,
        project_snapshot: Any | None = None,
    ) -> BrainOrchestrationResult:
        if not brain_enabled:
            return BrainOrchestrationResult(trigger=trigger, brain_enabled=False, ledger=ledger)
        needs = self._derive_needs(contract, environment, ledger, trigger, failure)
        failure_fingerprint = self._failure_fingerprint(failure)
        fresh: list[KnowledgeNeed] = []
        for need in needs:
            key = (need.id, self._environment_identity(environment), trigger.value, failure_fingerprint)
            if key in self._seen:
                continue
            self._seen.add(key)
            fresh.append(need)
        if not fresh:
            return BrainOrchestrationResult(trigger=trigger, brain_enabled=True, needs=tuple(needs), deduplicated=bool(needs), ledger=ledger)

        results: list[Any] = []
        selections: list[Any] = []
        for need in fresh:
            result = self.knowledge_service.resolve(need, offline=offline)
            results.append(result)
            selections.append(self.selector.select(result, budget_bytes=self.selection_budget_bytes, run_id=run_state.run_id if run_state else None))
        context_bundle = self.context_manager.build_context(
            project_snapshot=project_snapshot,
            run_state=run_state,
            external_context=tuple(selections),
        )
        traces = tuple(self.context_manager.last_knowledge_traces)
        updated_ledger = self._correlate_ledger(ledger, traces)
        degraded = any(bool(getattr(result, "error", None)) or bool(getattr(result, "degraded", False)) for result in results)
        return BrainOrchestrationResult(trigger=trigger, brain_enabled=True, needs=tuple(fresh), retrieval_results=tuple(results), selected=tuple(selections), context_bundle=context_bundle, provider_messages=context_bundle.to_messages(), traces=traces, degraded=degraded, ledger=updated_ledger)

    def _derive_needs(self, contract: FabricTaskContract, environment: KnowledgeEnvironment, ledger: TaskProgressLedger | None, trigger: BrainTrigger, failure: ValidationViolation | None) -> tuple[KnowledgeNeed, ...]:
        if trigger is BrainTrigger.BUILD_FAILURE and failure is not None:
            if failure.code.casefold() in {
                "build_timeout",
                "build_environment_failure",
                "build_dependency_failure",
            } or any(marker in failure.code.casefold() for marker in ("timeout", "environment", "infrastructure", "dependency")):
                return ()
            return self.repair_deriver.derive(failure, environment).needs
        task_text = " ".join((contract.goal, *(item.description for item in contract.requirements)))
        signals = [*contract.required_capabilities, *(item.query for item in contract.knowledge_signals)]
        if trigger is BrainTrigger.PENDING_REQUIREMENT and ledger is not None:
            pending = set(ledger.pending_requirement_ids(tuple(item.requirement_id for item in contract.requirements)))
            signals.extend(item.description for item in contract.requirements if item.requirement_id in pending and item.required)
        return self.precode_deriver.derive(task_text, environment, capability_signals=signals, metadata=contract.environment_constraints.to_dict()).needs

    def _correlate_ledger(self, ledger: TaskProgressLedger | None, traces: Iterable[Any]) -> TaskProgressLedger | None:
        if ledger is None:
            return None
        correlation = dict(ledger.knowledge_correlation)
        for trace in traces:
            for need in trace.needs:
                refs = tuple(dict.fromkeys((*correlation.get(need.id, ()), *trace.evidence_refs)))
                correlation[need.id] = refs
        return replace(ledger, knowledge_correlation=correlation)

    def _environment_identity(self, environment: KnowledgeEnvironment) -> str:
        payload = json.dumps(environment.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _failure_fingerprint(self, failure: ValidationViolation | None) -> str | None:
        if failure is None:
            return None
        payload = {"code": failure.code, "requirement": failure.requirement, "expected": failure.expected, "actual": failure.actual}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


__all__ = ["BrainOrchestrationResult", "BrainTrigger", "FabricBrainOrchestrator"]
