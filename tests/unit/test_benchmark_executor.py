from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil

import pytest

from pd_agent.benchmark import (
    BenchmarkConfig,
    BenchmarkCollector,
    BenchmarkExecutionStatus,
    BenchmarkExecutor,
    BenchmarkFailureCode,
    BenchmarkFailureOrigin,
    BenchmarkTask,
    BenchmarkTaskOutcome,
    BenchmarkValidationRequirements,
)
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
from pd_agent.core import ArtifactResult, BuildResult, RunState, RunStatus
from pd_agent.minecraft import MinecraftEvidencePaths, MinecraftTargetMetadata, MinecraftTestResult, MinecraftTestSpec, MinecraftTestStatus
from pd_agent.reporting import FinalReport, RunStorage
from pd_agent.context.knowledge import KnowledgeRejection, KnowledgeSourceAttempt, KnowledgeTrace


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _fixture_root() -> Path:
    return Path("tests/fixtures/l11_fabric_fixture").resolve()


def _task(*, minecraft: bool = False, expected_neighbor_update: bool = False, test_id: str = "l8") -> BenchmarkTask:
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
                "spec": {
                    "kind": "registry_lookup",
                    "target_mod_id": "pdagentl11",
                    "minecraft_version": "1.21.11",
                    "loader_version": "0.19.3",
                    "test_id": test_id,
                    "timeout_seconds": 30,
                    "expected_neighbor_update": expected_neighbor_update,
                },
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
    return ArtifactResult(
        path=project_root / "build" / "libs" / "mod.jar",
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
    def __init__(self) -> None:
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


def test_executor_carries_neighbor_expectation_into_minecraft_spec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _FakeController)
    executor = BenchmarkExecutor(
        provider=object(),
        build_runner=object(),
        artifact_validator=object(),
    )
    task = _task(minecraft=True, expected_neighbor_update=True, test_id="block_state_probe_with_signal")
    config = _config(brain_enabled=False)
    fake_minecraft = _FakeMinecraftRunner()
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
    assert kwargs["run_id"] == "attempt-6"


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
