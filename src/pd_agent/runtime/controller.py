"""Run controller for PD Agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pd_agent.artifacts import ArtifactValidator
from pd_agent.build import GradleBuildRunner
from pd_agent.context import ContextManager
from pd_agent.core import ExecutionLimits, RunState, RunStatus
from pd_agent.project import ProjectInspector, ProjectInspectionStatus, ProjectSnapshot
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage
from pd_agent.tools import ToolExecutor, create_filesystem_tools

from .engine import AgentRuntime


@dataclass(slots=True)
class RunController:
    """High-level orchestration around the agent runtime."""

    provider: Any
    storage: RunStorage
    build_runner: GradleBuildRunner
    artifact_validator: ArtifactValidator
    context_manager: ContextManager
    tool_executor: ToolExecutor | None = None
    project_inspector: ProjectInspector = ProjectInspector()
    limits: ExecutionLimits = ExecutionLimits()
    model_config: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.tool_executor is None:
            object.__setattr__(self, "tool_executor", ToolExecutor(tools=create_filesystem_tools()))

    def run(
        self,
        project_root: Path,
        task: str,
        *,
        external_context: tuple[Any, ...] = (),
        model_config: Mapping[str, Any] | None = None,
        pending_mutation_targets: tuple[str, ...] = (),
    ) -> tuple[RunState, FinalReport]:
        snapshot = self.project_inspector.inspect(project_root)
        run_state = RunState(project_root=project_root, task=task)
        run_state.set_pending_mutation_targets(pending_mutation_targets)
        run_id = run_state.run_id
        self._emit(run_id, RunEventType.RUN_STARTED, {"task": task, "project_root": str(project_root)})
        run_state.transition_to(RunStatus.INSPECTING)
        self._emit(run_id, RunEventType.STATE_CHANGED, {"state": run_state.state.value, "reason": "inspection started"})
        self._emit(run_id, RunEventType.PROJECT_INSPECTED, {"status": snapshot.status.value, "issues": list(snapshot.issues)})
        self.storage.write_run_state(run_state)

        tool_executor = self.tool_executor or ToolExecutor(event_sink=self.storage.event_writer(run_id), tools=create_filesystem_tools())
        tool_executor.event_sink = self.storage.event_writer(run_id)
        runtime = AgentRuntime(
            provider=self.provider,
            tool_executor=tool_executor,
            build_runner=self.build_runner,
            artifact_validator=self.artifact_validator,
            context_manager=self.context_manager,
            reporting=self.storage,
            model_config=model_config or self.model_config or {},
        )
        run_state, report = runtime.run(
            run_state=run_state,
            project_snapshot=snapshot,
            task=task,
            external_context=external_context,
            limits=self.limits,
        )
        self.storage.write_run_state(run_state)
        return run_state, report

    def inspect(self, project_root: Path) -> ProjectSnapshot:
        return self.project_inspector.inspect(project_root)

    def _emit(self, run_id: str, event_type: RunEventType, payload: Mapping[str, Any]) -> None:
        self.storage.append_event(RunEvent(run_id=run_id, event_type=event_type, payload=dict(payload)))


__all__ = ["RunController"]
