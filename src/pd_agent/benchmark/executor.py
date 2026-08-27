"""Single-run benchmark executor."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
import hashlib
import inspect
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from pd_agent.artifacts import ArtifactValidator
from pd_agent.brain import (
    FileKnowledgeCache,
    KnowledgeEnvironment,
    KnowledgeEnvironmentResolver,
    KnowledgeNeed,
    KnowledgeRetrievalResult,
    MinecraftBrain,
    PreCodeKnowledgeNeedDeriver,
)
from pd_agent.brain.models import KnowledgeType
from pd_agent.build import GradleBuildRunner
from pd_agent.context import ContextManager, ExternalContextSource, ProjectContextSource, RunContextSource
from pd_agent.core import ExecutionLimits, ModelProvider, ProviderError, RunState
from pd_agent.minecraft import (
    MinecraftEvidencePaths,
    MinecraftObservationType,
    MinecraftTargetMetadata,
    MinecraftTestResult,
    MinecraftTestRunner,
    MinecraftTestSpec,
    MinecraftTestStatus,
)
from pd_agent.minecraft.errors import MinecraftTestValidationError, UnsupportedMinecraftEnvironmentError
from pd_agent.project import (
    ProjectInspector,
    ProjectInspectionStatus,
    ProjectSnapshot,
    resolve_logical_resource_path,
)
from pd_agent.reporting import FinalReport, RunStorage
from pd_agent.tools import ToolExecutor
from pd_agent.validation import PreBuildWorkspaceValidator

from .acceptance import (
    AcceptanceMinecraftObservationEvaluation,
    AcceptanceResourceEvaluation,
    evaluate_required_minecraft_observations,
    evaluate_required_resources,
)
from .dependencies import (
    ResolvedRuntimeModDependency,
    RuntimeModDependencyResolutionError,
    resolve_runtime_mod_dependencies,
)
from .environment import BenchmarkGradleEnvironment
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
from .functional import BenchmarkFunctionalValidator
from .public_validation import build_public_validation_contract
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
    if not fragment:
        return "run"
    if len(fragment) <= 24:
        return fragment
    return hashlib.sha256(fragment.encode("utf-8")).hexdigest()[:16]


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
    return ContextManager(
        sources=(
            ("project", ProjectContextSource()),
            ("run", RunContextSource()),
            ("external", ExternalContextSource()),
        )
    )


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


def _task_mutation_targets(task: BenchmarkTask, project_snapshot: ProjectSnapshot) -> tuple[str, ...]:
    """Expose minimal source/resource targets as internal progress metadata."""

    spec = task.acceptance.spec if isinstance(task.acceptance.spec, Mapping) else {}
    raw_resources = spec.get("required_resources", ())
    if not isinstance(raw_resources, Sequence) or isinstance(raw_resources, (str, bytes, bytearray)):
        return ()
    targets: list[str] = ["role:source"] if task.validation.source_change else []
    for resource in raw_resources:
        if isinstance(resource, Mapping) and resource.get("path"):
            targets.append(resolve_logical_resource_path(project_snapshot, str(resource["path"])))
    return tuple(dict.fromkeys(targets))


def _target_mod_id_for_task(task: BenchmarkTask) -> str:
    """Resolve the expected Fabric mod id from the acceptance contract."""

    spec = task.acceptance.spec if isinstance(task.acceptance.spec, Mapping) else {}
    preservation = spec.get("preservation_invariants")
    preservation_mapping = preservation if isinstance(preservation, Mapping) else {}
    candidates = (
        spec.get("target_mod_id"),
        spec.get("mod_id"),
        preservation_mapping.get("mod_id"),
    )
    for candidate in candidates:
        value = str(candidate).strip() if candidate is not None else ""
        if value:
            return value
    raise ValueError(
        "acceptance contract missing target mod id: expected target_mod_id, mod_id, "
        "or preservation_invariants.mod_id"
    )


def _minecraft_spec_for_task(
    task: BenchmarkTask,
    *,
    artifact_path: Path,
    artifact_sha256: str,
    default_timeout_seconds: int,
    runtime_mod_jars: Sequence[Path] = (),
) -> MinecraftTestSpec:
    spec = task.acceptance.spec if isinstance(task.acceptance.spec, Mapping) else {}
    target_mod_id = _target_mod_id_for_task(task)
    test_id = str(spec.get("test_id") or f"{task.task_id}:{task.task_version}").strip()
    observation_type = str(spec.get("observation_type") or MinecraftObservationType.LEGACY_BLOCK_STATE.value).strip()
    observation_params = spec.get("observation_params")
    if observation_params is None:
        observation_params = spec.get("expectations", {})
    minecraft_version = str(spec.get("minecraft_version") or task.environment.minecraft_version or "").strip()
    loader_version = str(spec.get("loader_version") or task.environment.loader_version or "").strip()
    timeout_seconds = int(spec.get("timeout_seconds", default_timeout_seconds))
    expect_neighbor_update = bool(spec.get("expected_neighbor_update", spec.get("expect_neighbor_update", False)))
    return MinecraftTestSpec(
        target_jar=artifact_path,
        target_mod_id=target_mod_id,
        minecraft_version=minecraft_version,
        loader_version=loader_version,
        test_id=test_id,
        observation_type=observation_type,
        observation_params=observation_params,
        timeout_seconds=timeout_seconds,
        expect_neighbor_update=expect_neighbor_update,
        runtime_mod_jars=tuple(runtime_mod_jars),
    )


def _task_acceptance_spec(task: BenchmarkTask) -> Mapping[str, Any]:
    return task.acceptance.spec if isinstance(task.acceptance.spec, Mapping) else {}


def _relative_minecraft_target_path(artifact_path: Path, project_root: Path) -> Path:
    resolved_target = Path(artifact_path).resolve(strict=True)
    resolved_root = Path(project_root).resolve(strict=True)
    try:
        return resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise BenchmarkWorkspaceError(
            f"minecraft target jar is outside minecraft runner project_root: {resolved_target} not within {resolved_root}"
        ) from exc


def _minecraft_infra_error_result(
    *,
    task: BenchmarkTask,
    artifact: Any,
    run_id: str,
    reason: str,
    target_jar: Path,
    evidence_root: Path,
    default_timeout_seconds: int,
) -> MinecraftTestResult:
    artifact_metadata = artifact.metadata if isinstance(artifact.metadata, Mapping) else {}
    target_sha256 = str(artifact_metadata.get("sha256", "")) if isinstance(artifact_metadata, Mapping) else ""
    spec = _minecraft_spec_for_task(
        task,
        artifact_path=target_jar,
        artifact_sha256=target_sha256,
        default_timeout_seconds=default_timeout_seconds,
    )
    target = MinecraftTargetMetadata(
        path=Path(artifact.path) if artifact.path is not None else target_jar,
        size_bytes=int(getattr(artifact, "size", 0)),
        sha256=target_sha256,
        mod_id=spec.target_mod_id,
        minecraft_version=spec.minecraft_version,
        loader_version=spec.loader_version,
        java_version=task.environment.java_version,
    )
    now = datetime.now(timezone.utc)
    return MinecraftTestResult(
        run_id=run_id,
        status=MinecraftTestStatus.INFRA_ERROR,
        reason=reason,
        spec=spec,
        target=target,
        evidence_paths=MinecraftEvidencePaths(root=evidence_root / run_id),
        started_at=now,
        finished_at=now,
        duration_seconds=0.0,
        metadata={"phase": "preflight", "reason": reason},
    )


def _combined_minecraft_result(
    *,
    base_result: MinecraftTestResult,
    resource_evaluation: AcceptanceResourceEvaluation,
    observation_evaluation: AcceptanceMinecraftObservationEvaluation,
    observation_results: Sequence[MinecraftTestResult],
) -> MinecraftTestResult:
    observation_payloads = [result.to_dict() for result in observation_results]
    metadata = {
        **dict(base_result.metadata),
        "acceptance_evaluation": {
            "resources": resource_evaluation.to_dict(),
            "minecraft_observations": observation_evaluation.to_dict(),
            "minecraft_results": observation_payloads,
        },
        "minecraft_acceptance_results": observation_payloads,
    }

    final_status = base_result.status
    final_reason = base_result.reason

    if observation_results:
        final_status = observation_results[0].status
        final_reason = observation_results[0].reason
        for result in observation_results:
            if result.status in {MinecraftTestStatus.CRASH, MinecraftTestStatus.TIMEOUT, MinecraftTestStatus.INFRA_ERROR}:
                final_status = result.status
                final_reason = result.reason
                break
            if result.status == MinecraftTestStatus.FAIL and final_status not in {
                MinecraftTestStatus.CRASH,
                MinecraftTestStatus.TIMEOUT,
                MinecraftTestStatus.INFRA_ERROR,
            }:
                final_status = MinecraftTestStatus.FAIL
                final_reason = result.reason

    if not resource_evaluation.passed and final_status not in {
        MinecraftTestStatus.CRASH,
        MinecraftTestStatus.TIMEOUT,
        MinecraftTestStatus.INFRA_ERROR,
    }:
        final_status = MinecraftTestStatus.FAIL
        final_reason = resource_evaluation.violations[0] if resource_evaluation.violations else "resource requirements not satisfied"

    return replace(
        base_result,
        status=final_status,
        reason=final_reason,
        metadata=metadata,
    )


def _execution_environment_snapshot(
    *,
    task: BenchmarkTask,
    config: BenchmarkConfig,
    workspace: BenchmarkWorkspace,
    project_snapshot: ProjectSnapshot,
    resolution: Mapping[str, Any] | None,
    knowledge_needs: Sequence[KnowledgeNeed],
    gradle_environment: BenchmarkGradleEnvironment | None = None,
    runtime_mod_dependencies: Sequence[Mapping[str, Any]] | None = None,
    fixture_hash_after: str | None = None,
) -> dict[str, Any]:
    snapshot = {
        "task": task.to_dict(),
        "config": config.to_dict(),
        "benchmark_root": str(workspace.benchmark_root),
        "workspace_root": str(workspace.workspace_root),
        "fixture_identity_algorithm": workspace.identity_algorithm,
        "canonical_fixture_hash": workspace.canonical_hash_before,
        "workspace_hash_initial": workspace.workspace_hash_initial,
        "project_snapshot": project_snapshot.to_dict(),
        "knowledge_needs": [need.to_dict() for need in knowledge_needs],
    }
    if resolution is not None:
        snapshot["knowledge_environment"] = resolution
    if gradle_environment is not None:
        snapshot["gradle_environment"] = gradle_environment.to_dict()
    if runtime_mod_dependencies is not None:
        snapshot["runtime_mod_dependencies"] = [dict(item) for item in runtime_mod_dependencies]
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
    gradle_environment: BenchmarkGradleEnvironment | None = None
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
            identity_algorithm=task.fixture.identity_algorithm,
        )
        resolved_runtime_mod_dependencies: tuple[ResolvedRuntimeModDependency, ...] = ()

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

            if knowledge_needs is not None:
                requested_needs = tuple(knowledge_needs)
            else:
                requested_needs = _task_knowledge_needs(task, environment=resolved_environment)
                if not requested_needs and config.brain_enabled:
                    spec = task.acceptance.spec if isinstance(task.acceptance.spec, Mapping) else {}
                    signals = tuple(str(value) for value in task.tags)
                    requested_needs = PreCodeKnowledgeNeedDeriver().derive(
                        f"{task.description}\n{task.prompt}",
                        resolved_environment,
                        capability_signals=signals,
                        metadata=spec,
                    ).needs
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
            runtime_mod_dependency_resolution_error: RuntimeModDependencyResolutionError | None = None
            if self.gradle_environment is not None:
                try:
                    resolved_runtime_mod_dependencies = resolve_runtime_mod_dependencies(
                        workspace.workspace_root,
                        gradle_user_home=self.gradle_environment.gradle_user_home,
                        project_snapshot=project_snapshot,
                    )
                except RuntimeModDependencyResolutionError as exc:
                    runtime_mod_dependency_resolution_error = exc
                    resolved_runtime_mod_dependencies = ()

            try:
                public_validation_contract = build_public_validation_contract(task.acceptance)
            except ValueError:
                # Legacy acceptance remains on the executor fallback until its
                # public contract is explicitly compatible with Batch 3.
                public_validation_contract = None
            functional_validator = None
            if public_validation_contract is not None and (task.validation.artifact or task.validation.minecraft):
                functional_validator = BenchmarkFunctionalValidator(
                    acceptance_spec=_task_acceptance_spec(task),
                    runtime_check=lambda artifact, run_id: (
                        _minecraft_infra_error_result(
                            task=task,
                            artifact=artifact,
                            run_id=run_id,
                            reason=str(runtime_mod_dependency_resolution_error),
                            target_jar=Path(artifact.path) if artifact.path is not None else workspace.workspace_root,
                            evidence_root=workspace.workspace_root / "evidence" / "minecraft",
                            default_timeout_seconds=execution_limits.process_timeout_seconds,
                        )
                        if runtime_mod_dependency_resolution_error is not None
                        else self._maybe_run_minecraft(
                            task,
                            config,
                            run_state=None,
                            final_report=None,
                            workspace=workspace,
                            project_snapshot=project_snapshot,
                            benchmark_run_id=benchmark_run_id,
                            filesystem_run_id=run_id,
                            minecraft_runner=minecraft_runner or self.minecraft_runner,
                            runtime_mod_dependencies=resolved_runtime_mod_dependencies,
                            artifact_override=artifact,
                        )
                    ),
                )
            controller = RunController(
                provider=self.provider,
                storage=runtime_storage,
                build_runner=self.build_runner,
                artifact_validator=self.artifact_validator,
                context_manager=context_manager,
                tool_executor=self.tool_executor,
                limits=execution_limits,
                model_config=dict(config.model_config),
                pre_build_validator=PreBuildWorkspaceValidator(
                    resource_roots=project_snapshot.resource_roots,
                ),
                functional_validator=functional_validator,
            )
            run_kwargs = {
                "external_context": external_context,
                "model_config": dict(config.model_config),
                "pending_mutation_targets": _task_mutation_targets(task, project_snapshot),
            }
            if "validation_contract" in inspect.signature(controller.run).parameters:
                run_kwargs["validation_contract"] = public_validation_contract
            run_state, final_report = controller.run(workspace.workspace_root, task.prompt, **run_kwargs)

            if runtime_mod_dependency_resolution_error is not None:
                artifact = final_report.artifact or run_state.artifact_result
                target_jar = Path(artifact.path) if artifact is not None and artifact.path is not None else workspace.workspace_root
                minecraft = _minecraft_infra_error_result(
                    task=task,
                    artifact=artifact,
                    run_id=run_fragment,
                    reason=str(runtime_mod_dependency_resolution_error),
                    target_jar=target_jar,
                    evidence_root=workspace.workspace_root / "evidence" / "minecraft",
                    default_timeout_seconds=execution_limits.process_timeout_seconds,
                )
            elif functional_validator is None or not any(
                result.stage.value in {"POST_ARTIFACT", "RUNTIME"}
                for result in final_report.validation_results
            ):
                # Test doubles and older controller integrations do not expose
                # the Batch 3 evidence yet; retain the legacy collector path.
                minecraft = self._maybe_run_minecraft(
                    task,
                    config,
                    run_state=run_state,
                    final_report=final_report,
                    workspace=workspace,
                    project_snapshot=project_snapshot,
                    benchmark_run_id=benchmark_run_id,
                    filesystem_run_id=run_fragment,
                    minecraft_runner=minecraft_runner or self.minecraft_runner,
                    runtime_mod_dependencies=resolved_runtime_mod_dependencies,
                )
            else:
                minecraft = functional_validator.last_minecraft_result
            runtime_mod_dependency_records = tuple(dependency.to_dict() for dependency in resolved_runtime_mod_dependencies)
            if minecraft is not None and runtime_mod_dependency_records:
                minecraft = replace(
                    minecraft,
                    metadata={
                        **dict(minecraft.metadata),
                        "runtime_mod_dependencies": list(runtime_mod_dependency_records),
                    },
                )
            fixture_hash_after = compute_fixture_identity(
                workspace.source_fixture,
                algorithm=workspace.identity_algorithm,
            )
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
                runtime_mod_dependencies=runtime_mod_dependency_records or None,
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
        run_state: RunState | None,
        final_report: FinalReport | None,
        workspace: BenchmarkWorkspace,
        project_snapshot: ProjectSnapshot,
        benchmark_run_id: str,
        filesystem_run_id: str,
        minecraft_runner: MinecraftTestRunner | None,
        runtime_mod_dependencies: Sequence[ResolvedRuntimeModDependency] | None = None,
        artifact_override: Any | None = None,
    ) -> MinecraftTestResult | None:
        if not task.validation.minecraft:
            return None
        runner = minecraft_runner
        artifact = artifact_override or (final_report.artifact if final_report is not None else None)
        if artifact is None and run_state is not None:
            artifact = run_state.artifact_result
        if artifact is None or artifact.path is None:
            return None
        target_root = Path(runner.project_root) if runner is not None else workspace.workspace_root
        execution_limits = _benchmark_execution_limits(config)
        acceptance_spec = _task_acceptance_spec(task)
        try:
            target_jar = _relative_minecraft_target_path(artifact.path, target_root)
        except (BenchmarkWorkspaceError, FileNotFoundError, OSError) as exc:
            return _minecraft_infra_error_result(
                task=task,
                artifact=artifact,
                run_id=filesystem_run_id,
                reason=str(exc),
                target_jar=artifact.path,
                evidence_root=workspace.workspace_root / "evidence" / "minecraft",
                default_timeout_seconds=execution_limits.process_timeout_seconds,
            )
        runtime_mod_jars: tuple[Path, ...] = tuple(dependency.path for dependency in runtime_mod_dependencies or ())
        primary_spec = _minecraft_spec_for_task(
            task,
            artifact_path=target_jar,
            artifact_sha256=str(artifact.metadata.get("sha256", "")) if isinstance(artifact.metadata, Mapping) else "",
            default_timeout_seconds=execution_limits.process_timeout_seconds,
            runtime_mod_jars=runtime_mod_jars,
        )
        if runner is None:
            return _minecraft_infra_error_result(
                task=task,
                artifact=artifact,
                run_id=filesystem_run_id,
                reason="minecraft runner is required for minecraft validation",
                target_jar=target_jar,
                evidence_root=workspace.workspace_root / "evidence" / "minecraft",
                default_timeout_seconds=execution_limits.process_timeout_seconds,
            )
        observation_evaluation = evaluate_required_minecraft_observations(primary_spec, acceptance_spec)
        if not observation_evaluation.passed:
            return _minecraft_infra_error_result(
                task=task,
                artifact=artifact,
                run_id=filesystem_run_id,
                reason="invalid required minecraft observations: " + "; ".join(observation_evaluation.violations),
                target_jar=target_jar,
                evidence_root=workspace.workspace_root / "evidence" / "minecraft",
                default_timeout_seconds=execution_limits.process_timeout_seconds,
            )
        resource_evaluation = evaluate_required_resources(artifact.path, acceptance_spec)
        expected_sha256 = None
        if isinstance(acceptance_spec, Mapping):
            expected_sha256 = acceptance_spec.get("expected_sha256")
        observation_results: list[MinecraftTestResult] = []
        try:
            observation_results.append(
                runner.run(
                    primary_spec,
                    run_id=filesystem_run_id,
                    java_version=task.environment.java_version,
                    expected_sha256=str(expected_sha256) if expected_sha256 is not None else None,
                    authorized_runtime_roots=(
                        (
                            workspace.workspace_root,
                            self.gradle_environment.gradle_user_home,
                        )
                        if self.gradle_environment is not None
                        else (workspace.workspace_root,)
                    ),
                )
            )
            for index, extra_spec in enumerate(observation_evaluation.required_observations, start=1):
                observation_results.append(
                    runner.run(
                        extra_spec,
                        run_id=f"{filesystem_run_id}-obs-{index}",
                        java_version=task.environment.java_version,
                        expected_sha256=str(expected_sha256) if expected_sha256 is not None else None,
                        authorized_runtime_roots=(
                            (
                                workspace.workspace_root,
                                self.gradle_environment.gradle_user_home,
                            )
                            if self.gradle_environment is not None
                            else (workspace.workspace_root,)
                        ),
                    )
                )
        except (MinecraftTestValidationError, UnsupportedMinecraftEnvironmentError) as exc:
            return _minecraft_infra_error_result(
                task=task,
                artifact=artifact,
                run_id=filesystem_run_id,
                reason=str(exc),
                target_jar=target_jar,
                evidence_root=workspace.workspace_root / "evidence" / "minecraft",
                default_timeout_seconds=execution_limits.process_timeout_seconds,
            )
        if not observation_results:
            return _minecraft_infra_error_result(
                task=task,
                artifact=artifact,
                run_id=filesystem_run_id,
                reason="minecraft validation did not produce an observation result",
                target_jar=target_jar,
                evidence_root=workspace.workspace_root / "evidence" / "minecraft",
                default_timeout_seconds=execution_limits.process_timeout_seconds,
            )
        return _combined_minecraft_result(
            base_result=observation_results[0],
            resource_evaluation=resource_evaluation,
            observation_evaluation=observation_evaluation,
            observation_results=tuple(observation_results),
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
        runtime_mod_dependencies: Sequence[Mapping[str, Any]] = (),
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
            gradle_environment=self.gradle_environment,
            runtime_mod_dependencies=runtime_mod_dependencies,
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
