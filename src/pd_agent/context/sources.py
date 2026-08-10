"""Context sources for PD Agent v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
import json

from pd_agent.core import BuildResult
from pd_agent.project import ProjectSnapshot
from pd_agent.reporting.redaction import json_ready

from .models import ContextItem, ContextRequest
from .knowledge import KnowledgeRetrievalResult, KnowledgeTrace, SelectedKnowledge


@dataclass(frozen=True, slots=True)
class ProjectContextSource:
    """Project snapshot to compact context."""

    name: str = "project"

    def get(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        snapshot = request.project_snapshot
        if snapshot is None:
            return ()
        return (
            ContextItem.from_text(
                source=self.name,
                priority=10,
                label="project-overview",
                content=_project_overview(snapshot),
                metadata={
                    "project_root": _path_text(snapshot.project_root),
                    "status": snapshot.status.value,
                    "issues": list(snapshot.issues),
                    "target_subproject": _path_text(snapshot.target_subproject),
                },
            ),
            ContextItem.from_text(
                source=self.name,
                priority=20,
                label="project-structure",
                content=_project_structure(snapshot),
                metadata={
                    "fabric_manifests": len(snapshot.fabric_manifests),
                    "modules": len(snapshot.modules),
                    "relevant_files": len(snapshot.relevant_files),
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class RunContextSource:
    """Run state and evidence to compact context."""

    name: str = "run"
    log_tail_bytes: int = 4096

    def get(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        run_state = request.run_state
        if run_state is None:
            return ()
        items = [
            ContextItem.from_text(
                source=self.name,
                priority=30,
                label="run-state",
                content=_run_state_summary(run_state),
                metadata={
                    "run_id": run_state.run_id,
                    "state": run_state.state.value,
                },
            ),
            ContextItem.from_text(
                source=self.name,
                priority=40,
                label="build-results",
                content=_build_results_summary(run_state.build_results),
                metadata={
                    "build_attempt_count": run_state.build_attempt_count,
                    "build_results": len(run_state.build_results),
                },
            ),
        ]
        if run_state.build_results:
            latest = run_state.build_results[-1]
            items.append(
                ContextItem.from_text(
                    source=self.name,
                    priority=45,
                    label="latest-build-log",
                    content=_build_log_summary(latest, tail_bytes=self.log_tail_bytes),
                    metadata={
                        "attempt": latest.attempt,
                        "exit_code": latest.exit_code,
                        "success": latest.success,
                    },
                )
            )
        if run_state.artifact_result is not None:
            items.append(
                ContextItem.from_text(
                    source=self.name,
                    priority=50,
                    label="artifact-result",
                    content=_artifact_summary(run_state.artifact_result),
                    metadata={
                        "classification": run_state.artifact_result.classification,
                    },
                )
            )
        return tuple(items)


@dataclass(frozen=True, slots=True)
class ExternalContextSource:
    """Explicit external context."""

    name: str = "external"

    def get(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        items: list[ContextItem] = []
        for index, raw in enumerate(request.external_context, start=1):
            if isinstance(raw, ContextItem):
                items.append(raw)
                continue
            if isinstance(raw, (KnowledgeRetrievalResult, SelectedKnowledge, KnowledgeTrace)):
                continue
            if isinstance(raw, str):
                items.append(
                    ContextItem.from_text(
                        source=self.name,
                        priority=100,
                        label=f"external-{index}",
                        content=raw,
                    )
                )
                continue
            if isinstance(raw, Mapping):
                items.append(
                    ContextItem.from_text(
                        source=str(raw.get("source", self.name)),
                        priority=int(raw.get("priority", 100)),
                        label=raw.get("label"),
                        content=str(raw.get("content", "")),
                        metadata=dict(raw.get("metadata", {})),
                        truncated=bool(raw.get("truncated", False)),
                    )
                )
                continue
            items.append(
                ContextItem.from_text(
                    source=self.name,
                    priority=100,
                    label=f"external-{index}",
                    content=str(raw),
                    metadata={"kind": type(raw).__name__},
                )
            )
        return tuple(items)


def _project_overview(snapshot: ProjectSnapshot) -> str:
    lines = [
        f"project_root: {_path_text(snapshot.project_root)}",
        f"status: {snapshot.status.value}",
        f"target_subproject: {_path_text(snapshot.target_subproject)}",
    ]
    if snapshot.issues:
        lines.append(f"issues: {list(snapshot.issues)}")
    if snapshot.metadata_errors:
        lines.append(f"metadata_errors: {list(snapshot.metadata_errors)}")
    if snapshot.detected_versions:
        lines.append(f"detected_versions: {_versions(snapshot.detected_versions)}")
    if snapshot.git.present:
        lines.append(
            f"git: {json_ready({'branch': snapshot.git.branch, 'head': snapshot.git.head, 'clean': snapshot.git.working_tree_clean, 'status': list(snapshot.git.status_porcelain[:10])})}"
        )
        if snapshot.git.diff is not None:
            lines.append(f"git_diff_excerpt: {_excerpt_lines(snapshot.git.diff.text, 12)}")
        if snapshot.git.cached_diff is not None:
            lines.append(f"git_cached_diff_excerpt: {_excerpt_lines(snapshot.git.cached_diff.text, 12)}")
    return "\n".join(lines)


def _project_structure(snapshot: ProjectSnapshot) -> str:
    lines = [
        f"settings_files: {_paths(snapshot.settings_files)}",
        f"build_files: {_paths(snapshot.build_files)}",
        f"gradle_properties: {_path_text(snapshot.gradle_properties)}",
        f"version_catalogs: {_paths(snapshot.version_catalogs)}",
        f"source_roots: {_paths(snapshot.source_roots)}",
        f"resource_roots: {_paths(snapshot.resource_roots)}",
        f"relevant_files: {_paths(snapshot.relevant_files[:20])}",
    ]
    if snapshot.modules:
        lines.append(f"modules: {_module_summary(snapshot.modules)}")
    if snapshot.fabric_manifests:
        lines.append(f"fabric_manifests: {_manifest_summary(snapshot.fabric_manifests)}")
    if snapshot.mixin_configs:
        lines.append(f"mixin_configs: {_mixin_summary(snapshot.mixin_configs)}")
    return "\n".join(lines)


def _run_state_summary(run_state) -> str:
    lines = [
        f"run_id: {run_state.run_id}",
        f"task: {run_state.task}",
        f"state: {run_state.state.value}",
        f"current_plan: {run_state.current_plan}",
        f"changed_files: {list(run_state.changed_files)}",
        f"tool_call_count: {run_state.tool_call_count}",
        f"agent_step_count: {run_state.agent_step_count}",
        f"build_attempt_count: {run_state.build_attempt_count}",
        f"last_error: {run_state.last_error}",
        f"termination_reason: {run_state.termination_reason}",
    ]
    return "\n".join(lines)


def _build_results_summary(build_results: tuple[BuildResult, ...]) -> str:
    if not build_results:
        return "build_results: []"
    lines = ["build_results:"]
    for result in build_results:
        lines.append(
            f"- attempt={result.attempt} exit_code={result.exit_code} success={result.success} duration={result.duration_seconds:.3f}s"
        )
    return "\n".join(lines)


def _build_log_summary(result: BuildResult, *, tail_bytes: int) -> str:
    stdout_tail = _tail_utf8(result.stdout_log, tail_bytes)
    stderr_tail = _tail_utf8(result.stderr_log, tail_bytes)
    lines = [
        f"attempt: {result.attempt}",
        f"command_display: {result.command_display}",
        f"exit_code: {result.exit_code}",
        "stdout:",
        stdout_tail,
        "stderr:",
        stderr_tail,
    ]
    return "\n".join(lines)


def _artifact_summary(artifact_result) -> str:
    return "\n".join(
        [
            f"path: {_path_text(artifact_result.path)}",
            f"size: {artifact_result.size}",
            f"timestamp: {artifact_result.timestamp.isoformat()}",
            f"classification: {artifact_result.classification}",
            f"metadata: {json_ready(dict(artifact_result.metadata))}",
        ]
    )


def _paths(paths: Sequence[Path]) -> list[str]:
    return [_path_text(path) for path in paths]


def _path_text(path: Path | None) -> str | None:
    return path.as_posix() if path is not None else None


def _versions(values: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        key: getattr(value, "value", None) if hasattr(value, "value") else str(value)
        for key, value in values.items()
    }


def _module_summary(modules) -> list[str]:
    return [
        f"{module.path.as_posix()}:build_files={len(module.build_files)} manifests={len(module.fabric_manifests)}"
        for module in modules
    ]


def _manifest_summary(manifests) -> list[str]:
    return [
        f"{manifest.path.as_posix()}:id={manifest.mod_id} version={manifest.version} environment={manifest.environment}"
        for manifest in manifests
    ]


def _mixin_summary(mixins) -> list[str]:
    return [f"{mixin.path.as_posix()}:package={mixin.package}" for mixin in mixins]


def _tail_utf8(text: str, limit_bytes: int) -> str:
    if limit_bytes <= 0:
        return "..."
    encoded = text.encode("utf-8")
    if len(encoded) <= limit_bytes:
        return text
    suffix = "..."
    suffix_bytes = len(suffix.encode("utf-8"))
    if limit_bytes <= suffix_bytes:
        return suffix
    budget = limit_bytes - suffix_bytes
    chunk = encoded[-budget:]
    while chunk:
        try:
            return chunk.decode("utf-8") + suffix
        except UnicodeDecodeError as exc:
            if exc.start == 0:
                chunk = chunk[1:]
            else:
                chunk = chunk[: exc.start]
    return suffix


def _excerpt_lines(text: str, max_lines: int) -> str:
    if not text:
        return ""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines] + ["..."])
