"""Single-run benchmark executor."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from pd_agent.artifacts import ArtifactValidator
from pd_agent.brain import FileKnowledgeCache, KnowledgeEnvironment, KnowledgeEnvironmentResolver, KnowledgeNeed, KnowledgeRetrievalResult, MinecraftBrain
from pd_agent.brain.models import KnowledgeType
from pd_agent.build import GradleBuildRunner
from pd_agent.context import ContextManager, ProjectContextSource, RunContextSource
from pd_agent.core import ExecutionLimits, ModelProvider, ProviderError, RunState
from pd_agent.minecraft import MinecraftTestResult, MinecraftTestRunner, MinecraftTestSpec
from pd_agent.project import ProjectInspector, ProjectInspectionStatus, ProjectSnapshot
from pd_agent.reporting import FinalReport, RunStorage
from pd_agent.tools import ToolExecutor

from .classifier import BenchmarkClassifier, BenchmarkClassification
from .collector import BenchmarkCollection, BenchmarkCollector
from .models import (
    BenchmarkConfig,
    BenchmarkExecutionStatus,
    BenchmarkFailureCode,
    BenchmarkFailureOrigin,
    BenchmarkRun,
    BenchmarkTask,
    BenchmarkTaskOutcome,
)
from .scheduler import BenchmarkScheduledAttempt
from .workspace import BenchmarkWorkspace, BenchmarkWorkspaceError, compute_fixture_identity, prepare_workspace
from pd_agent.core import RunStatus
from pd_agent.runtime import RunController
from dataclasses import replace


def _write_json(path: Path, data: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _as_mapping(value: object) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        dumped = value.to_dict()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return None


def _filesystem_safe_fragment(value: str) -> str:
    fragment = re.sub(r'[<>:"/\\|?*]+', "_", str(value)).strip(" .")
    return fragment or "run"


def _knowledge_need_from_mapping(data: Mapping[str, Any], *, environment: KnowledgeEnvironment) -> KnowledgeNeed:
    need_type = data.get("type", "SYMBOL")
    if hasattr(need_type, "value"):
        need_type = need_type.value
    return KnowledgeNeed(
        id=str(data.get("id", "knowledge-need")),
        type=KnowledgeType(str(need_type)),
        query=str(data.get("query", "")),
        environment=environment,
        hints=tuple(str(item) for item in data.get("hints", [])),
    )


def _default_context_manager(brain_enabled: bool) -> ContextManager:
    if brain_enabled:
        return ContextManager()
    return ContextManager(sources=(("project", ProjectContextSource()), ("run", RunContextSource())))


def _benchmark_execution_limits(config: BenchmarkConfig) -> ExecutionLimits:
    limits = config.execution_limits
    if isinstance(limits, ExecutionLimits):
        return limits
    if limits is None:
        return ExecutionLimits()
    if isinstance(limits, Mapping):
        return ExecutionLimits.from_dict(dict(limits))
    raise TypeError("benchmark execution_limits must be an ExecutionLimits or mapping")


def _task_knowledge_needs(task: BenchmarkTask, *, environment: KnowledgeEnvironment) -> tuple[KnowledgeNeed, ...]:
    spec = task.acceptance.spec
    if not isinstance(spec, Mapping):
        return ()
    raw = spec.get("knowledge_needs", spec.get("knowledge_need"))
    if raw is None:
        return ()
    if isinstance(raw, Mapping):
        return (_knowledge_need_from_mapping(raw, environment=environment),)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        needs: list[KnowledgeNeed] = []
        for item in raw:
            if isinstance(item, Mapping):
                needs.append(_knowledge_need_from_mapping(item, environment=environment))
        return tuple(needs)
    return ()


def _minecraft_spec_for_task(
    task: BenchmarkTask,
    *,
    artifact_path: Path,
    artifact_sha256: str,
) -> MinecraftTestSpec:
    spec = task.acceptance.spec if isinstance(task.acceptance.spec, Mapping) else {}
    target_mod_id = str(spec.get("target_mod_id") or spec.get("mod_id") or task.task_id).strip()
    test_id = str(spec.get("test_id") or f"{task.task_id}:{task.task_version}").strip()
    minecraft_version = str(spec.get("minecraft_version") or task.environment.minecraft_version or "").strip()
    loader_version = str(spec.get("loader_version") or task.environment.loader_version or "").strip()
    timeout_seconds = int(spec.get("timeout_seconds", 60))
    expect_neighbor_update = bool(spec.get("expected_neighbor_update", spec.get("expect_neighbor_update", False)))
    return MinecraftTestSpec(
        target_jar=artifact_path,
        target_mod_id=target_mod_id,
        minecraft_version=minecraft_version,
        loader_version=loader_version,
        test_id=test_id,
        timeout_seconds=timeout_seconds,
        expect_neighbor_update=expect_neighbor_update,
    )


def _execution_environment_snapshot(
    *,
    task: BenchmarkTask,
    config: BenchmarkConfig,
    workspace: BenchmarkWorkspace,
    project_snapshot: ProjectSnapshot,
    resolution: Mapping[str, Any] | None,
    knowledge_needs: Sequence[KnowledgeNeed],
    fixture_hash_after: str | None = None,
) -> dict[str, Any]:
    snapshot = {
        "task": task.to_dict(),
        "config": config.to_dict(),
        "benchmark_root": str(workspace.benchmark_root),
        "workspace_root": str(workspace.workspace_root),
        "canonical_fixture_hash": workspace.canonical_hash_before,
        "workspace_hash_initial": workspace.workspace_hash_initial,
        "project_snapshot": project_snapshot.to_dict(),
        "knowledge_needs": [need.to_dict() for need in knowledge_needs],
    }
    if resolution is not None:
        snapshot["knowledge_environment"] = resolution
    if fixture_hash_after is not None:
        snapshot["fixture_integrity"] = {
            "canonical_hash_before": workspace.canonical_hash_before,
            "canonical_hash_after": fixture_hash_after,
            "contaminated": fixture_hash_after != workspace.canonical_hash_before,
        }
    return snapshot


@dataclass(frozen=True, slots=True)
class BenchmarkExecutionResult:
    """Persisted result for one benchmark execution."""

    execution_id: str
    execution_root: Path
    workspace: BenchmarkWorkspace
    run_state: RunState
    final_report: FinalReport
    collection: BenchmarkCollection
    classification: BenchmarkClassification
    benchmark_run: BenchmarkRun
    minecraft_result: MinecraftTestResult | None
    project_snapshot: ProjectSnapshot
    benchmark_run_path: Path
    benchmark_collection_path: Path
    benchmark_classification_path: Path
    workspace_metadata_path: Path
    runtime_storage_root: Path


@dataclass(slots=True)
class BenchmarkExecutor:
    """Execute one benchmark run through the normal PD Agent runtime."""

    provider: ModelProvider
    build_runner: GradleBuildRunner
    artifact_validator: ArtifactValidator
    benchmark_root: Path | None = None
    tool_executor: ToolExecutor | None = None
    context_manager_factory: Callable[[bool], ContextManager] = _default_context_manager
    knowledge_environment_resolver: KnowledgeEnvironmentResolver = field(default_factory=KnowledgeEnvironmentResolver)
    knowledge_source: Any | None = None
    minecraft_runner: MinecraftTestRunner | None = None
    collector: BenchmarkCollector = field(default_factory=BenchmarkCollector)
    classifier: BenchmarkClassifier = field(default_factory=BenchmarkClassifier)

    def execute(
        self,
        task: BenchmarkTask,
        config: BenchmarkConfig,
        scheduled_attempt: BenchmarkScheduledAttempt,
        *,
        fixture_root: Path,
        execution_root: Path,
        pd_agent_commit: str | None = None,
        knowledge_needs: Sequence[KnowledgeNeed] | None = None,
        preserve_workspace: bool = False,
        minecraft_runner: MinecraftTestRunner | None = None,
    ) -> BenchmarkExecutionResult:
        execution_root = Path(execution_root).resolve(strict=False)
        execution_root.mkdir(parents=True, exist_ok=True)
        benchmark_run_id = scheduled_attempt.scheduled_attempt_id
        run_fragment = _filesystem_safe_fragment(benchmark_run_id)
        execution_id = execution_root.name
        run_root = execution_root / "runs" / run_fragment
        run_root.mkdir(parents=True, exist_ok=True)

        fixture_root = Path(fixture_root).resolve(strict=True)
        workspace = prepare_workspace(
            fixture_root,
            execution_root,
            run_id=run_fragment,
            attempt_id=f"attempt-{scheduled_attempt.attempt_index:03d}",
            preserve_on_cleanup=preserve_workspace,
        )

        try:
            project_inspector = ProjectInspector()
            project_snapshot = project_inspector.inspect(workspace.workspace_root)
            if project_snapshot.status != ProjectInspectionStatus.READY:
                raise BenchmarkWorkspaceError(f"workspace inspection not ready: {project_snapshot.status.value}")

            env_resolution = self.knowledge_environment_resolver.resolve(
                workspace.workspace_root,
                verification_sources=(task.environment.to_dict(),),
            )
            resolved_environment = env_resolution.environment

            requested_needs = tuple(knowledge_needs) if knowledge_needs is not None else _task_knowledge_needs(
                task,
                environment=resolved_environment,
            )
            external_context: tuple[Any, ...] = ()
            if config.brain_enabled and requested_needs and self.knowledge_source is not None:
                cache_root = execution_root / "brain-cache" / run_fragment
                brain = MinecraftBrain(
                    source=self.knowledge_source,
                    cache=FileKnowledgeCache(cache_root),
                )
                retrieved: list[KnowledgeRetrievalResult] = []
                offline = bool(_as_mapping(config.knowledge_config or {}).get("offline", False))
                for need in requested_needs:
                    retrieved.append(brain.retrieve(need, offline=offline))
                external_context = tuple(retrieved)

            context_manager = self.context_manager_factory(config.brain_enabled)
            runtime_storage = RunStorage(run_root / "runtime")
            execution_limits = _benchmark_execution_limits(config)
            controller = RunController(
                provider=self.provider,
                storage=runtime_storage,
                build_runner=self.build_runner,
                artifact_validator=self.artifact_validator,
                context_manager=context_manager,
                tool_executor=self.tool_executor,
                limits=execution_limits,
                model_config=dict(config.model_config),
            )
            run_state, final_report = controller.run(
                workspace.workspace_root,
                task.prompt,
                external_context=external_context,
                model_config=dict(config.model_config),
            )

            minecraft = self._maybe_run_minecraft(
                task,
                config,
                run_state=run_state,
                final_report=final_report,
                workspace=workspace,
                benchmark_run_id=benchmark_run_id,
                filesystem_run_id=run_fragment,
                minecraft_runner=minecraft_runner or self.minecraft_runner,
            )
            fixture_hash_after = compute_fixture_identity(workspace.source_fixture)
            contamination_reason = None
            if fixture_hash_after != workspace.canonical_hash_before:
                contamination_reason = (
                    "fixture contamination detected: "
                    f"before={workspace.canonical_hash_before} after={fixture_hash_after}"
                )

            collection = self.collector.collect(
                storage=runtime_storage,
                run_id=run_state.run_id,
                run_state=run_state,
                final_report=final_report,
                config=config,
                task=task,
                minecraft_result=minecraft,
            )
            if contamination_reason is not None:
                collection = replace(collection, inconsistencies=(*collection.inconsistencies, contamination_reason))
            classification = self._classify(collection, run_state=run_state)
            if contamination_reason is not None:
                classification = BenchmarkClassification(
                    execution_status=BenchmarkExecutionStatus.INVALID,
                    task_outcome=BenchmarkTaskOutcome.NOT_EVALUATED,
                    failure_origin=BenchmarkFailureOrigin.BENCHMARK_INFRA,
                    failure_code=BenchmarkFailureCode.BENCHMARK_CONTAMINATION,
                    reason=contamination_reason,
                )
            benchmark_run = self._benchmark_run(
                benchmark_run_id=benchmark_run_id,
                task=task,
                config=config,
                attempt=scheduled_attempt,
                pd_agent_commit=pd_agent_commit,
                workspace=workspace,
                run_state=run_state,
                final_report=final_report,
                collection=collection,
                classification=classification,
                project_snapshot=project_snapshot,
                env_resolution=env_resolution.to_dict(),
                knowledge_needs=requested_needs,
                runtime_storage=runtime_storage,
                fixture_hash_after=fixture_hash_after,
            )

            benchmark_run_path, collection_path, classification_path, workspace_metadata_path = self._persist(
                run_root=run_root,
                workspace=workspace,
                benchmark_run=benchmark_run,
                collection=collection,
                classification=classification,
                final_report=final_report,
                run_state=run_state,
            )
            return BenchmarkExecutionResult(
                execution_id=execution_id,
                execution_root=execution_root,
                workspace=workspace,
                run_state=run_state,
                final_report=final_report,
                collection=collection,
                classification=classification,
                benchmark_run=benchmark_run,
                minecraft_result=minecraft,
                project_snapshot=project_snapshot,
                benchmark_run_path=benchmark_run_path,
                benchmark_collection_path=collection_path,
                benchmark_classification_path=classification_path,
                workspace_metadata_path=workspace_metadata_path,
                runtime_storage_root=runtime_storage.storage_root,
            )
        finally:
            if not preserve_workspace:
                workspace.cleanup()

    def _maybe_run_minecraft(
        self,
        task: BenchmarkTask,
        config: BenchmarkConfig,
        *,
        run_state: RunState,
        final_report: FinalReport,
        workspace: BenchmarkWorkspace,
        benchmark_run_id: str,
        filesystem_run_id: str,
        minecraft_runner: MinecraftTestRunner | None,
    ) -> MinecraftTestResult | None:
        if not task.validation.minecraft:
            return None
        runner = minecraft_runner
        if runner is None:
            return None
        final_build = final_report.final_build or (run_state.build_results[-1] if run_state.build_results else None)
        artifact = final_report.artifact or run_state.artifact_result
        if final_build is None or artifact is None or artifact.path is None:
            return None
        spec = _minecraft_spec_for_task(
            task,
            artifact_path=artifact.path,
            artifact_sha256=str(artifact.metadata.get("sha256", "")) if isinstance(artifact.metadata, Mapping) else "",
        )
        expected_sha256 = None
        if isinstance(task.acceptance.spec, Mapping):
            expected_sha256 = task.acceptance.spec.get("expected_sha256")
        return runner.run(
            spec,
            run_id=filesystem_run_id,
            java_version=task.environment.java_version,
            expected_sha256=str(expected_sha256) if expected_sha256 is not None else None,
        )

    def _benchmark_run(
        self,
        *,
        benchmark_run_id: str,
        task: BenchmarkTask,
        config: BenchmarkConfig,
        attempt: BenchmarkScheduledAttempt,
        pd_agent_commit: str | None,
        workspace: BenchmarkWorkspace,
        run_state: RunState,
        final_report: FinalReport,
        collection: BenchmarkCollection,
        classification: BenchmarkClassification,
        project_snapshot: ProjectSnapshot,
        env_resolution: Mapping[str, Any],
        knowledge_needs: Sequence[KnowledgeNeed],
        runtime_storage: RunStorage,
        fixture_hash_after: str,
    ) -> BenchmarkRun:
        evidence_refs = (
            f"workspace-metadata.json",
            f"benchmark-collection.json",
            f"benchmark-classification.json",
            f"runtime/{run_state.run_id}/run.json",
            f"runtime/{run_state.run_id}/final-report.json",
            f"runtime/{run_state.run_id}/final-report.md",
            *(f"runtime/{run_state.run_id}/{ref}" for ref in final_report.evidence_refs),
        )
        environment_snapshot = _execution_environment_snapshot(
            task=task,
            config=config,
            workspace=workspace,
            project_snapshot=project_snapshot,
            resolution=env_resolution,
            knowledge_needs=knowledge_needs,
            fixture_hash_after=fixture_hash_after,
        )
        return BenchmarkRun(
            benchmark_run_id=benchmark_run_id,
            task_id=task.task_id,
            task_version=task.task_version,
            config_id=config.config_id,
            config_hash=config.config_hash(),
            repetition_index=attempt.repetition_index,
            attempt_index=attempt.attempt_index,
            pd_agent_commit=pd_agent_commit,
            fixture_hash=workspace.canonical_hash_before,
            environment_snapshot=environment_snapshot,
            underlying_run_id=run_state.run_id,
            started_at=run_state.started_at,
            finished_at=final_report.generated_at,
            duration_seconds=collection.duration_seconds,
            execution_status=classification.execution_status,
            task_outcome=classification.task_outcome,
            failure_origin=classification.failure_origin,
            failure_code=classification.failure_code,
            metrics=collection.metrics,
            evidence_refs=evidence_refs,
            notes=collection.inconsistencies,
        )

    def _classify(self, collection: BenchmarkCollection, *, run_state: RunState) -> BenchmarkClassification:
        provider_error = self._provider_error(collection, run_state=run_state)
        if provider_error is not None:
            return self.classifier.classify(collection, runtime_error=provider_error)
        return self.classifier.classify(collection)

    def _provider_error(self, collection: BenchmarkCollection, *, run_state: RunState) -> ProviderError | None:
        metadata = collection.provider_metadata or {}
        raw = metadata.get("provider_error") if isinstance(metadata, Mapping) else None
        if isinstance(raw, Mapping):
            message = str(raw.get("message") or run_state.provider_error_message or run_state.last_error or "provider error")
            return ProviderError(
                message,
                kind=str(raw.get("kind") or run_state.provider_error_kind or "unknown"),
                request_id=(str(raw["request_id"]) if raw.get("request_id") is not None else None),
                status_code=(int(raw["status_code"]) if raw.get("status_code") is not None else None),
                retryable=(bool(raw["retryable"]) if raw.get("retryable") is not None else None),
                provider=(str(raw["provider"]) if raw.get("provider") is not None else None),
                details=dict(raw.get("details", {})) if isinstance(raw.get("details"), Mapping) else None,
            )
        if run_state.provider_error_kind is None:
            return None
        return ProviderError(
            run_state.provider_error_message or run_state.last_error or "provider error",
            kind=run_state.provider_error_kind,
        )

    def _persist(
        self,
        *,
        run_root: Path,
        workspace: BenchmarkWorkspace,
        benchmark_run: BenchmarkRun,
        collection: BenchmarkCollection,
        classification: BenchmarkClassification,
        final_report: FinalReport,
        run_state: RunState,
    ) -> tuple[Path, Path, Path, Path]:
        workspace_metadata_path = _write_json(run_root / "workspace-metadata.json", workspace.to_dict())
        collection_path = _write_json(run_root / "benchmark-collection.json", collection.to_dict())
        classification_path = _write_json(run_root / "benchmark-classification.json", classification.to_dict())
        benchmark_run_path = _write_json(run_root / "benchmark-run.json", benchmark_run.to_dict())
        _write_json(run_root / "run-state.json", run_state.to_dict())
        _write_json(run_root / "final-report.json", final_report.to_dict())
        return benchmark_run_path, collection_path, classification_path, workspace_metadata_path


__all__ = [
    "BenchmarkExecutionResult",
    "BenchmarkExecutor",
]
