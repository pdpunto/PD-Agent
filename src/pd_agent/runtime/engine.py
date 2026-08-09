"""Single-agent execution loop for PD Agent."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from pd_agent.artifacts import ArtifactValidator
from pd_agent.build import GradleBuildRunner
from pd_agent.context import ContextManager
from pd_agent.core import (
    AgentMessage,
    AgentRequest,
    ArtifactResult,
    BuildResult,
    ExecutionLimits,
    ModelProvider,
    ProviderError,
    ProviderContinuation,
    RunState,
    RunStatus,
    ToolCall,
    ToolResult,
    ToolResultStatus,
)
from pd_agent.core.errors import BuildError, LimitReachedError
from pd_agent.core.errors import ArtifactValidationError
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage
from pd_agent.tools import ToolExecutionContext, ToolExecutor, create_filesystem_tools


@dataclass(slots=True)
class _LoopTelemetry:
    last_failure_signature: str | None = None
    failure_repeat_count: int = 0
    last_tool_signature: str | None = None
    tool_repeat_count: int = 0


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
    ) -> None:
        self.provider = provider
        self.tool_executor = tool_executor or ToolExecutor(tools=tuple(filesystem_tools) or create_filesystem_tools())
        self.build_runner = build_runner
        self.artifact_validator = artifact_validator
        self.context_manager = context_manager
        self.reporting = reporting
        self.model_config = dict(model_config or {})
        self._telemetry = _LoopTelemetry()

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
        try:
            while not run_state.state.is_terminal():
                self._check_limits(run_state, limits)

                if run_state.state in {RunStatus.PLANNING, RunStatus.DIAGNOSING, RunStatus.CORRECTING}:
                    response = self._call_provider(
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
                    )
                    if run_state.state.is_terminal():
                        self._persist_state(run_state)
                        break

                    if self._tool_results_have_rejection(tool_results):
                        run_state.state = RunStatus.FAILED
                        run_state.termination_reason = "tool rejected"
                        break

                    if run_state.state == RunStatus.PLANNING:
                        run_state.transition_to(RunStatus.EDITING)
                    elif run_state.state == RunStatus.DIAGNOSING:
                        run_state.transition_to(RunStatus.CORRECTING if tool_results else RunStatus.FAILED)
                        if run_state.state == RunStatus.FAILED:
                            run_state.termination_reason = "diagnosis produced no correction"
                    elif run_state.state == RunStatus.CORRECTING:
                        run_state.transition_to(RunStatus.BUILDING)
                    elif run_state.state == RunStatus.EDITING:
                        run_state.transition_to(RunStatus.BUILDING)
                    pending_tool_calls = response.tool_calls
                    pending_tool_results = tool_results
                    pending_provider_continuations = response.provider_continuations
                    self._persist_state(run_state)
                    continue

                if run_state.state == RunStatus.EDITING:
                    run_state.transition_to(RunStatus.BUILDING)
                    self._persist_state(run_state)
                    continue

                if run_state.state == RunStatus.BUILDING:
                    self._check_limits(run_state, limits)
                    build_result = self.build_runner.run(project_snapshot, run_state, limits)
                    self._observe_progress(run_state, build_result=build_result)
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
                        run_state.transition_to(RunStatus.REPORTING)
                        self._persist_state(run_state)
                        continue
                    run_state.state = RunStatus.FAILED
                    run_state.termination_reason = "artifact validation failed"
                    break

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
    ) -> Any:
        bundle = self.context_manager.build_context(
            project_snapshot=project_snapshot,
            run_state=run_state,
            external_context=external_context,
            limits=limits,
        )
        messages = bundle.to_messages() + tuple(history)
        request = AgentRequest(
            messages=messages,
            tool_calls=tool_calls,
            tool_results=tool_results,
            provider_continuations=provider_continuations,
            tools=tuple(self._tool_specs()),
            model_config=self._model_config(run_state, limits),
        )
        self._emit(
            run_state.run_id,
            RunEventType.MODEL_CALLED,
            {
                "message_count": len(request.messages),
                "tool_count": len(request.tools),
                "model_config": self._safe_model_config(request.model_config),
            },
        )
        try:
            return self.provider.execute(request)
        except ProviderError:
            run_state.state = RunStatus.FAILED
            run_state.termination_reason = "provider error"
            raise

    def _execute_tool_calls(
        self,
        tool_calls: tuple[ToolCall, ...],
        *,
        run_state: RunState,
        project_snapshot: ProjectSnapshot,
        limits: ExecutionLimits,
    ) -> tuple[ToolResult, ...]:
        if not tool_calls:
            return ()
        context = ToolExecutionContext(project_root=project_snapshot.project_root, limits=limits, run_id=run_state.run_id)
        results: list[ToolResult] = []
        for call in tool_calls:
            self._check_limits(run_state, limits)
            result = self.tool_executor.execute(call, context)
            results.append(result)
            run_state.record_tool_call()
            self._persist_state(run_state)
            self._observe_progress(run_state, tool_results=(result,))
            if run_state.state.is_terminal():
                break
        return tuple(results)

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
            limits_usage=self._limits_usage(run_state, limits),
            warnings=(),
            termination_reason=run_state.termination_reason,
            evidence_refs=(),
        )
        if self.reporting is not None:
            self.reporting.write_run_state(run_state)
            self.reporting.write_final_report(report)
            self._emit(run_state.run_id, RunEventType.RUN_FINISHED, {"final_state": run_state.state.value, "summary": summary})
        return run_state, report

    def _tool_specs(self) -> Iterable[Mapping[str, Any]]:
        for tool in self.tool_executor._tools.values():  # noqa: SLF001
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

    def _summary(self, run_state: RunState) -> str:
        return f"state={run_state.state.value} steps={run_state.agent_step_count} tools={run_state.tool_call_count} builds={run_state.build_attempt_count}"

    def _limits_usage(self, run_state: RunState, limits: ExecutionLimits) -> dict[str, int]:
        return {
            "agent_steps": run_state.agent_step_count,
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
    ) -> None:
        if tool_results:
            if any(result.status == ToolResultStatus.SUCCESS and result.metadata.get("changed") for result in tool_results):
                self._telemetry.last_tool_signature = None
                self._telemetry.tool_repeat_count = 0
            else:
                signature = self._tool_signature(tool_results)
                if signature == self._telemetry.last_tool_signature:
                    self._telemetry.tool_repeat_count += 1
                else:
                    self._telemetry.last_tool_signature = signature
                    self._telemetry.tool_repeat_count = 0
                if self._telemetry.tool_repeat_count >= 1:
                    run_state.state = RunStatus.FAILED
                    run_state.termination_reason = "repeated no-op tool calls"
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
                run_state.termination_reason = "repeated build failure"
                return
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
