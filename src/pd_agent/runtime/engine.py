"""Single-agent execution loop for PD Agent."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from pd_agent.artifacts import ArtifactValidator
from pd_agent.build import GradleBuildRunner
from pd_agent.context import ContextItem, ContextManager
from pd_agent.core import (
    AgentMessage,
    AgentRequest,
    ArtifactResult,
    BuildResult,
    ExecutionLimits,
    ModelProvider,
    PreBuildValidator,
    FunctionalValidator,
    ProviderError,
    ProviderContinuation,
    RunState,
    RunStatus,
    ToolCall,
    ToolResult,
    ToolResultStatus,
    ValidationResult,
    ValidationStatus,
)
from pd_agent.core.errors import BuildError, LimitReachedError
from pd_agent.core.errors import ArtifactValidationError
from pd_agent.core.terminal_reasons import (
    REPEATED_ACTION_GATE_VIOLATION,
    REPEATED_BUILD_FAILURE,
    REPEATED_RECOVERABLE_TOOL_REJECTION,
    REPEATED_UNRESOLVED_MUTATION_TARGETS,
    TOOL_REJECTED,
)
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage
from pd_agent.tools import ToolExecutionContext, ToolExecutor, create_filesystem_tools


@dataclass(slots=True)
class _RetainedFileEvidence:
    path: str
    observed_step: int
    excerpt: str
    truncated: bool
    bytes_total: int | None = None
    kind: str = "file"

    @property
    def excerpt_bytes(self) -> int:
        return len(self.excerpt.encode("utf-8"))


@dataclass(slots=True)
class _LoopTelemetry:
    last_failure_signature: str | None = None
    failure_repeat_count: int = 0
    last_tool_signature: str | None = None
    tool_repeat_count: int = 0
    consecutive_inspection_steps: int = 0
    consecutive_gate_violations: int = 0
    consecutive_recoverable_rejections: int = 0
    recent_inspection_tools: tuple[str, ...] = ()
    recent_inspected_paths: tuple[str, ...] = ()
    last_operational_progress_step: int = 0
    action_pressure_level: str = "normal"
    retained_file_evidence: dict[str, _RetainedFileEvidence] = field(default_factory=dict)
    validation_repair_pending: bool = False
    validation_repair_mutated: bool = False


class ActionGateState(StrEnum):
    """Gradual tool-exposure gate for exploration drift."""

    NORMAL = "normal"
    ACTION_REQUIRED = "action_required"
    FOCUSED_ACTION = "focused_action"
    ACTION_ONLY = "action_only"
    STALLED = "stalled"


_INSPECTION_TOOLS = frozenset({"list_directory", "read_file", "search_text"})
_BROAD_INSPECTION_TOOLS = frozenset({"list_directory", "search_text"})
_ACTION_REQUIRED_STEP = 3
_FOCUSED_ACTION_STEP = 5
_ACTION_ONLY_STEP = 7
_ACTION_STALL_STEP = 8
_RECENT_HISTORY_LIMIT = 8
_MAX_RETAINED_FILE_EVIDENCE = 8
_MAX_RETAINED_FILE_EXCERPT_BYTES = 4096
_MAX_RETAINED_FILE_TOTAL_BYTES = 24576


class AgentRuntime:
    """Drive planning, editing, builds, diagnosis and validation."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        tool_executor: ToolExecutor | None = None,
        build_runner: GradleBuildRunner,
        artifact_validator: ArtifactValidator,
        context_manager: ContextManager,
        reporting: RunStorage | None = None,
        model_config: Mapping[str, Any] | None = None,
        filesystem_tools: Iterable[Any] = (),
        pre_build_validator: PreBuildValidator | None = None,
        functional_validator: FunctionalValidator | None = None,
        validation_contract: Any | None = None,
    ) -> None:
        self.provider = provider
        self.tool_executor = tool_executor or ToolExecutor(tools=tuple(filesystem_tools) or create_filesystem_tools())
        self.build_runner = build_runner
        self.artifact_validator = artifact_validator
        self.context_manager = context_manager
        self.reporting = reporting
        self.model_config = dict(model_config or {})
        self.pre_build_validator = pre_build_validator
        self.functional_validator = functional_validator
        self.validation_contract = validation_contract
        self._telemetry = _LoopTelemetry()
        self._knowledge_trace_hashes: dict[str, set[str]] = {}
        self._knowledge_trace_refs: dict[str, list[str]] = {}

    def run(
        self,
        *,
        run_state: RunState,
        project_snapshot: ProjectSnapshot,
        task: str,
        external_context: tuple[Any, ...] = (),
        limits: ExecutionLimits | None = None,
    ) -> tuple[RunState, FinalReport]:
        limits = limits or ExecutionLimits()
        self._telemetry = _LoopTelemetry()
        run_state.task = task
        run_state.project_snapshot = project_snapshot.to_dict()
        self._emit(run_state.run_id, RunEventType.STATE_CHANGED, {"state": run_state.state.value, "reason": "start"})
        self._persist_state(run_state)

        if project_snapshot.status == ProjectInspectionStatus.BLOCKED:
            run_state.state = RunStatus.BLOCKED
            run_state.termination_reason = "project inspection blocked"
            return self._finish(run_state, project_snapshot, limits, external_context)
        if project_snapshot.status == ProjectInspectionStatus.INCOMPATIBLE:
            run_state.state = RunStatus.FAILED
            run_state.termination_reason = "project inspection incompatible"
            return self._finish(run_state, project_snapshot, limits, external_context)

        run_state.transition_to(RunStatus.PLANNING)
        self._mark_state(run_state, "inspect complete")

        history: list[AgentMessage] = [AgentMessage(role="user", content=task)]
        pending_tool_calls: tuple[ToolCall, ...] = ()
        pending_tool_results: tuple[ToolResult, ...] = ()
        pending_provider_continuations: tuple[ProviderContinuation, ...] = ()
        editing_continuation_available = False
        try:
            while not run_state.state.is_terminal():
                self._check_limits(run_state, limits)

                if run_state.state in {RunStatus.PLANNING, RunStatus.DIAGNOSING, RunStatus.CORRECTING} or (
                    run_state.state == RunStatus.EDITING and editing_continuation_available
                ):
                    editing_continuation_available = False
                    response, offered_tool_names = self._call_provider(
                        run_state=run_state,
                        project_snapshot=project_snapshot,
                        limits=limits,
                        external_context=external_context,
                        history=history,
                        tool_calls=pending_tool_calls,
                        tool_results=pending_tool_results,
                        provider_continuations=pending_provider_continuations,
                    )
                    pending_tool_calls = ()
                    pending_tool_results = ()
                    pending_provider_continuations = ()
                    run_state.record_agent_step()
                    self._persist_state(run_state)
                    self._emit(
                        run_state.run_id,
                        RunEventType.MODEL_RESPONDED,
                        {
                            "assistant_message": response.assistant_message,
                            "tool_call_count": len(response.tool_calls),
                            "requested_tool_names": [call.tool_name for call in response.tool_calls],
                            "offered_tool_names": list(offered_tool_names),
                            "unavailable_tool_names": [
                                call.tool_name for call in response.tool_calls if call.tool_name not in set(offered_tool_names)
                            ],
                            "gate_violation": any(call.tool_name not in set(offered_tool_names) for call in response.tool_calls),
                            "consecutive_gate_violations": self._telemetry.consecutive_gate_violations,
                            "usage": response.usage,
                            "provider_metadata": response.provider_metadata,
                        },
                    )
                    if response.assistant_message:
                        history.append(AgentMessage(role="assistant", content=response.assistant_message))
                        if run_state.current_plan is None and run_state.state == RunStatus.PLANNING:
                            run_state.current_plan = response.assistant_message
                        elif run_state.state == RunStatus.DIAGNOSING:
                            run_state.last_error = response.assistant_message

                    tool_results = self._execute_tool_calls(
                        response.tool_calls,
                        run_state=run_state,
                        project_snapshot=project_snapshot,
                        limits=limits,
                        offered_tool_names=offered_tool_names,
                    )
                    if run_state.state.is_terminal():
                        self._persist_state(run_state)
                        break

                    recoverable_rejection = self._tool_results_have_recoverable_rejection(tool_results)
                    fatal_rejection = self._tool_results_have_fatal_rejection(tool_results)
                    if fatal_rejection:
                        run_state.state = RunStatus.FAILED
                        run_state.termination_reason = TOOL_REJECTED
                        break

                    self._record_action_telemetry(
                        run_state,
                        tool_calls=response.tool_calls,
                        tool_results=tool_results,
                    )
                    if run_state.state.is_terminal():
                        self._persist_state(run_state)
                        break

                    gate_violation_detected = any(result.metadata.get("gate_violation") for result in tool_results)
                    progress_detected = self._tool_results_have_change(tool_results)
                    if progress_detected and self._telemetry.validation_repair_pending:
                        self._telemetry.validation_repair_mutated = True
                    pending_tool_calls = response.tool_calls
                    pending_tool_results = tool_results
                    pending_provider_continuations = response.provider_continuations

                    if (
                        not response.tool_calls
                        and run_state.pending_mutation_targets
                        and run_state.state in {RunStatus.PLANNING, RunStatus.EDITING}
                    ):
                        unresolved_mutation_targets = list(run_state.pending_mutation_targets)
                        self._telemetry.consecutive_gate_violations += 1
                        message = (
                            "Required mutation targets remain unresolved: "
                            f"{unresolved_mutation_targets!r}. "
                            "Make a concrete modification for one of these targets before validation."
                        )
                        self._emit(
                            run_state.run_id,
                            RunEventType.ACTION_GATE_VIOLATION,
                            {
                                "requested_tool_names": [],
                                "offered_tool_names": list(offered_tool_names),
                                "unavailable_tool_names": [],
                                "gate_violation": True,
                                "unresolved_mutation_targets": unresolved_mutation_targets,
                                "message": message,
                            },
                        )
                        history.append(AgentMessage(role="user", content=message))
                        if self._telemetry.consecutive_gate_violations >= 2:
                            run_state.state = RunStatus.FAILED
                            run_state.termination_reason = (
                                REPEATED_UNRESOLVED_MUTATION_TARGETS
                            )
                            break
                        self._persist_state(run_state)
                        continue

                    if gate_violation_detected and not progress_detected:
                        if run_state.state == RunStatus.EDITING and run_state.pending_mutation_targets:
                            editing_continuation_available = True
                        self._persist_state(run_state)
                        continue

                    if recoverable_rejection and not progress_detected:
                        self._telemetry.consecutive_recoverable_rejections += 1
                        run_state.consecutive_recoverable_rejections = self._telemetry.consecutive_recoverable_rejections
                        if self._telemetry.consecutive_recoverable_rejections >= 2:
                            run_state.state = RunStatus.FAILED
                            run_state.termination_reason = REPEATED_RECOVERABLE_TOOL_REJECTION
                            break
                        if run_state.state == RunStatus.EDITING and run_state.pending_mutation_targets:
                            editing_continuation_available = True
                        self._persist_state(run_state)
                        continue

                    if (
                        run_state.state == RunStatus.PLANNING
                        and tool_results
                        and self._tool_results_are_inspection_only(tool_results)
                        and not self._tool_results_have_change(tool_results)
                    ):
                        self._persist_state(run_state)
                        continue

                    if run_state.state == RunStatus.PLANNING:
                        run_state.transition_to(RunStatus.EDITING)
                        if run_state.pending_mutation_targets:
                            editing_continuation_available = True
                    elif run_state.state == RunStatus.DIAGNOSING:
                        self._reset_action_pressure(run_state)
                        run_state.transition_to(RunStatus.CORRECTING if tool_results else RunStatus.FAILED)
                        if run_state.state == RunStatus.FAILED:
                            run_state.termination_reason = "diagnosis produced no correction"
                    elif run_state.state == RunStatus.CORRECTING:
                        if self._telemetry.validation_repair_pending:
                            if self._telemetry.validation_repair_mutated:
                                self._telemetry.validation_repair_pending = False
                                self._telemetry.validation_repair_mutated = False
                                run_state.transition_to(RunStatus.EDITING)
                            else:
                                # Inspection is a valid repair step; keep the repair
                                # phase open until progress or an existing stall limit.
                                run_state.transition_to(RunStatus.EDITING)
                                editing_continuation_available = True
                        else:
                            run_state.transition_to(RunStatus.BUILDING)
                    elif run_state.state == RunStatus.EDITING:
                        if self._telemetry.validation_repair_pending:
                            if self._telemetry.validation_repair_mutated:
                                self._telemetry.validation_repair_pending = False
                                self._telemetry.validation_repair_mutated = False
                            else:
                                editing_continuation_available = True
                                self._persist_state(run_state)
                                continue
                        if run_state.pending_mutation_targets:
                            editing_continuation_available = True
                        else:
                            validation_status = self._run_prebuild_validation(run_state, project_snapshot, history)
                            if validation_status == "PASS":
                                run_state.transition_to(RunStatus.BUILDING)
                            elif validation_status == "BLOCKED" or run_state.state.is_terminal():
                                self._persist_state(run_state)
                                break
                    self._persist_state(run_state)
                    continue

                if run_state.state == RunStatus.EDITING:
                    if run_state.pending_mutation_targets:
                        editing_continuation_available = True
                        self._persist_state(run_state)
                        continue
                    validation_status = self._run_prebuild_validation(run_state, project_snapshot, history)
                    if validation_status != "PASS":
                        self._persist_state(run_state)
                        if validation_status == "BLOCKED" or run_state.state.is_terminal():
                            break
                        continue
                    run_state.transition_to(RunStatus.BUILDING)
                    self._persist_state(run_state)
                    continue

                if run_state.state == RunStatus.BUILDING:
                    if run_state.pending_mutation_targets:
                        run_state.state = RunStatus.FAILED
                        run_state.termination_reason = "pending mutation targets block build"
                        self._emit(
                            run_state.run_id,
                            RunEventType.ACTION_GATE_VIOLATION,
                            {
                                "gate_violation": True,
                                "unresolved_mutation_targets": list(run_state.pending_mutation_targets),
                                "message": "Build blocked until all required mutation targets are completed.",
                            },
                        )
                        self._persist_state(run_state)
                        break
                    self._check_limits(run_state, limits)
                    build_result = self.build_runner.run(project_snapshot, run_state, limits)
                    self._observe_progress(run_state, build_result=build_result)
                    self._record_action_telemetry(
                        run_state,
                        build_result=build_result,
                    )
                    if run_state.state.is_terminal():
                        self._persist_state(run_state)
                        break
                    if build_result.success:
                        run_state.transition_to(RunStatus.VALIDATING_ARTIFACT)
                    else:
                        if run_state.build_attempt_count >= limits.max_build_attempts:
                            run_state.state = RunStatus.LIMIT_REACHED
                            run_state.termination_reason = "max_build_attempts reached"
                            break
                        self._reset_action_pressure(run_state)
                        run_state.transition_to(RunStatus.DIAGNOSING)
                        run_state.last_error = build_result.stderr_log or build_result.stdout_log or f"build failed with exit_code {build_result.exit_code}"
                    self._persist_state(run_state)
                    continue

                if run_state.state == RunStatus.VALIDATING_ARTIFACT:
                    self._check_limits(run_state, limits)
                    final_build = run_state.build_results[-1] if run_state.build_results else None
                    if final_build is None:
                        run_state.state = RunStatus.FAILED
                        run_state.termination_reason = "missing build result for artifact validation"
                        break
                    artifact = self.artifact_validator.validate(project_snapshot, final_build, run_id=run_state.run_id)
                    run_state.artifact_result = artifact
                    self._emit(
                        run_state.run_id,
                        RunEventType.ARTIFACT_VALIDATED,
                        {"classification": artifact.classification, "valid": artifact.classification == "VALID"},
                    )
                    if artifact.classification == "VALID":
                        run_state.transition_to(
                            RunStatus.VALIDATING_FUNCTIONAL
                            if self.functional_validator is not None
                            else RunStatus.REPORTING
                        )
                        self._persist_state(run_state)
                        continue
                    run_state.state = RunStatus.FAILED
                    run_state.termination_reason = "artifact validation failed"
                    break

                if run_state.state == RunStatus.VALIDATING_FUNCTIONAL:
                    self._check_limits(run_state, limits)
                    functional_status = self._run_functional_validation(run_state, project_snapshot, history)
                    if functional_status == "PASS":
                        run_state.transition_to(RunStatus.REPORTING)
                        self._persist_state(run_state)
                        continue
                    if functional_status in {"BLOCKED", "FAILED"} or run_state.state.is_terminal():
                        self._persist_state(run_state)
                        break
                    self._persist_state(run_state)
                    continue

                if run_state.state == RunStatus.REPORTING:
                    run_state.state = RunStatus.COMPLETED
                    run_state.termination_reason = "completed"
                    break

                if run_state.state in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.BLOCKED, RunStatus.LIMIT_REACHED, RunStatus.ABORTED}:
                    break

                raise BuildError(f"unhandled runtime state: {run_state.state.value}")
        except LimitReachedError as exc:
            run_state.state = RunStatus.LIMIT_REACHED
            run_state.termination_reason = str(exc)
        except (ProviderError, BuildError, ArtifactValidationError) as exc:
            if run_state.state not in {RunStatus.FAILED, RunStatus.BLOCKED, RunStatus.LIMIT_REACHED, RunStatus.ABORTED}:
                run_state.state = RunStatus.FAILED
            run_state.last_error = str(exc)
            if isinstance(exc, ProviderError):
                run_state.provider_error_kind = exc.kind
                run_state.provider_error_message = exc.message
            run_state.termination_reason = str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            run_state.state = RunStatus.FAILED
            run_state.last_error = f"{type(exc).__name__}: {exc}"
            run_state.termination_reason = "internal error"

        return self._finish(run_state, project_snapshot, limits, external_context)

    def _call_provider(
        self,
        *,
        run_state: RunState,
        project_snapshot: ProjectSnapshot,
        limits: ExecutionLimits,
        external_context: tuple[Any, ...],
        history: list[AgentMessage],
        tool_calls: tuple[ToolCall, ...],
        tool_results: tuple[ToolResult, ...],
        provider_continuations: tuple[ProviderContinuation, ...],
    ) -> tuple[Any, tuple[str, ...]]:
        gate_state = self._action_gate_state(self._telemetry)
        policy_context = self._build_action_transition_context(run_state, limits, gate_state)
        tool_specs = tuple(self._tool_specs(gate_state))
        offered_tool_names = tuple(spec["name"] for spec in tool_specs)
        retained_evidence_context = self._retained_file_evidence_context_items()
        bundle = self.context_manager.build_context(
            project_snapshot=project_snapshot,
            run_state=run_state,
            external_context=(policy_context, *retained_evidence_context, *external_context),
            limits=limits,
        )
        self._persist_knowledge_traces(run_state.run_id)
        messages = bundle.to_messages() + tuple(history)
        request = AgentRequest(
            messages=messages,
            tool_calls=tool_calls,
            tool_results=tool_results,
            provider_continuations=provider_continuations,
            tools=tool_specs,
            model_config=self._model_config(run_state, limits),
        )
        self._emit(
            run_state.run_id,
            RunEventType.MODEL_CALLED,
            {
                "phase": run_state.state.value,
                "message_count": len(request.messages),
                "tool_count": len(request.tools),
                "model_config": self._safe_model_config(request.model_config),
                "action_gate_state": gate_state.value,
                "escalation_state": gate_state.value,
                "action_required": gate_state != ActionGateState.NORMAL,
                "consecutive_inspection_steps": self._telemetry.consecutive_inspection_steps,
                "consecutive_recoverable_rejections": self._telemetry.consecutive_recoverable_rejections,
                "consecutive_gate_violations": self._telemetry.consecutive_gate_violations,
                "agent_steps_remaining": max(limits.max_agent_steps - run_state.agent_step_count, 0),
                "tool_calls_remaining": max(limits.max_tool_calls - run_state.tool_call_count, 0),
                "build_attempts_remaining": max(limits.max_build_attempts - run_state.build_attempt_count, 0),
                "offered_tool_names": list(offered_tool_names),
            },
        )
        run_state.record_logical_provider_request()
        self._persist_state(run_state)
        try:
            return self.provider.execute(request), offered_tool_names
        except ProviderError as exc:
            run_state.state = RunStatus.FAILED
            run_state.provider_error_kind = exc.kind
            run_state.provider_error_message = exc.message
            run_state.termination_reason = "provider error"
            raise

    def _persist_knowledge_traces(self, run_id: str) -> None:
        traces = getattr(self.context_manager, "last_knowledge_traces", ())
        if not traces or self.reporting is None:
            return
        seen = self._knowledge_trace_hashes.setdefault(run_id, set())
        refs = self._knowledge_trace_refs.setdefault(run_id, [])
        paths = self.reporting.paths_for(run_id)
        for trace in traces:
            payload = trace.to_dict()
            digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            evidence_path = self.reporting.store_large_payload(
                run_id,
                "knowledge-trace",
                payload,
                sequence=len(refs) + 1,
            )
            refs.append(evidence_path.relative_to(paths.root).as_posix())

    def _execute_tool_calls(
        self,
        tool_calls: tuple[ToolCall, ...],
        *,
        run_state: RunState,
        project_snapshot: ProjectSnapshot,
        limits: ExecutionLimits,
        offered_tool_names: tuple[str, ...],
    ) -> tuple[ToolResult, ...]:
        if not tool_calls:
            return ()
        offered_tool_name_set = set(offered_tool_names)
        requested_tool_names = tuple(call.tool_name for call in tool_calls)
        unavailable_tool_names = tuple(
            dict.fromkeys(call.tool_name for call in tool_calls if call.tool_name not in offered_tool_name_set)
        )
        if unavailable_tool_names:
            self._emit(
                run_state.run_id,
                RunEventType.ACTION_GATE_VIOLATION,
                {
                    "requested_tool_names": list(requested_tool_names),
                    "offered_tool_names": list(offered_tool_names),
                    "unavailable_tool_names": list(unavailable_tool_names),
                    "gate_violation": True,
                    "message": (
                        f"Tool(s) {list(unavailable_tool_names)!r} are not available in the current action gate. "
                        "Choose one of the offered tools or return no tool call."
                    ),
                },
            )
        context = ToolExecutionContext(project_root=project_snapshot.project_root, limits=limits, run_id=run_state.run_id)
        results: list[ToolResult] = []
        for call in tool_calls:
            self._check_limits(run_state, limits)
            if call.tool_name not in offered_tool_name_set:
                results.append(
                    ToolResult(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        status=ToolResultStatus.ERROR,
                        error=(
                            f"Tool '{call.tool_name}' is not available in the current action gate. "
                            "Choose one of the offered tools or return no tool call."
                        ),
                        metadata={
                            "gate_violation": True,
                            "requested_tool_names": list(requested_tool_names),
                            "offered_tool_names": list(offered_tool_names),
                            "unavailable_tool_names": list(unavailable_tool_names),
                        },
                    )
                )
                continue
            result = self.tool_executor.execute(call, context)
            results.append(result)
            run_state.record_tool_call()
            self._record_retained_file_evidence(run_state, result)
            self._record_changed_files(run_state, result)
            self._record_completed_mutation_target(run_state, result)
            self._persist_state(run_state)
            self._observe_progress(
                run_state,
                tool_results=(result,),
                recoverable_rejection=result.status == ToolResultStatus.REJECTED and result.metadata.get("rejection_code") == "file_exists",
            )
            if run_state.state.is_terminal():
                break
        return tuple(results)

    def _record_completed_mutation_target(self, run_state: RunState, result: ToolResult) -> None:
        if (
            result.status != ToolResultStatus.SUCCESS
            or not result.metadata.get("changed")
            or result.tool_name not in {
                "write_file",
                "create_file",
            }
        ):
            return
        path = result.metadata.get("path")
        if path is None and isinstance(result.output, Mapping):
            path = result.output.get("path")
        if path is not None:
            run_state.record_completed_mutation_target(path)

    def _record_changed_files(self, run_state: RunState, result: ToolResult) -> None:
        if result.status != ToolResultStatus.SUCCESS:
            return
        if not result.metadata.get("changed"):
            return
        path = result.metadata.get("path")
        if path is None and isinstance(result.output, Mapping):
            path = result.output.get("path")
        if path is None:
            return
        run_state.record_changed_file(path)

    def _record_retained_file_evidence(self, run_state: RunState, result: ToolResult) -> None:
        if result.status != ToolResultStatus.SUCCESS:
            return

        if result.metadata.get("changed"):
            self._remove_retained_file_evidence(result)

        if result.tool_name != "read_file":
            return

        output = result.output if isinstance(result.output, Mapping) else {}
        path = output.get("path")
        content = output.get("content")
        if path is None or content is None:
            return

        excerpt, excerpt_truncated = self._truncate_utf8_prefix(str(content), _MAX_RETAINED_FILE_EXCERPT_BYTES)
        bytes_total = output.get("bytes_total")
        try:
            normalized_bytes_total = int(bytes_total) if bytes_total is not None else None
        except (TypeError, ValueError):
            normalized_bytes_total = None

        self._telemetry.retained_file_evidence[str(path)] = _RetainedFileEvidence(
            path=str(path),
            observed_step=run_state.agent_step_count,
            excerpt=excerpt,
            truncated=bool(output.get("truncated", False)) or excerpt_truncated,
            bytes_total=normalized_bytes_total,
        )
        self._prune_retained_file_evidence()

    def _remove_retained_file_evidence(self, result: ToolResult) -> None:
        path = result.metadata.get("path")
        if path is None and isinstance(result.output, Mapping):
            path = result.output.get("path")
        if path is None:
            return
        self._telemetry.retained_file_evidence.pop(str(path), None)

    def _prune_retained_file_evidence(self) -> None:
        while self._telemetry.retained_file_evidence:
            entries = self._sorted_retained_file_evidence()
            total_bytes = sum(entry.excerpt_bytes for entry in entries)
            if len(entries) <= _MAX_RETAINED_FILE_EVIDENCE and total_bytes <= _MAX_RETAINED_FILE_TOTAL_BYTES:
                return
            oldest = entries[0]
            self._telemetry.retained_file_evidence.pop(oldest.path, None)

    def _sorted_retained_file_evidence(self) -> tuple[_RetainedFileEvidence, ...]:
        return tuple(
            sorted(
                self._telemetry.retained_file_evidence.values(),
                key=lambda entry: (entry.observed_step, entry.path),
            )
        )

    def _retained_file_evidence_paths(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self._sorted_retained_file_evidence())

    def _retained_file_evidence_context_items(self) -> tuple[ContextItem, ...]:
        entries = self._sorted_retained_file_evidence()
        if not entries:
            return ()

        total_bytes = sum(entry.excerpt_bytes for entry in entries)
        items: list[ContextItem] = [
            ContextItem.from_text(
                source="runtime",
                priority=6,
                label="retained-inspection-evidence",
                content="\n".join(
                    [
                        f"retained_file_count: {len(entries)}",
                        f"retained_total_excerpt_bytes: {total_bytes}",
                        f"retained_paths: {[entry.path for entry in entries]}",
                    ]
                ),
                metadata={
                    "retained_file_count": len(entries),
                    "retained_total_excerpt_bytes": total_bytes,
                    "retained_paths": [entry.path for entry in entries],
                },
            )
        ]
        for entry in entries:
            items.append(
                ContextItem.from_text(
                    source="runtime",
                    priority=7,
                    label=f"retained-file:{entry.path}",
                    content="\n".join(
                        [
                            f"path: {entry.path}",
                            f"kind: {entry.kind}",
                            f"observed_step: {entry.observed_step}",
                            f"truncated: {entry.truncated}",
                            f"bytes_total: {entry.bytes_total}",
                            "excerpt:",
                            entry.excerpt,
                        ]
                    ),
                    metadata={
                        "path": entry.path,
                        "kind": entry.kind,
                        "observed_step": entry.observed_step,
                        "truncated": entry.truncated,
                        "bytes_total": entry.bytes_total,
                        "excerpt_bytes": entry.excerpt_bytes,
                    },
                    truncated=entry.truncated,
                )
            )
        return tuple(items)

    def _truncate_utf8_prefix(self, text: str, limit_bytes: int) -> tuple[str, bool]:
        if limit_bytes <= 0:
            return "", bool(text)
        encoded = text.encode("utf-8")
        if len(encoded) <= limit_bytes:
            return text, False
        chunk = encoded[:limit_bytes]
        while chunk:
            try:
                return chunk.decode("utf-8"), True
            except UnicodeDecodeError as exc:
                chunk = chunk[:exc.start]
        return "", True

    def _finish(
        self,
        run_state: RunState,
        project_snapshot: ProjectSnapshot,
        limits: ExecutionLimits,
        external_context: tuple[Any, ...],
    ) -> tuple[RunState, FinalReport]:
        if not run_state.state.is_terminal():
            run_state.state = RunStatus.FAILED
            run_state.termination_reason = run_state.termination_reason or "runtime finished without terminal state"
        summary = self._summary(run_state)
        report = FinalReport(
            run_id=run_state.run_id,
            final_state=run_state.state,
            summary=summary,
            project=str(project_snapshot.project_root),
            requested_task=run_state.task,
            files_changed=run_state.changed_files,
            build_attempts=run_state.build_results,
            final_build=run_state.build_results[-1] if run_state.build_results else None,
            artifact=run_state.artifact_result,
            validation_results=run_state.validation_results,
            limits_usage=self._limits_usage(run_state, limits),
            warnings=(),
            termination_reason=run_state.termination_reason,
            evidence_refs=tuple(self._knowledge_trace_refs.get(run_state.run_id, ())),
        )
        if self.reporting is not None:
            self.reporting.write_run_state(run_state)
            self.reporting.write_final_report(report)
            self._emit(run_state.run_id, RunEventType.RUN_FINISHED, {"final_state": run_state.state.value, "summary": summary})
        return run_state, report

    def _run_prebuild_validation(
        self,
        run_state: RunState,
        project_snapshot: ProjectSnapshot,
        history: list[AgentMessage],
    ) -> str:
        if self.pre_build_validator is None:
            return "PASS"
        result = self.pre_build_validator.validate(
            project_snapshot.project_root,
            self.validation_contract,
        )
        if not isinstance(result, ValidationResult):
            raise TypeError("pre-build validator must return ValidationResult")
        signature = self._validation_signature(result)
        run_state.record_validation_result(result, signature)
        self._emit(
            run_state.run_id,
            RunEventType.VALIDATION_COMPLETED,
            {"result": result.to_dict(), "signature": signature},
        )
        if result.status == ValidationStatus.PASS:
            return "PASS"
        if result.status == ValidationStatus.BLOCKED:
            run_state.state = RunStatus.BLOCKED
            run_state.termination_reason = "pre-build validation blocked"
            return "BLOCKED"

        if run_state.validation_repeat_count >= 1:
            run_state.state = RunStatus.FAILED
            run_state.termination_reason = "repeated semantic validation failure"
            return "FAILED"
        feedback = self._validation_feedback(result)
        self._emit(
            run_state.run_id,
            RunEventType.SEMANTIC_REPAIR_FEEDBACK,
            {"stage": result.stage.value, "signature": signature, "feedback": feedback},
        )
        history.append(AgentMessage(role="user", content=feedback))
        self._telemetry.validation_repair_pending = True
        self._telemetry.validation_repair_mutated = False
        self._reset_action_pressure(run_state)
        run_state.transition_to(RunStatus.CORRECTING)
        return "REPAIR"

    def _run_functional_validation(
        self,
        run_state: RunState,
        project_snapshot: ProjectSnapshot,
        history: list[AgentMessage],
    ) -> str:
        validator = self.functional_validator
        artifact = run_state.artifact_result
        if validator is None:
            return "PASS"
        if artifact is None:
            run_state.state = RunStatus.BLOCKED
            run_state.termination_reason = "functional validation missing artifact"
            return "BLOCKED"
        result = validator.validate(
            project_snapshot.project_root,
            artifact,
            self.validation_contract,
            run_state.run_id,
        )
        if not isinstance(result, ValidationResult):
            raise TypeError("functional validator must return ValidationResult")
        staged_results = getattr(validator, "last_results", (result,))
        if not isinstance(staged_results, (tuple, list)):
            staged_results = (result,)
        if result not in staged_results:
            staged_results = (*staged_results, result)
        for staged_result in staged_results:
            if not isinstance(staged_result, ValidationResult):
                raise TypeError("functional validator last_results must contain ValidationResult")
            signature = self._validation_signature(staged_result)
            run_state.record_validation_result(staged_result, signature)
            self._emit(
                run_state.run_id,
                RunEventType.VALIDATION_COMPLETED,
                {"result": staged_result.to_dict(), "signature": signature},
            )
            if staged_result.status == ValidationStatus.BLOCKED:
                run_state.state = RunStatus.BLOCKED
                run_state.termination_reason = "functional validation blocked"
                return "BLOCKED"
            if staged_result.status == ValidationStatus.REPAIRABLE_FAIL:
                if run_state.validation_repeat_count >= 1:
                    run_state.state = RunStatus.FAILED
                    run_state.termination_reason = "repeated semantic validation failure"
                    return "FAILED"
                feedback = self._functional_validation_feedback(staged_result)
                self._emit(
                    run_state.run_id,
                    RunEventType.SEMANTIC_REPAIR_FEEDBACK,
                    {"stage": staged_result.stage.value, "signature": signature, "feedback": feedback},
                )
                history.append(AgentMessage(role="user", content=feedback))
                self._telemetry.validation_repair_pending = True
                self._telemetry.validation_repair_mutated = False
                self._reset_action_pressure(run_state)
                run_state.transition_to(RunStatus.CORRECTING)
                return "REPAIR"
        run_state.reset_validation_stall()
        return "PASS"

    def _functional_validation_feedback(self, result: ValidationResult) -> str:
        lines = [f"{result.stage.value.title().replace('_', ' ')} validation failed:"]
        for violation in result.violations:
            lines.append(f"- {violation.requirement}: {violation.message}")
        return "\n".join(lines)

    def _validation_feedback(self, result: ValidationResult) -> str:
        lines = ["Semantic validation failed before build:"]
        for violation in result.violations:
            lines.append(
                f"- {violation.code}: {violation.requirement}; {violation.message}"
            )
        return "\n".join(lines)

    def _validation_signature(self, result: ValidationResult) -> str:
        payload = {
            "stage": result.stage.value,
            "violations": [
                {
                    "code": violation.code,
                    "requirement": violation.requirement,
                    "observed_category": self._observed_category(violation.observed),
                }
                for violation in result.violations
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _observed_category(self, observed: Any) -> str:
        if isinstance(observed, Mapping):
            category = observed.get("category")
            if category is not None:
                return str(category)
            if "present" in observed:
                return "present" if bool(observed["present"]) else "missing"
        return type(observed).__name__

    def _tool_specs(self, gate_state: ActionGateState) -> Iterable[Mapping[str, Any]]:
        for tool in self.tool_executor._tools.values():  # noqa: SLF001
            if gate_state == ActionGateState.FOCUSED_ACTION and tool.name in _BROAD_INSPECTION_TOOLS:
                continue
            if gate_state in {ActionGateState.ACTION_ONLY, ActionGateState.STALLED} and tool.name in _INSPECTION_TOOLS:
                continue
            yield {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }

    def _model_config(self, run_state: RunState, limits: ExecutionLimits) -> dict[str, Any]:
        config = dict(self.model_config)
        if run_state.current_plan:
            config.setdefault("instructions", run_state.current_plan)
        config.setdefault("provider_retry_limit", limits.provider_retry_limit)
        return config

    def _safe_model_config(self, model_config: Mapping[str, Any]) -> dict[str, Any]:
        safe = {}
        for key in ("model", "instructions", "temperature", "top_p", "max_output_tokens", "provider_retry_limit"):
            if key in model_config:
                safe[key] = model_config[key]
        return safe

    def _tool_results_have_rejection(self, tool_results: tuple[ToolResult, ...]) -> bool:
        return any(result.status == ToolResultStatus.REJECTED for result in tool_results)

    def _tool_results_have_recoverable_rejection(self, tool_results: tuple[ToolResult, ...]) -> bool:
        return any(
            result.status == ToolResultStatus.REJECTED and result.metadata.get("rejection_code") == "file_exists"
            for result in tool_results
        )

    def _tool_results_have_fatal_rejection(self, tool_results: tuple[ToolResult, ...]) -> bool:
        return any(
            result.status == ToolResultStatus.REJECTED and result.metadata.get("rejection_code") != "file_exists"
            for result in tool_results
        )

    def _tool_results_have_change(self, tool_results: tuple[ToolResult, ...]) -> bool:
        return any(result.status == ToolResultStatus.SUCCESS and result.metadata.get("changed") for result in tool_results)

    def _tool_results_are_inspection_only(self, tool_results: tuple[ToolResult, ...]) -> bool:
        inspection_tools = {"read_file", "list_directory", "search_text"}
        return all(result.tool_name in inspection_tools for result in tool_results)

    def _summary(self, run_state: RunState) -> str:
        return f"state={run_state.state.value} steps={run_state.agent_step_count} tools={run_state.tool_call_count} builds={run_state.build_attempt_count}"

    def _build_action_transition_context(self, run_state: RunState, limits: ExecutionLimits, gate_state: ActionGateState) -> ContextItem:
        telemetry = self._telemetry
        remaining_agent_steps = max(limits.max_agent_steps - run_state.agent_step_count, 0)
        remaining_tool_calls = max(limits.max_tool_calls - run_state.tool_call_count, 0)
        remaining_build_attempts = max(limits.max_build_attempts - run_state.build_attempt_count, 0)
        policy_lines = self._action_policy_lines(run_state, telemetry, gate_state)
        content_lines = [
            f"phase: {run_state.state.value}",
            "budget:",
            f"- agent_steps_used: {run_state.agent_step_count}",
            f"- agent_steps_max: {limits.max_agent_steps}",
            f"- agent_steps_remaining: {remaining_agent_steps}",
            f"- tool_calls_used: {run_state.tool_call_count}",
            f"- tool_calls_max: {limits.max_tool_calls}",
            f"- tool_calls_remaining: {remaining_tool_calls}",
            f"- build_attempts_used: {run_state.build_attempt_count}",
            f"- pending_mutation_target_count: {len(run_state.pending_mutation_targets)}",
            f"- completed_mutation_target_count: {len(run_state.completed_mutation_targets)}",
            f"- build_attempts_max: {limits.max_build_attempts}",
            f"- build_attempts_remaining: {remaining_build_attempts}",
            "progress:",
            f"- files_changed: {list(run_state.changed_files)}",
            f"- build_attempted: {bool(run_state.build_results)}",
            f"- retained_inspection_evidence_count: {len(self._telemetry.retained_file_evidence)}",
            f"- retained_inspection_evidence_paths: {list(self._retained_file_evidence_paths())}",
            f"- consecutive_inspection_steps: {telemetry.consecutive_inspection_steps}",
            f"- recent_inspection_tools: {list(telemetry.recent_inspection_tools)}",
            f"- recent_inspected_paths: {list(telemetry.recent_inspected_paths)}",
            f"- consecutive_recoverable_rejections: {telemetry.consecutive_recoverable_rejections}",
            f"- last_operational_progress_step: {telemetry.last_operational_progress_step}",
            f"- consecutive_gate_violations: {telemetry.consecutive_gate_violations}",
            f"- action_gate_state: {gate_state.value}",
            f"- escalation_state: {telemetry.action_pressure_level}",
            "policy:",
            *policy_lines,
        ]
        return ContextItem.from_text(
            source="runtime",
            priority=5,
            label="action-transition-policy",
            content="\n".join(content_lines),
            metadata={
                "phase": run_state.state.value,
                "agent_steps_remaining": remaining_agent_steps,
                "tool_calls_remaining": remaining_tool_calls,
                "build_attempts_remaining": remaining_build_attempts,
                "consecutive_inspection_steps": telemetry.consecutive_inspection_steps,
                "consecutive_recoverable_rejections": telemetry.consecutive_recoverable_rejections,
                "consecutive_gate_violations": telemetry.consecutive_gate_violations,
                "action_gate_state": gate_state.value,
                "escalation_state": telemetry.action_pressure_level,
                "action_required": gate_state != ActionGateState.NORMAL,
            },
        )

    def _action_policy_lines(self, run_state: RunState, telemetry: _LoopTelemetry, gate_state: ActionGateState) -> tuple[str, ...]:
        if run_state.state == RunStatus.DIAGNOSING:
            phase_goal = "Investigate the build error only as needed to choose a concrete correction."
            phase_rules = (
                "- Use build errors as evidence for the next fix.",
                "- Inspect only the files or symbols directly implicated by the failure.",
                "- Once the cause is understood, correct it and return to build.",
            )
        elif run_state.state == RunStatus.CORRECTING:
            phase_goal = "Apply the concrete correction suggested by the diagnosis and build again."
            phase_rules = (
                "- Make the smallest plausible change that addresses the verified cause.",
                "- Prefer a quick build after the edit.",
                "- Do not keep re-reading the same files without new evidence.",
            )
        elif run_state.state == RunStatus.EDITING:
            phase_goal = "Make the concrete change implied by the gathered evidence."
            phase_rules = (
                "- Prefer an implementable edit over more exploration.",
                "- Keep the change minimal and directly tied to the task.",
                "- Build early after a plausible edit.",
            )
        else:
            phase_goal = "Gather only enough evidence to choose and execute the next concrete action."
            phase_rules = (
                "- Inspect only what is directly required for the task.",
                "- Do not repeat equivalent exploration without new evidence.",
                "- Once evidence is sufficient, perform a concrete modification.",
                "- Prefer an early build after a plausible implementation.",
            )
        mutation_rules = (
            "- File mutation tool selection:",
            "- existing path or observed existing file -> write_file",
            "- genuinely new/nonexistent path -> create_file",
            "- never use create_file to replace an existing file",
            "- use recent_inspected_paths as guidance, but treat only an observed file as an existing target.",
            "- prefer files and symbols directly supported by the task and retained inspection evidence.",
            "- preserve unrelated structure, declarations, metadata, configuration, entrypoints and public contracts unless verified evidence shows they are implicated.",
            "- when rewriting an existing file, keep non-target content and contracts intact unless the verified fix requires changing them.",
            "- if the evidence is insufficient to choose a target confidently, inspect only the specific blocker or validate the current state with a build.",
        )
        escalation_rules = self._escalation_policy_lines(gate_state)
        return (
            f"- current_phase: {run_state.state.value}",
            f"- goal: {phase_goal}",
            "- inspection alone is not progress.",
            *phase_rules,
            *mutation_rules,
            "- Use actual build errors as evidence for subsequent correction.",
            *escalation_rules,
        )

    def _escalation_policy_lines(self, gate_state: ActionGateState) -> tuple[str, ...]:
        if gate_state == ActionGateState.ACTION_REQUIRED:
            return (
                "ACTION REQUIRED: Investigation has consumed several consecutive steps without operational progress.",
                "Use the evidence already gathered to perform a concrete modification or other task-directed action now, unless a specific unresolved blocker requires further inspection.",
                "If further inspection is required, identify the specific unresolved blocker and inspect only what is needed to resolve it.",
            )
        if gate_state == ActionGateState.FOCUSED_ACTION:
            return (
                "FOCUSED ACTION: Broad exploration is no longer available. Read only a specific file if a concrete unresolved blocker requires it; otherwise modify the project or finish the turn so the runtime can attempt a build.",
            )
        if gate_state == ActionGateState.ACTION_ONLY:
            return (
                "ACTION ONLY: The investigation budget for this phase is exhausted. Make the best concrete task-directed modification supported by the evidence already gathered, or return no tool call so the runtime can validate the current state with a build.",
            )
        if gate_state == ActionGateState.STALLED:
            return (
                "STALL WARNING: exploration has continued without operational progress.",
                "Stop broad inspection and either act on the best evidence available or identify the specific blocker that still prevents action.",
            )
        return ()

    def _limits_usage(self, run_state: RunState, limits: ExecutionLimits) -> dict[str, int]:
        return {
            "agent_steps": run_state.agent_step_count,
            "logical_provider_request_count": run_state.logical_provider_request_count,
            "tool_calls": run_state.tool_call_count,
            "build_attempts": run_state.build_attempt_count,
            "max_agent_steps": limits.max_agent_steps,
            "max_tool_calls": limits.max_tool_calls,
            "max_build_attempts": limits.max_build_attempts,
        }

    def _observe_progress(
        self,
        run_state: RunState,
        *,
        tool_results: tuple[ToolResult, ...] = (),
        build_result: BuildResult | None = None,
        recoverable_rejection: bool = False,
    ) -> None:
        if tool_results:
            if recoverable_rejection:
                return
            if any(result.status == ToolResultStatus.SUCCESS and result.metadata.get("changed") for result in tool_results):
                self._telemetry.last_tool_signature = None
                self._telemetry.tool_repeat_count = 0
                run_state.reset_validation_stall()
            else:
                signature = self._tool_signature(tool_results)
                if signature == self._telemetry.last_tool_signature:
                    self._telemetry.tool_repeat_count += 1
                else:
                    self._telemetry.last_tool_signature = signature
                    self._telemetry.tool_repeat_count = 0
                if self._telemetry.tool_repeat_count >= 1:
                    run_state.state = RunStatus.FAILED
                    run_state.termination_reason = (
                        "semantic repair produced no mutation"
                        if self._telemetry.validation_repair_pending
                        else "repeated no-op tool calls"
                    )
                    return

        if build_result is not None:
            if build_result.success:
                self._telemetry.last_failure_signature = None
                self._telemetry.failure_repeat_count = 0
                return
            signature = self._build_failure_signature(build_result)
            if signature == self._telemetry.last_failure_signature:
                self._telemetry.failure_repeat_count += 1
            else:
                self._telemetry.last_failure_signature = signature
                self._telemetry.failure_repeat_count = 0
            if self._telemetry.failure_repeat_count >= 1:
                run_state.state = RunStatus.FAILED
                run_state.termination_reason = REPEATED_BUILD_FAILURE
                return

    def _record_action_telemetry(
        self,
        run_state: RunState,
        *,
        tool_calls: tuple[ToolCall, ...] = (),
        tool_results: tuple[ToolResult, ...] = (),
        build_result: BuildResult | None = None,
    ) -> None:
        progress_detected = False
        if build_result is not None and build_result.success:
            progress_detected = True
            self._telemetry.last_operational_progress_step = run_state.agent_step_count
        if tool_results and self._tool_results_have_change(tool_results):
            progress_detected = True
            self._telemetry.last_operational_progress_step = run_state.agent_step_count

        gate_violation = any(result.metadata.get("gate_violation") for result in tool_results)
        inspection_only_step = bool(tool_calls) and all(call.tool_name in _INSPECTION_TOOLS for call in tool_calls) and not gate_violation
        if progress_detected:
            self._telemetry.consecutive_inspection_steps = 0
            self._telemetry.consecutive_gate_violations = 0
            self._telemetry.consecutive_recoverable_rejections = 0
            run_state.consecutive_recoverable_rejections = 0
            self._telemetry.action_pressure_level = ActionGateState.NORMAL.value
            return

        if any(result.metadata.get("gate_violation") for result in tool_results):
            self._telemetry.consecutive_gate_violations += 1
            if self._telemetry.consecutive_gate_violations >= 2:
                run_state.state = RunStatus.FAILED
                run_state.termination_reason = REPEATED_ACTION_GATE_VIOLATION
            return

        if not inspection_only_step:
            return

        self._telemetry.consecutive_inspection_steps += 1
        self._telemetry.recent_inspection_tools = self._tail_strings(
            self._telemetry.recent_inspection_tools,
            tuple(call.tool_name for call in tool_calls),
            limit=_RECENT_HISTORY_LIMIT,
        )
        self._telemetry.recent_inspected_paths = self._tail_strings(
            self._telemetry.recent_inspected_paths,
            self._inspection_paths(tool_results),
            limit=_RECENT_HISTORY_LIMIT,
        )
        if self._telemetry.consecutive_inspection_steps >= _ACTION_STALL_STEP:
            self._telemetry.action_pressure_level = ActionGateState.STALLED.value
            run_state.state = RunStatus.FAILED
            run_state.termination_reason = (
                "semantic repair produced no mutation"
                if self._telemetry.validation_repair_pending
                else "exploration stalled without operational progress"
            )
        elif self._telemetry.consecutive_inspection_steps >= _ACTION_ONLY_STEP:
            self._telemetry.action_pressure_level = ActionGateState.ACTION_ONLY.value
        elif self._telemetry.consecutive_inspection_steps >= _FOCUSED_ACTION_STEP:
            self._telemetry.action_pressure_level = ActionGateState.FOCUSED_ACTION.value
        elif self._telemetry.consecutive_inspection_steps >= _ACTION_REQUIRED_STEP:
            self._telemetry.action_pressure_level = ActionGateState.ACTION_REQUIRED.value
        else:
            self._telemetry.action_pressure_level = ActionGateState.NORMAL.value

    def _inspection_paths(self, tool_results: tuple[ToolResult, ...]) -> tuple[str, ...]:
        paths: list[str] = []
        for result in tool_results:
            output = result.output
            if not isinstance(output, Mapping):
                continue
            if result.tool_name == "search_text":
                raw_paths = output.get("paths", ())
                if isinstance(raw_paths, Sequence) and not isinstance(raw_paths, (str, bytes, bytearray)):
                    paths.extend(str(path) for path in raw_paths)
                continue
            path = output.get("path")
            if path is not None:
                paths.append(str(path))
        return tuple(paths)

    def _tail_strings(self, existing: tuple[str, ...], new_items: tuple[str, ...], *, limit: int) -> tuple[str, ...]:
        if not new_items:
            return existing
        combined = (*existing, *new_items)
        if len(combined) <= limit:
            return combined
        return combined[-limit:]

    def _reset_action_pressure(self, run_state: RunState | None = None) -> None:
        self._telemetry.consecutive_inspection_steps = 0
        self._telemetry.consecutive_gate_violations = 0
        self._telemetry.consecutive_recoverable_rejections = 0
        if run_state is not None:
            run_state.consecutive_recoverable_rejections = 0
        self._telemetry.action_pressure_level = ActionGateState.NORMAL.value

    def _action_gate_state(self, telemetry: _LoopTelemetry) -> ActionGateState:
        if telemetry.consecutive_inspection_steps >= _ACTION_STALL_STEP:
            return ActionGateState.STALLED
        if telemetry.consecutive_inspection_steps >= _ACTION_ONLY_STEP:
            return ActionGateState.ACTION_ONLY
        if telemetry.consecutive_inspection_steps >= _FOCUSED_ACTION_STEP:
            return ActionGateState.FOCUSED_ACTION
        if telemetry.consecutive_inspection_steps >= _ACTION_REQUIRED_STEP:
            return ActionGateState.ACTION_REQUIRED
        return ActionGateState.NORMAL

    def _tool_signature(self, tool_results: tuple[ToolResult, ...]) -> str:
        payload = [
            {
                "tool_name": result.tool_name,
                "status": result.status.value,
                "output": result.output,
                "error": result.error,
                "metadata": dict(result.metadata),
            }
            for result in tool_results
        ]
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _build_failure_signature(self, build_result: BuildResult) -> str:
        payload = {
            "exit_code": build_result.exit_code,
            "stdout": build_result.stdout_log,
            "stderr": build_result.stderr_log,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _check_limits(self, run_state: RunState, limits: ExecutionLimits) -> None:
        violations = run_state.limit_violations(limits)
        if violations:
            run_state.state = RunStatus.LIMIT_REACHED
            run_state.termination_reason = ", ".join(violations)
            self._emit(run_state.run_id, RunEventType.LIMIT_REACHED, {"violations": list(violations)})
            raise LimitReachedError(run_state.termination_reason)

    def _mark_state(self, run_state: RunState, reason: str) -> None:
        self._emit(run_state.run_id, RunEventType.STATE_CHANGED, {"state": run_state.state.value, "reason": reason})

    def _persist_state(self, run_state: RunState) -> None:
        if self.reporting is not None:
            self.reporting.write_run_state(run_state)

    def _emit(self, run_id: str, event_type: RunEventType, payload: Mapping[str, Any]) -> None:
        if self.reporting is None:
            return
        self.reporting.append_event(RunEvent(run_id=run_id, event_type=event_type, payload=dict(payload)))


__all__ = ["AgentRuntime"]
