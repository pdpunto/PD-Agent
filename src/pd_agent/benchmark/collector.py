"""Benchmark evidence collector."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from pd_agent.core import AgentResponse, ArtifactResult, BuildResult, RunState, RunStatus
from pd_agent.context import KnowledgeTrace
from pd_agent.minecraft import MinecraftTestResult, MinecraftTestStatus
from pd_agent.project import ProjectSnapshot
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage
from pd_agent.reporting.redaction import json_ready

from .models import BenchmarkConfig, BenchmarkMetrics, BenchmarkTask, BenchmarkValidationRequirements


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        dumped = value.to_dict()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    if hasattr(value, "model_dump") and callable(value.model_dump):
        dumped = value.model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return None


def _unique_strings(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


def _tool_call_from_event(event: RunEvent) -> tuple[str | None, str | None]:
    payload = event.payload
    if not isinstance(payload, Mapping):
        return None, None
    if event.event_type == RunEventType.TOOL_REQUESTED:
        call = payload
    elif event.event_type in {RunEventType.TOOL_EXECUTED, RunEventType.TOOL_REJECTED}:
        call = payload.get("call")
        if not isinstance(call, Mapping):
            call = payload
    else:
        return None, None
    call_id = call.get("call_id")
    tool_name = call.get("tool_name") or call.get("name")
    return (str(call_id) if call_id is not None else None, str(tool_name) if tool_name is not None else None)


def _logical_tool_calls(events: Sequence[RunEvent]) -> tuple[tuple[str, str | None], ...]:
    ordered: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for event in events:
        call_id, tool_name = _tool_call_from_event(event)
        if not call_id or call_id in seen:
            continue
        seen.add(call_id)
        ordered.append((call_id, tool_name))
    return tuple(ordered)


def _model_call_count(events: Sequence[RunEvent]) -> int:
    return sum(1 for event in events if event.event_type == RunEventType.MODEL_CALLED)


def _trace_provenance_refs(trace: KnowledgeTrace) -> tuple[str, ...]:
    refs: list[str] = []
    for attempt in trace.source_attempts:
        parts = [attempt.source_id, attempt.source_kind]
        if attempt.locator:
            parts.append(attempt.locator)
        if attempt.revision:
            parts.append(attempt.revision)
        if attempt.checksum:
            parts.append(attempt.checksum)
        refs.append("|".join(parts))
    return tuple(refs)


def _trace_payload_refs(storage: RunStorage, run_id: str, report: FinalReport) -> tuple[KnowledgeTrace, ...]:
    traces: list[KnowledgeTrace] = []
    paths = storage.paths_for(run_id)
    for ref in report.evidence_refs:
        ref_path = paths.root / ref
        if not ref_path.exists():
            continue
        try:
            payload = json.loads(ref_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        try:
            traces.append(KnowledgeTrace.from_dict(payload))
        except Exception:
            continue
    return tuple(traces)


def _project_snapshot_dict(project_snapshot: ProjectSnapshot | Mapping[str, Any] | None) -> dict[str, Any] | None:
    if project_snapshot is None:
        return None
    if isinstance(project_snapshot, ProjectSnapshot):
        return project_snapshot.to_dict()
    if isinstance(project_snapshot, Mapping):
        return dict(project_snapshot)
    return None


def _environment_identity(project_snapshot: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if project_snapshot is None:
        return None
    detected_versions = project_snapshot.get("detected_versions")
    if isinstance(detected_versions, Mapping):
        detected_versions = {
            str(key): value.get("value") if isinstance(value, Mapping) else value
            for key, value in detected_versions.items()
        }
    else:
        detected_versions = None
    identity = {
        "project_root": project_snapshot.get("project_root"),
        "status": project_snapshot.get("status"),
        "target_subproject": project_snapshot.get("target_subproject"),
        "detected_versions": detected_versions,
    }
    return {key: value for key, value in identity.items() if value is not None}


@dataclass(frozen=True, slots=True)
class BenchmarkCollection:
    """Normalized benchmark evidence."""

    run_id: str | None = None
    task_id: str | None = None
    task_version: str | None = None
    config_id: str | None = None
    config_hash: str | None = None
    repetition_index: int | None = None
    attempt_index: int | None = None
    provider: str | None = None
    model: str | None = None
    brain_enabled: bool | None = None
    validation_requirements: BenchmarkValidationRequirements | None = None
    public_model_config: Mapping[str, Any] | None = None
    public_provider_config: Mapping[str, Any] | None = None
    knowledge_config: Mapping[str, Any] | None = None
    final_state: RunStatus | None = None
    termination_reason: str | None = None
    build_attempts: tuple[BuildResult, ...] = ()
    final_build: BuildResult | None = None
    artifact: ArtifactResult | None = None
    changed_files: tuple[str, ...] = ()
    tool_call_count: int | None = None
    tool_names: tuple[str, ...] = ()
    agent_step_count: int | None = None
    logical_provider_request_count: int | None = None
    duration_seconds: float | None = None
    usage: Mapping[str, Any] | None = None
    provider_metadata: Mapping[str, Any] | None = None
    retrieved_item_ids: tuple[str, ...] = ()
    selected_item_ids: tuple[str, ...] = ()
    injected_item_ids: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    knowledge_traces: tuple[KnowledgeTrace, ...] = ()
    environment_identity: Mapping[str, Any] | None = None
    project_snapshot: Mapping[str, Any] | None = None
    minecraft_result: MinecraftTestResult | None = None
    events: tuple[RunEvent, ...] = ()
    inconsistencies: tuple[str, ...] = ()
    metrics: BenchmarkMetrics = field(default_factory=BenchmarkMetrics)

    @property
    def retrieved_count(self) -> int | None:
        if self.knowledge_traces:
            return len(self.retrieved_item_ids)
        return 0 if self.brain_enabled is not None else None

    @property
    def selected_count(self) -> int | None:
        if self.knowledge_traces:
            return len(self.selected_item_ids)
        return 0 if self.brain_enabled is not None else None

    @property
    def injected_count(self) -> int | None:
        if self.knowledge_traces:
            return len(self.injected_item_ids)
        return 0 if self.brain_enabled is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "config_id": self.config_id,
            "config_hash": self.config_hash,
            "repetition_index": self.repetition_index,
            "attempt_index": self.attempt_index,
            "provider": self.provider,
            "model": self.model,
            "brain_enabled": self.brain_enabled,
            "validation_requirements": (
                self.validation_requirements.to_dict()
                if self.validation_requirements is not None
                else None
            ),
            "public_model_config": json_ready(dict(self.public_model_config)) if self.public_model_config is not None else None,
            "public_provider_config": json_ready(dict(self.public_provider_config)) if self.public_provider_config is not None else None,
            "knowledge_config": json_ready(dict(self.knowledge_config)) if self.knowledge_config is not None else None,
            "final_state": self.final_state.value if self.final_state is not None else None,
            "termination_reason": self.termination_reason,
            "build_attempts": [item.to_dict() for item in self.build_attempts],
            "final_build": self.final_build.to_dict() if self.final_build is not None else None,
            "artifact": self.artifact.to_dict() if self.artifact is not None else None,
            "changed_files": list(self.changed_files),
            "tool_call_count": self.tool_call_count,
            "tool_names": list(self.tool_names),
            "agent_step_count": self.agent_step_count,
            "logical_provider_request_count": self.logical_provider_request_count,
            "duration_seconds": self.duration_seconds,
            "usage": json_ready(dict(self.usage)) if self.usage is not None else None,
            "provider_metadata": (
                json_ready(dict(self.provider_metadata))
                if self.provider_metadata is not None
                else None
            ),
            "retrieved_item_ids": list(self.retrieved_item_ids),
            "selected_item_ids": list(self.selected_item_ids),
            "injected_item_ids": list(self.injected_item_ids),
            "provenance_refs": list(self.provenance_refs),
            "knowledge_traces": [trace.to_dict() for trace in self.knowledge_traces],
            "environment_identity": (
                json_ready(dict(self.environment_identity))
                if self.environment_identity is not None
                else None
            ),
            "project_snapshot": (
                json_ready(dict(self.project_snapshot)) if self.project_snapshot is not None else None
            ),
            "minecraft_result": (
                self.minecraft_result.to_dict() if self.minecraft_result is not None else None
            ),
            "events": [event.to_dict() for event in self.events],
            "inconsistencies": list(self.inconsistencies),
            "metrics": self.metrics.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BenchmarkCollection":
        return cls(
            run_id=data.get("run_id"),
            task_id=data.get("task_id"),
            task_version=data.get("task_version"),
            config_id=data.get("config_id"),
            config_hash=data.get("config_hash"),
            repetition_index=data.get("repetition_index"),
            attempt_index=data.get("attempt_index"),
            provider=data.get("provider"),
            model=data.get("model"),
            brain_enabled=data.get("brain_enabled"),
            validation_requirements=(
                BenchmarkValidationRequirements.from_dict(dict(data["validation_requirements"]))
                if data.get("validation_requirements") is not None
                else None
            ),
            public_model_config=dict(data.get("public_model_config", {})) if data.get("public_model_config") is not None else None,
            public_provider_config=dict(data.get("public_provider_config", {})) if data.get("public_provider_config") is not None else None,
            knowledge_config=dict(data.get("knowledge_config", {})) if data.get("knowledge_config") is not None else None,
            final_state=RunStatus(str(data["final_state"])) if data.get("final_state") is not None else None,
            termination_reason=data.get("termination_reason"),
            build_attempts=tuple(BuildResult.from_dict(item) for item in data.get("build_attempts", [])),
            final_build=(BuildResult.from_dict(dict(data["final_build"])) if data.get("final_build") is not None else None),
            artifact=(ArtifactResult.from_dict(dict(data["artifact"])) if data.get("artifact") is not None else None),
            changed_files=tuple(str(item) for item in data.get("changed_files", [])),
            tool_call_count=data.get("tool_call_count"),
            tool_names=tuple(str(item) for item in data.get("tool_names", [])),
            agent_step_count=data.get("agent_step_count"),
            logical_provider_request_count=data.get("logical_provider_request_count"),
            duration_seconds=data.get("duration_seconds"),
            usage=dict(data.get("usage", {})) if data.get("usage") is not None else None,
            provider_metadata=dict(data.get("provider_metadata", {})) if data.get("provider_metadata") is not None else None,
            retrieved_item_ids=tuple(str(item) for item in data.get("retrieved_item_ids", [])),
            selected_item_ids=tuple(str(item) for item in data.get("selected_item_ids", [])),
            injected_item_ids=tuple(str(item) for item in data.get("injected_item_ids", [])),
            provenance_refs=tuple(str(item) for item in data.get("provenance_refs", [])),
            knowledge_traces=tuple(KnowledgeTrace.from_dict(item) for item in data.get("knowledge_traces", [])),
            environment_identity=dict(data.get("environment_identity", {})) if data.get("environment_identity") is not None else None,
            project_snapshot=dict(data.get("project_snapshot", {})) if data.get("project_snapshot") is not None else None,
            minecraft_result=(
                MinecraftTestResult.from_dict(dict(data["minecraft_result"]))
                if data.get("minecraft_result") is not None
                else None
            ),
            events=tuple(RunEvent.from_dict(item) for item in data.get("events", [])),
            inconsistencies=tuple(str(item) for item in data.get("inconsistencies", [])),
            metrics=BenchmarkMetrics.from_dict(dict(data["metrics"])) if data.get("metrics") is not None else BenchmarkMetrics(),
        )


class BenchmarkCollector:
    """Collect structured benchmark evidence from run artifacts."""

    def collect(
        self,
        *,
        storage: RunStorage | None = None,
        run_id: str | None = None,
        repetition_index: int | None = None,
        attempt_index: int | None = None,
        run_state: RunState | None = None,
        final_report: FinalReport | None = None,
        events: Sequence[RunEvent] = (),
        knowledge_traces: Sequence[KnowledgeTrace] = (),
        provider_response: AgentResponse | None = None,
        project_snapshot: ProjectSnapshot | Mapping[str, Any] | None = None,
        config: BenchmarkConfig | None = None,
        task: BenchmarkTask | None = None,
        validation_requirements: BenchmarkValidationRequirements | None = None,
        minecraft_result: MinecraftTestResult | None = None,
    ) -> BenchmarkCollection:
        if storage is not None and (run_state is None or final_report is None or not events):
            if run_id is None:
                run_id = run_state.run_id if run_state is not None else final_report.run_id if final_report is not None else None
            if run_id is None:
                raise ValueError("run_id is required when loading from storage")
            if run_state is None:
                run_state = storage.read_run_state(run_id)
            if final_report is None:
                final_report = storage.read_final_report(run_id)
            if not events:
                events = storage.read_events(run_id)
            if not knowledge_traces and final_report is not None:
                knowledge_traces = _trace_payload_refs(storage, run_id, final_report)

        if run_state is None and final_report is None:
            raise ValueError("run_state or final_report is required")

        run_id = run_id or (run_state.run_id if run_state is not None else None) or (final_report.run_id if final_report is not None else None)
        if run_state is not None and run_id is not None and run_state.run_id != run_id:
            raise ValueError("run_id mismatch with run_state")
        if final_report is not None and run_id is not None and final_report.run_id != run_id:
            raise ValueError("run_id mismatch with final_report")

        task = task
        validation_requirements = validation_requirements or (task.validation if task is not None else None)

        final_state = final_report.final_state if final_report is not None else (run_state.state if run_state is not None else None)
        termination_reason = final_report.termination_reason if final_report is not None else (run_state.termination_reason if run_state is not None else None)

        build_attempts = final_report.build_attempts if final_report is not None and final_report.build_attempts else (run_state.build_results if run_state is not None else ())
        final_build = final_report.final_build if final_report is not None and final_report.final_build is not None else (run_state.build_results[-1] if run_state is not None and run_state.build_results else None)
        artifact = final_report.artifact if final_report is not None and final_report.artifact is not None else (run_state.artifact_result if run_state is not None else None)

        inconsistencies: list[str] = []
        if run_state is not None and final_report is not None and run_state.run_id != final_report.run_id:
            inconsistencies.append("run_id_mismatch")
        if run_state is not None and final_report is not None and run_state.state != final_report.final_state:
            inconsistencies.append("final_state_contradiction")
        if run_state is not None and final_report is not None and final_report.final_build is not None and run_state.build_results:
            if final_report.final_build.to_dict() != run_state.build_results[-1].to_dict():
                inconsistencies.append("final_build_contradiction")
        if run_state is not None and final_report is not None and final_report.artifact is not None and run_state.artifact_result is not None:
            if final_report.artifact.to_dict() != run_state.artifact_result.to_dict():
                inconsistencies.append("artifact_contradiction")

        logical_tool_calls = _logical_tool_calls(events)
        model_call_count = _model_call_count(events)
        tool_names = self._tool_names(logical_tool_calls)
        tool_call_count = run_state.tool_call_count if run_state is not None else None
        if tool_call_count is not None and logical_tool_calls:
            if len(logical_tool_calls) != tool_call_count:
                inconsistencies.append("tool_call_mismatch")
        if run_state is not None and build_attempts and run_state.build_attempt_count != len(build_attempts):
            inconsistencies.append("build_count_mismatch")
        logical_provider_request_count = run_state.logical_provider_request_count if run_state is not None else None
        if (
            run_state is not None
            and logical_provider_request_count is not None
            and logical_provider_request_count != model_call_count
            and (logical_provider_request_count > 0 or model_call_count == 0)
        ):
            inconsistencies.append("logical_provider_request_mismatch")

        provider_metadata = self._provider_metadata(provider_response, events, run_state=run_state)
        usage = self._usage(provider_response, events)
        provider = config.provider if config is not None else provider_metadata.get("provider") if provider_metadata else None
        model = config.model if config is not None else provider_metadata.get("model") if provider_metadata else None
        brain_enabled = config.brain_enabled if config is not None else None

        project_snapshot_data = _project_snapshot_dict(project_snapshot)
        if project_snapshot_data is None and run_state is not None and run_state.project_snapshot is not None:
            project_snapshot_data = dict(run_state.project_snapshot)
        environment_identity = _environment_identity(project_snapshot_data)

        traces = tuple(knowledge_traces)
        retrieved_ids = self._trace_ids(traces, "retrieved_item_ids")
        selected_ids = self._trace_ids(traces, "selected_item_ids")
        injected_ids = self._trace_ids(traces, "context_item_ids")
        provenance_refs = tuple(ref for trace in traces for ref in _trace_provenance_refs(trace))

        if brain_enabled is False and not traces and final_report is not None and not final_report.evidence_refs:
            retrieved_ids = ()
            selected_ids = ()
            injected_ids = ()

        if brain_enabled is False and (retrieved_ids or selected_ids or injected_ids):
            inconsistencies.append("brain_off_retrieval_present")

        if validation_requirements is not None:
            if validation_requirements.build and final_build is None:
                inconsistencies.append("missing_required_build_result")
            if validation_requirements.artifact and artifact is None:
                inconsistencies.append("missing_required_artifact")
            if validation_requirements.minecraft and minecraft_result is None:
                inconsistencies.append("missing_required_minecraft_result")

        duration_seconds = None
        if run_state is not None and final_report is not None:
            duration_seconds = max((final_report.generated_at - run_state.started_at).total_seconds(), 0.0)
        elif run_state is not None and run_state.build_results:
            duration_seconds = run_state.build_results[-1].duration_seconds

        metrics = BenchmarkMetrics(
            duration_seconds=duration_seconds,
            tool_call_count=tool_call_count,
            build_count=len(build_attempts) if build_attempts else None,
            agent_step_count=run_state.agent_step_count if run_state is not None else None,
            logical_provider_request_count=logical_provider_request_count,
            input_tokens=usage.get("input_tokens") if usage is not None else None,
            output_tokens=usage.get("output_tokens") if usage is not None else None,
            total_tokens=usage.get("total_tokens") if usage is not None else None,
            cost=usage.get("cost") if usage is not None and isinstance(usage.get("cost"), (int, float)) else None,
            extra={
                "provider": provider,
                "model": model,
                "brain_enabled": brain_enabled,
                "retrieved_item_count": len(retrieved_ids),
                "selected_item_count": len(selected_ids),
                "injected_item_count": len(injected_ids),
                "tool_names": list(tool_names),
            },
        )

        return BenchmarkCollection(
            run_id=run_id,
            task_id=task.task_id if task is not None else None,
            task_version=task.task_version if task is not None else None,
            config_id=config.config_id if config is not None else None,
            config_hash=config.config_hash() if config is not None else None,
            repetition_index=repetition_index,
            attempt_index=attempt_index,
            provider=provider,
            model=model,
            brain_enabled=brain_enabled,
            validation_requirements=validation_requirements,
            public_model_config=dict(config.model_config) if config is not None else None,
            public_provider_config=dict(config.provider_config) if config is not None else None,
            knowledge_config=dict(config.knowledge_config) if config is not None else None,
            final_state=final_state,
            termination_reason=termination_reason,
            build_attempts=build_attempts,
            final_build=final_build,
            artifact=artifact,
            changed_files=run_state.changed_files if run_state is not None else (),
            tool_call_count=tool_call_count,
            tool_names=tool_names,
            agent_step_count=run_state.agent_step_count if run_state is not None else None,
            logical_provider_request_count=logical_provider_request_count,
            duration_seconds=duration_seconds,
            usage=usage,
            provider_metadata=provider_metadata or None,
            retrieved_item_ids=retrieved_ids,
            selected_item_ids=selected_ids,
            injected_item_ids=injected_ids,
            provenance_refs=provenance_refs,
            knowledge_traces=traces,
            environment_identity=environment_identity,
            project_snapshot=project_snapshot_data,
            minecraft_result=minecraft_result,
            events=tuple(events),
            inconsistencies=tuple(inconsistencies),
            metrics=metrics,
        )

    def _provider_metadata(
        self,
        provider_response: AgentResponse | None,
        events: Sequence[RunEvent],
        *,
        run_state: RunState | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if provider_response is not None and provider_response.provider_metadata is not None:
            metadata.update(dict(provider_response.provider_metadata))
        for event in events:
            if event.event_type == RunEventType.MODEL_RESPONDED:
                payload = event.payload
                if isinstance(payload, Mapping):
                    event_metadata = payload.get("provider_metadata")
                    if isinstance(event_metadata, Mapping):
                        metadata.update(dict(event_metadata))
        if run_state is not None and run_state.provider_error_kind is not None:
            metadata["provider_error"] = {
                "kind": run_state.provider_error_kind,
                "message": run_state.provider_error_message or run_state.last_error,
            }
        return metadata

    def _usage(self, provider_response: AgentResponse | None, events: Sequence[RunEvent]) -> dict[str, Any] | None:
        if provider_response is not None and provider_response.usage is not None:
            return dict(provider_response.usage)
        for event in events:
            if event.event_type == RunEventType.MODEL_RESPONDED:
                payload = event.payload
                if isinstance(payload, Mapping):
                    usage = payload.get("usage")
                    if isinstance(usage, Mapping):
                        return dict(usage)
        return None

    def _tool_names(self, logical_tool_calls: Sequence[tuple[str, str | None]]) -> tuple[str, ...]:
        names: list[str] = []
        for _call_id, name in logical_tool_calls:
            if name:
                names.append(name)
        return _unique_strings(names)

    def _trace_ids(self, traces: Sequence[KnowledgeTrace], field_name: str) -> tuple[str, ...]:
        ordered: list[str] = []
        for trace in traces:
            ids = getattr(trace, field_name, ())
            for item in ids:
                if item not in ordered:
                    ordered.append(item)
        return tuple(ordered)
