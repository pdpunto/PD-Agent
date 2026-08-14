from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil

import pytest

from pd_agent.benchmark import (
    BenchmarkConfig,
    BenchmarkCollector,
    BenchmarkGradleEnvironment,
    BenchmarkExecutionStatus,
    BenchmarkExecutor,
    BenchmarkFailureCode,
    BenchmarkFailureOrigin,
    BenchmarkTask,
    BenchmarkTaskOutcome,
    BenchmarkValidationRequirements,
)
from pd_agent.benchmark.executor import _default_context_manager, _filesystem_safe_fragment
from pd_agent.brain import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeRetrievalResult,
    KnowledgeRetrievalStatus,
    KnowledgeSourceResult,
    KnowledgeType,
    SourceAuthority,
)
from pd_agent.core import ArtifactResult, BuildResult, ExecutionLimits, RunState, RunStatus
from pd_agent.minecraft import MinecraftEvidencePaths, MinecraftTargetMetadata, MinecraftTestResult, MinecraftTestSpec, MinecraftTestStatus
from pd_agent.minecraft.errors import MinecraftTestValidationError
from pd_agent.reporting import FinalReport, RunStorage
from pd_agent.context import ContextItem
from pd_agent.context.knowledge import KnowledgeRejection, KnowledgeSourceAttempt, KnowledgeTrace


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _fixture_root() -> Path:
    return Path("tests/fixtures/l11_fabric_fixture").resolve()


def _task(
    *,
    minecraft: bool = False,
    expected_neighbor_update: bool = False,
    test_id: str = "l8",
    observation_type: str = "LEGACY_BLOCK_STATE",
    observation_params: dict[str, object] | None = None,
    timeout_seconds: int | None = 30,
) -> BenchmarkTask:
    spec: dict[str, object] = {
        "kind": "registry_lookup",
        "target_mod_id": "pdagentl11",
        "minecraft_version": "1.21.11",
        "loader_version": "0.19.3",
        "test_id": test_id,
        "observation_type": observation_type,
        "expected_neighbor_update": expected_neighbor_update,
    }
    if observation_params is not None:
        spec["observation_params"] = observation_params
    if timeout_seconds is not None:
        spec["timeout_seconds"] = timeout_seconds
    return BenchmarkTask.from_dict(
        {
            "schema_version": 1,
            "task_id": "B001",
            "task_version": "1",
            "description": "Task",
            "prompt": "Update the mod",
            "fixture": {
                "schema_version": 1,
                "fixture_ref": str(_fixture_root()),
                "fixture_identity": "fixture",
                "identity_algorithm": "sha256-tree-v1",
                "metadata": {},
            },
            "validation": {
                "schema_version": 1,
                "build": True,
                "artifact": True,
                "minecraft": minecraft,
                "source_change": True,
            },
            "acceptance": {
                "schema_version": 1,
                "acceptance_type": "minecraft_harness",
                "spec": spec,
                "notes": [],
            },
            "environment": {
                "schema_version": 1,
                "minecraft_version": "1.21.11",
                "loader_version": "0.19.3",
                "loom_version": "1.13.3",
                "yarn_version": "1.21.11+build.6",
                "java_version": "21",
                "fabric_api_version": "0.122.0+1.21.11",
                "extra": {},
            },
            "tags": [],
            "notes": [],
        }
    )


def _config(*, brain_enabled: bool) -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id="cfg-1",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=brain_enabled,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60},
        knowledge_config={"offline": False},
        target_repetition_count=1,
    )


def _config_with_limits(*, brain_enabled: bool, limits: ExecutionLimits) -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id=f"cfg-{'on' if brain_enabled else 'off'}",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=brain_enabled,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60, "provider_retry_limit": 3},
        execution_limits=limits,
        knowledge_config={"offline": False},
        target_repetition_count=1,
    )


def _build(project_root: Path) -> BuildResult:
    return BuildResult(
        attempt=1,
        command_display="gradlew build",
        cwd=project_root,
        started_at=_utc("2026-08-11T10:00:10"),
        duration_seconds=2.0,
        exit_code=0,
        stdout_log="ok",
        stderr_log="",
    )


def _artifact(project_root: Path) -> ArtifactResult:
    artifact_path = project_root / "build" / "libs" / "mod.jar"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("jar", encoding="utf-8")
    return ArtifactResult(
        path=artifact_path,
        size=123,
        timestamp=_utc("2026-08-11T10:00:11"),
        classification="VALID",
        metadata={"sha256": "abc"},
    )


def _run_state(project_root: Path, task: str, *, status: RunStatus, error: str | None = None) -> RunState:
    build = _build(project_root)
    artifact = _artifact(project_root)
    return RunState(
        run_id="11111111-1111-4111-8111-111111111111",
        project_root=project_root,
        task=task,
        state=status,
        started_at=_utc("2026-08-11T10:00:00"),
        changed_files=("src/main/java/dev/pdpunto/l11/ExampleMod.java",),
        tool_call_count=0,
        agent_step_count=1,
        build_attempt_count=1,
        build_results=(build,),
        artifact_result=artifact,
        last_error=error,
        provider_error_kind=None,
        provider_error_message=None,
        termination_reason="completed" if status == RunStatus.COMPLETED else error,
    )


def _final_report(run_state: RunState, *, evidence_refs: tuple[str, ...] = ()) -> FinalReport:
    build = run_state.build_results[-1]
    artifact = run_state.artifact_result
    return FinalReport(
        run_id=run_state.run_id,
        final_state=run_state.state,
        summary="ok",
        project=str(run_state.project_root),
        requested_task=run_state.task,
        files_changed=run_state.changed_files,
        build_attempts=run_state.build_results,
        final_build=build,
        artifact=artifact,
        warnings=(),
        termination_reason=run_state.termination_reason,
        evidence_refs=evidence_refs,
    )


class _FakeController:
    last_init: dict[str, object] = {}
    last_run: dict[str, object] = {}

    def __init__(self, **kwargs: object) -> None:
        self.last_init = dict(kwargs)
        _FakeController.last_init = self.last_init
        self.storage = kwargs["storage"]

    def run(self, project_root: Path, task: str, *, external_context=(), model_config=None):
        _FakeController.last_run = {
            "project_root": project_root,
            "task": task,
            "external_context": tuple(external_context),
            "model_config": dict(model_config or {}),
        }
        run_state = _run_state(project_root, task, status=RunStatus.COMPLETED)
        evidence_refs: tuple[str, ...] = ()
        if external_context:
            env = KnowledgeEnvironment(
                minecraft_version="1.21.11",
                loader_version="0.19.3",
                loom_version="1.13.3",
                mappings_namespace="yarn",
                mappings_version="1.21.11+build.6",
                java_version="21",
            )
            need = external_context[0].need
            trace = KnowledgeTrace(
                run_id=run_state.run_id,
                environment=env,
                needs=(need,),
                source_attempts=(
                    KnowledgeSourceAttempt(
                        source_id="yarn",
                        source_kind="artifact",
                        status=KnowledgeRetrievalStatus.SUCCESS,
                        retrieved_item_ids=("yarn:item:1",),
                        locator="https://maven.fabricmc.net",
                        revision="build.6",
                        checksum="abc123",
                    ),
                ),
                retrieved_item_ids=("yarn:item:1",),
                selected_item_ids=("yarn:item:1",),
                context_item_ids=("yarn:item:1",),
                rejected_items=(),
                misses=(),
            )
            evidence_path = self.storage.store_large_payload(run_state.run_id, "knowledge-trace", trace.to_dict(), 1)
            evidence_refs = (str(evidence_path.relative_to(self.storage.storage_root / run_state.run_id)),)
        final_report = _final_report(run_state, evidence_refs=evidence_refs)
        return run_state, final_report


class _FakeKnowledgeSource:
    source_id = "yarn"
    source_kind = "artifact"
    artifact_version = "1.21.11+build.6"

    def supports(self, need: KnowledgeNeed) -> bool:
        return True

    def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
        return CompatibilityStatus.COMPATIBLE

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeSourceResult:
        provenance = KnowledgeProvenance(
            source_id="yarn",
            source_kind="artifact",
            locator="https://maven.fabricmc.net",
            artifact_or_document_version="1.21.11+build.6",
            revision="build.6",
            checksum_algorithm="sha256",
            checksum="abc123",
        )
        item = KnowledgeItem(
            id="yarn:item:1",
            content={"symbol": {"named": "Registries.BLOCK", "descriptor": "Lnet/minecraft/registry/Registry;"}},
            environment=need.environment,
            authority=SourceAuthority.AUTHORITATIVE_SOURCE,
            provenance=provenance,
            metadata={"match_score": 10},
        )
        return KnowledgeSourceResult(
            status=KnowledgeRetrievalStatus.SUCCESS,
            source_id=self.source_id,
            source_kind=self.source_kind,
            need=need,
            items=(item,),
            provenance=(provenance,),
            error=None,
            cache_key=None,
        )


class _FakeMinecraftRunner:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path("C:/dev/project")
        self.calls: list[tuple[object, dict[str, object]]] = []

    def run(self, spec, **kwargs):
        self.calls.append((spec, dict(kwargs)))
        return MinecraftTestResult(
            run_id=str(kwargs["run_id"]),
            status=MinecraftTestStatus.PASS,
            reason="ok",
            spec=spec,
            target=MinecraftTargetMetadata(
                path=spec.target_jar,
                size_bytes=123,
                sha256=str(kwargs.get("expected_sha256") or "abc"),
                mod_id=spec.target_mod_id,
                minecraft_version=spec.minecraft_version,
                loader_version=spec.loader_version,
                java_version=str(kwargs["java_version"]),
            ),
            evidence_paths=MinecraftEvidencePaths(root=Path(kwargs["run_id"]) / "evidence"),
        )


def _workspace_root(execution_root: Path, scheduled_attempt_id: str, attempt_index: int) -> Path:
    return (
        execution_root
        / "workspaces"
        / _filesystem_safe_fragment(scheduled_attempt_id)
        / f"attempt-{attempt_index:03d}"
        / _fixture_root().name
    )


def _gradle_seed(root: Path) -> Path:
    (root / "wrapper").mkdir(parents=True, exist_ok=True)
    (root / "caches" / "marker.txt").parent.mkdir(parents=True, exist_ok=True)
    (root / "wrapper" / "seed.txt").write_text("wrapper", encoding="utf-8")
    (root / "caches" / "marker.txt").write_text("cache", encoding="utf-8")
    return root


def _context_source_names(manager) -> tuple[str, ...]:  # noqa: ANN001
    return tuple(binding.name for binding in manager._sources)  # noqa: SLF001


def test_default_context_manager_brain_off_preserves_external_context_source() -> None:
    manager = _default_context_manager(False)

    assert _context_source_names(manager) == ("project", "run", "external")


def test_default_context_manager_brain_on_keeps_knowledge_and_external_sources() -> None:
    manager = _default_context_manager(True)

    assert _context_source_names(manager) == ("project", "run", "knowledge", "external")


def test_default_context_manager_brain_off_keeps_runtime_external_context_visible(tmp_path: Path) -> None:
    manager = _default_context_manager(False)
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    snapshot = None
    run_state = _run_state(root, "task", status=RunStatus.PLANNING)

    bundle = manager.build_context(
        project_snapshot=snapshot,
        run_state=run_state,
        external_context=(
            ContextItem.from_text(source="runtime", priority=5, label="policy", content="ACTION REQUIRED"),
            ContextItem.from_text(source="runtime", priority=6, label="retained-inspection-evidence", content="path: notes.txt"),
        ),
    )

    text = bundle.to_text()
    assert "ACTION REQUIRED" in text
    assert "retained-inspection-evidence" in text
    assert manager.last_knowledge_traces == ()


def test_executor_brain_off_pass_and_cleans_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task()
    config = _config(brain_enabled=False)
    fake_minecraft = _FakeMinecraftRunner()
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-1", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        minecraft_runner=fake_minecraft,
    )

    assert result.classification.execution_status == BenchmarkExecutionStatus.COMPLETED
    assert result.classification.task_outcome == BenchmarkTaskOutcome.PASS
    assert _FakeController.last_run["external_context"] == ()
    assert fake_minecraft.calls == []
    assert not result.workspace.workspace_root.exists()
    assert result.runtime_storage_root.exists()
    assert result.benchmark_run.underlying_run_id == result.run_state.run_id
    assert result.collection.retrieved_count == 0
    assert result.collection.selected_count == 0
    assert result.collection.injected_count == 0


def test_executor_brain_on_injects_context_and_traces(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
        knowledge_source=_FakeKnowledgeSource(),
    )
    task = _task()
    config = _config(brain_enabled=True)
    need = KnowledgeNeed(
        id="need-1",
        type=KnowledgeType.SYMBOL,
        query="Registries.BLOCK lookup",
        environment=KnowledgeEnvironment(
            minecraft_version="1.21.11",
            loader_version="0.19.3",
            loom_version="1.13.3",
            mappings_namespace="yarn",
            mappings_version="1.21.11+build.6",
            java_version="21",
        ),
    )
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-2", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        knowledge_needs=(need,),
    )

    assert len(_FakeController.last_run["external_context"]) == 1
    retrieved = _FakeController.last_run["external_context"][0]
    assert isinstance(retrieved, KnowledgeRetrievalResult)
    assert retrieved.items[0].id == "yarn:item:1"
    assert result.collection.retrieved_count == 1
    assert result.collection.selected_count == 1
    assert result.collection.injected_count == 1
    assert result.collection.knowledge_traces[0].retrieved_item_ids == ("yarn:item:1",)
    assert result.collection.knowledge_traces[0].selected_item_ids == ("yarn:item:1",)
    assert result.collection.knowledge_traces[0].context_item_ids == ("yarn:item:1",)


def test_executor_records_gradle_environment_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    seed_root = _gradle_seed(tmp_path / "seed")
    execution_root = tmp_path / "exec"
    execution_root.mkdir()
    gradle_environment = BenchmarkGradleEnvironment.prepare(
        seed_root=seed_root,
        execution_root=execution_root,
    )
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
        gradle_environment=gradle_environment,
    )
    task = _task()
    config = _config(brain_enabled=False)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-gradle-env", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=execution_root,
    )

    environment_snapshot = result.benchmark_run.environment_snapshot["gradle_environment"]
    assert environment_snapshot["bootstrap_status"] == "READY"
    assert environment_snapshot["offline"] is True
    assert environment_snapshot["gradle_user_home"].endswith("gradle-user-home")
    assert environment_snapshot["seed_manifest"]["seed_id"] == "gradle-wrapper-caches"
    assert environment_snapshot["seed_manifest"]["identity_hash"] is not None


@pytest.mark.parametrize("brain_enabled", [False, True])
def test_executor_propagates_execution_limits_to_controller(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, brain_enabled: bool) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    limits = ExecutionLimits(
        max_agent_steps=25,
        max_tool_calls=50,
        max_build_attempts=7,
        provider_retry_limit=3,
        process_timeout_seconds=601,
        max_tool_output_bytes=1001,
        max_context_bytes=2001,
    )
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task()
    config = _config_with_limits(brain_enabled=brain_enabled, limits=limits)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": f"attempt-limits-{brain_enabled}", "attempt_index": 1, "repetition_index": 0})()

    executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
    )

    applied = _FakeController.last_init["limits"]
    assert applied == limits
    assert applied.max_agent_steps == 25
    assert applied.max_tool_calls == 50
    assert applied.max_build_attempts == 7
    assert applied.provider_retry_limit == 3
    assert applied.process_timeout_seconds == 601
    assert applied.max_tool_output_bytes == 1001
    assert applied.max_context_bytes == 2001


@pytest.mark.parametrize("brain_enabled", [False, True])
def test_executor_uses_execution_limits_for_minecraft_timeout_when_task_omits_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    brain_enabled: bool,
) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    limits = ExecutionLimits(
        max_agent_steps=25,
        max_tool_calls=50,
        max_build_attempts=7,
        provider_retry_limit=3,
        process_timeout_seconds=123,
        max_tool_output_bytes=1001,
        max_context_bytes=2001,
    )
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(minecraft=True, timeout_seconds=None)
    config = _config_with_limits(brain_enabled=brain_enabled, limits=limits)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": f"attempt-timeout-{brain_enabled}", "attempt_index": 1, "repetition_index": 0})()
    fake_minecraft = _FakeMinecraftRunner(
        project_root=_workspace_root(tmp_path / "exec", scheduled_attempt.scheduled_attempt_id, scheduled_attempt.attempt_index)
    )

    executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        minecraft_runner=fake_minecraft,
    )

    assert fake_minecraft.calls
    spec, _ = fake_minecraft.calls[0]
    assert spec.timeout_seconds == 123


@pytest.mark.parametrize("brain_enabled", [False, True])
def test_executor_prefers_explicit_minecraft_timeout_override_over_execution_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    brain_enabled: bool,
) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    limits = ExecutionLimits(
        max_agent_steps=25,
        max_tool_calls=50,
        max_build_attempts=7,
        provider_retry_limit=3,
        process_timeout_seconds=600,
        max_tool_output_bytes=1001,
        max_context_bytes=2001,
    )
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(minecraft=True, timeout_seconds=42)
    config = _config_with_limits(brain_enabled=brain_enabled, limits=limits)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": f"attempt-explicit-{brain_enabled}", "attempt_index": 1, "repetition_index": 0})()
    fake_minecraft = _FakeMinecraftRunner(
        project_root=_workspace_root(tmp_path / "exec", scheduled_attempt.scheduled_attempt_id, scheduled_attempt.attempt_index)
    )

    executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        minecraft_runner=fake_minecraft,
    )

    assert fake_minecraft.calls
    spec, _ = fake_minecraft.calls[0]
    assert spec.timeout_seconds == 42


def test_executor_carries_neighbor_expectation_into_minecraft_spec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(minecraft=True, expected_neighbor_update=True, test_id="block_state_probe_with_signal")
    config = _config(brain_enabled=False)
    workspace_root = _workspace_root(tmp_path / "exec", "attempt-6", 1)
    fake_minecraft = _FakeMinecraftRunner(project_root=workspace_root)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-6", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        minecraft_runner=fake_minecraft,
    )

    assert fake_minecraft.calls
    spec, kwargs = fake_minecraft.calls[0]
    assert spec.expect_neighbor_update is True
    assert spec.target_jar == Path("build/libs/mod.jar")
    assert not spec.target_jar.is_absolute()
    assert kwargs["run_id"] == "attempt-6"


def test_executor_carries_registry_observation_into_minecraft_spec(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(
        minecraft=True,
        test_id="server_registry_presence",
        observation_type="REGISTRY_ENTRY_PRESENT",
        observation_params={"registry_kind": "block", "identifier": "minecraft:diamond_block"},
    )
    config = _config(brain_enabled=False)
    workspace_root = _workspace_root(tmp_path / "exec", "attempt-registry", 1)
    fake_minecraft = _FakeMinecraftRunner(project_root=workspace_root)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-registry", "attempt_index": 1, "repetition_index": 0})()

    executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        minecraft_runner=fake_minecraft,
    )

    assert fake_minecraft.calls
    spec, kwargs = fake_minecraft.calls[0]
    assert spec.observation_type.value == "REGISTRY_ENTRY_PRESENT"
    assert spec.observation_params == {"registry_kind": "block", "identifier": "minecraft:diamond_block"}
    assert spec.expect_neighbor_update is False
    assert spec.target_jar == Path("build/libs/mod.jar")
    assert kwargs["run_id"] == "attempt-registry"


def test_executor_blocks_when_minecraft_runner_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(minecraft=True, expected_neighbor_update=True, test_id="block_state_probe_with_signal")
    config = _config(brain_enabled=False)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-missing-runner", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
    )

    assert result.classification.execution_status == BenchmarkExecutionStatus.BLOCKED
    assert result.classification.failure_origin == BenchmarkFailureOrigin.MINECRAFT_HARNESS
    assert result.classification.failure_code == BenchmarkFailureCode.HARNESS_INFRA_ERROR
    assert result.minecraft_result is not None
    assert result.minecraft_result.status == MinecraftTestStatus.INFRA_ERROR
    assert "minecraft runner is required" in result.minecraft_result.reason
    assert result.collection.inconsistencies == ()


def test_executor_blocks_when_minecraft_runner_rejects_target_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _RejectingMinecraftRunner(_FakeMinecraftRunner):
        def run(self, spec, **kwargs):  # noqa: ANN001
            raise MinecraftTestValidationError("target fabric.mod.json is missing main entrypoint")

    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(minecraft=True, expected_neighbor_update=True, test_id="block_state_probe_with_signal")
    config = _config(brain_enabled=False)
    fake_minecraft = _RejectingMinecraftRunner(project_root=tmp_path / "exec" / "workspaces" / "attempt-reject" / "attempt-001" / _fixture_root().name)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-reject", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        minecraft_runner=fake_minecraft,
    )

    assert result.classification.execution_status == BenchmarkExecutionStatus.BLOCKED
    assert result.classification.failure_origin == BenchmarkFailureOrigin.MINECRAFT_HARNESS
    assert result.classification.failure_code == BenchmarkFailureCode.HARNESS_INFRA_ERROR
    assert result.minecraft_result is not None
    assert result.minecraft_result.status == MinecraftTestStatus.INFRA_ERROR
    assert "missing main entrypoint" in result.minecraft_result.reason


def test_executor_blocks_when_minecraft_target_escapes_runner_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _ExternalArtifactController(_FakeController):
        def run(self, project_root: Path, task: str, *, external_context=(), model_config=None):
            run_state = _run_state(project_root, task, status=RunStatus.COMPLETED)
            external_artifact = ArtifactResult(
                path=tmp_path / "external" / "build" / "libs" / "mod.jar",
                size=123,
                timestamp=_utc("2026-08-11T10:00:11"),
                classification="VALID",
                metadata={"sha256": "abc"},
            )
            external_artifact.path.parent.mkdir(parents=True, exist_ok=True)
            external_artifact.path.write_text("jar", encoding="utf-8")
            run_state.artifact_result = external_artifact
            final_report = _final_report(run_state)
            return run_state, final_report

    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _ExternalArtifactController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(minecraft=True, expected_neighbor_update=True, test_id="block_state_probe_with_signal")
    config = _config(brain_enabled=False)
    fake_minecraft = _FakeMinecraftRunner(project_root=tmp_path / "exec" / "workspaces" / "attempt-external" / "attempt-001" / _fixture_root().name)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-external", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        minecraft_runner=fake_minecraft,
    )

    assert result.classification.execution_status == BenchmarkExecutionStatus.BLOCKED
    assert result.classification.failure_origin == BenchmarkFailureOrigin.MINECRAFT_HARNESS
    assert result.classification.failure_code == BenchmarkFailureCode.HARNESS_INFRA_ERROR
    assert result.minecraft_result is not None
    assert result.minecraft_result.status == MinecraftTestStatus.INFRA_ERROR
    assert "outside minecraft runner project_root" in result.minecraft_result.reason
    assert fake_minecraft.calls == []


def test_executor_sanitizes_filesystem_run_fragment_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(minecraft=True, expected_neighbor_update=True, test_id="block_state_probe_with_signal")
    config = _config(brain_enabled=False)
    scheduled_attempt = type(
        "Attempt",
        (),
        {"scheduled_attempt_id": "B001:1:cfg-off:abc:def:0:1", "attempt_index": 7, "repetition_index": 0},
    )()
    fake_minecraft = _FakeMinecraftRunner(
        project_root=_workspace_root(tmp_path / "exec", scheduled_attempt.scheduled_attempt_id, scheduled_attempt.attempt_index)
    )

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
        minecraft_runner=fake_minecraft,
    )

    assert result.benchmark_run.benchmark_run_id == "B001:1:cfg-off:abc:def:0:1"
    assert result.workspace.run_id != result.benchmark_run.benchmark_run_id
    assert ":" not in result.workspace.run_id
    assert ":" not in result.benchmark_run_path.parent.name
    assert fake_minecraft.calls
    _, kwargs = fake_minecraft.calls[0]
    assert kwargs["run_id"] == result.workspace.run_id
    assert ":" not in kwargs["run_id"]


def test_filesystem_safe_fragment_shortens_long_attempt_ids() -> None:
    fragment = _filesystem_safe_fragment("B001:1:" + "x" * 200)

    assert len(fragment) == 16
    assert all(char in "0123456789abcdef" for char in fragment)


@pytest.mark.parametrize(
    "kind, expected_code",
    [
        ("authentication", BenchmarkFailureCode.PROVIDER_AUTH),
        ("rate_limit", BenchmarkFailureCode.PROVIDER_RATE_LIMIT),
        ("timeout", BenchmarkFailureCode.PROVIDER_TIMEOUT),
        ("unavailable", BenchmarkFailureCode.PROVIDER_UNAVAILABLE),
    ],
)
def test_executor_provider_issue_uses_structured_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str, expected_code: BenchmarkFailureCode) -> None:
    class _BlockedController(_FakeController):
        def run(self, project_root: Path, task: str, *, external_context=(), model_config=None):
            run_state = _run_state(project_root, task, status=RunStatus.FAILED, error="provider failed")
            run_state.provider_error_kind = kind
            run_state.provider_error_message = f"{kind} failure"
            final_report = _final_report(run_state)
            return run_state, final_report

    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _BlockedController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task()
    config = _config(brain_enabled=False)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-3", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
    )

    assert result.classification.execution_status == BenchmarkExecutionStatus.BLOCKED
    assert result.classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert result.classification.failure_origin == BenchmarkFailureOrigin.PROVIDER
    assert result.classification.failure_code == expected_code


def test_executor_message_with_provider_word_without_kind_does_not_fake_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _NoKindController(_FakeController):
        def run(self, project_root: Path, task: str, *, external_context=(), model_config=None):
            run_state = _run_state(project_root, task, status=RunStatus.FAILED, error="provider word only")
            final_report = _final_report(run_state)
            return run_state, final_report

    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _NoKindController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task()
    config = _config(brain_enabled=False)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-4", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=_fixture_root(),
        execution_root=tmp_path / "exec",
    )

    assert result.classification.failure_code != BenchmarkFailureCode.PROVIDER_UNAVAILABLE


def test_executor_contamination_invalidates_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    shutil.copytree(_fixture_root(), fixture_root)
    target_file = fixture_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"

    class _MutatingController(_FakeController):
        def run(self, project_root: Path, task: str, *, external_context=(), model_config=None):
            target_file.write_text(target_file.read_text(encoding="utf-8") + "\n// contamination\n", encoding="utf-8")
            run_state = _run_state(project_root, task, status=RunStatus.COMPLETED)
            final_report = _final_report(run_state)
            return run_state, final_report

    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _MutatingController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task()
    config = _config(brain_enabled=False)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-5", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=fixture_root,
        execution_root=tmp_path / "exec",
    )

    assert result.classification.execution_status == BenchmarkExecutionStatus.INVALID
    assert result.classification.task_outcome == BenchmarkTaskOutcome.NOT_EVALUATED
    assert result.classification.failure_origin == BenchmarkFailureOrigin.BENCHMARK_INFRA
    assert result.classification.failure_code == BenchmarkFailureCode.BENCHMARK_CONTAMINATION
    assert result.benchmark_run.environment_snapshot["fixture_integrity"]["contaminated"] is True
    assert result.benchmark_run.environment_snapshot["fixture_integrity"]["canonical_hash_before"] != result.benchmark_run.environment_snapshot["fixture_integrity"]["canonical_hash_after"]
    assert any("fixture contamination detected" in note for note in result.benchmark_run.notes)


def test_executor_contamination_invalidates_even_if_runtime_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    shutil.copytree(_fixture_root(), fixture_root)
    target_file = fixture_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"

    class _FailingController(_FakeController):
        def run(self, project_root: Path, task: str, *, external_context=(), model_config=None):
            target_file.write_text(target_file.read_text(encoding="utf-8") + "\n// contamination\n", encoding="utf-8")
            run_state = _run_state(project_root, task, status=RunStatus.FAILED, error="build failed")
            final_report = _final_report(run_state)
            return run_state, final_report

    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FailingController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task()
    config = _config(brain_enabled=False)
    scheduled_attempt = type("Attempt", (), {"scheduled_attempt_id": "attempt-6", "attempt_index": 1, "repetition_index": 0})()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=fixture_root,
        execution_root=tmp_path / "exec",
    )

    assert result.classification.execution_status == BenchmarkExecutionStatus.INVALID
    assert result.classification.failure_code == BenchmarkFailureCode.BENCHMARK_CONTAMINATION
