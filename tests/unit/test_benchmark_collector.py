from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile

from pd_agent.benchmark import BenchmarkCollector, BenchmarkConfig, BenchmarkTask, BenchmarkValidationRequirements
from pd_agent.brain import KnowledgeEnvironment, KnowledgeItem, KnowledgeNeed, KnowledgeProvenance, KnowledgeRetrievalResult, KnowledgeRetrievalStatus, KnowledgeType, SourceAuthority
from pd_agent.context import KnowledgeSourceAttempt, KnowledgeTrace
from pd_agent.core import AgentResponse, ArtifactResult, BuildResult, RunState, RunStatus
from pd_agent.minecraft import MinecraftEvidencePaths, MinecraftTargetMetadata, MinecraftTestResult, MinecraftTestSpec, MinecraftTestStatus
from pd_agent.project import DetectedValue, ProjectSnapshot
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _task() -> BenchmarkTask:
    return BenchmarkTask.from_dict(
        {
            "schema_version": 1,
            "task_id": "B001",
            "task_version": "1",
            "description": "Task",
            "prompt": "Prompt",
            "fixture": {
                "schema_version": 1,
                "fixture_ref": "tests/fixtures/l11_fabric_fixture",
                "fixture_identity": "sha256:fixture",
                "identity_algorithm": "sha256",
                "metadata": {},
            },
            "validation": {
                "schema_version": 1,
                "build": True,
                "artifact": True,
                "minecraft": True,
                "source_change": True,
            },
            "acceptance": {
                "schema_version": 1,
                "acceptance_type": "minecraft_harness",
                "spec": {"kind": "registry_lookup"},
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


def _config() -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id="cfg-1",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=True,
        model_config={"max_output_tokens": 512},
        provider_config={"timeout_seconds": 60},
        knowledge_config={"cache": "warm"},
        execution_limits=None,
        target_repetition_count=3,
    )


def _knowledge_trace(run_id: str) -> KnowledgeTrace:
    env = KnowledgeEnvironment(
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        loom_version="1.13.3",
        mappings_namespace="yarn",
        mappings_version="1.21.11+build.6",
        java_version="21",
    )
    need = KnowledgeNeed(
        id="need-1",
        type=KnowledgeType.SYMBOL,
        query="Registries.BLOCK lookup",
        environment=env,
    )
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
        environment=env,
        authority=SourceAuthority.AUTHORITATIVE_SOURCE,
        provenance=provenance,
        metadata={"match_score": 10},
    )
    retrieval = KnowledgeRetrievalResult(
        status=KnowledgeRetrievalStatus.SUCCESS,
        need=need,
        items=(item,),
        source_results=(),
        cache_hit=False,
        offline=False,
    )
    return KnowledgeTrace(
        run_id=run_id,
        environment=env,
        needs=(need,),
        source_attempts=(
            KnowledgeSourceAttempt(
                source_id="yarn",
                source_kind="artifact",
                status=KnowledgeRetrievalStatus.SUCCESS,
                retrieved_item_ids=(item.id,),
                locator=provenance.locator,
                revision=provenance.revision,
                checksum=provenance.checksum,
            ),
        ),
        retrieved_item_ids=(item.id,),
        rejected_items=(),
        selected_item_ids=(item.id,),
        context_item_ids=(item.id,),
        misses=(),
        started_at=_utc("2026-08-11T10:00:00"),
        finished_at=_utc("2026-08-11T10:00:01"),
    )


def _minecraft_result(run_id: str) -> MinecraftTestResult:
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/mod.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="harness-pass",
        timeout_seconds=60,
    )
    target = MinecraftTargetMetadata(
        path=Path("build/libs/mod.jar"),
        size_bytes=10,
        sha256="deadbeef",
        mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        java_version="21",
    )
    evidence = MinecraftEvidencePaths(root=Path("evidence/minecraft/run-1"))
    return MinecraftTestResult(
        run_id=run_id,
        status=MinecraftTestStatus.PASS,
        reason="ok",
        spec=spec,
        target=target,
        evidence_paths=evidence,
        started_at=_utc("2026-08-11T10:00:02"),
        finished_at=_utc("2026-08-11T10:00:03"),
        duration_seconds=1.0,
    )


def test_collects_normalized_evidence_from_storage(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "11111111-1111-4111-8111-111111111111"
    run_state = RunState(
        run_id=run_id,
        task="repair the mod",
        project_root=tmp_path / "project",
        state=RunStatus.COMPLETED,
        started_at=_utc("2026-08-11T10:00:00"),
        current_plan="plan",
        changed_files=("src/main/java/dev/p/A.java",),
        tool_call_count=2,
        agent_step_count=3,
        build_attempt_count=1,
        build_results=(
            BuildResult(
                attempt=1,
                command_display="gradlew build",
                cwd=tmp_path / "project",
                started_at=_utc("2026-08-11T10:00:10"),
                duration_seconds=8.0,
                exit_code=0,
                stdout_log="BUILD SUCCESSFUL",
                stderr_log="",
            ),
        ),
        artifact_result=ArtifactResult(
            path=tmp_path / "project" / "build" / "libs" / "mod.jar",
            size=123,
            timestamp=_utc("2026-08-11T10:00:11"),
            classification="VALID",
            metadata={"valid": True},
        ),
        termination_reason="completed",
    )
    storage.write_run_state(run_state)

    report = FinalReport(
        run_id=run_id,
        final_state=RunStatus.COMPLETED,
        summary="summary",
        project=str(tmp_path / "project"),
        requested_task="repair the mod",
        files_changed=("src/main/java/dev/p/A.java",),
        build_attempts=run_state.build_results,
        final_build=run_state.build_results[-1],
        artifact=run_state.artifact_result,
        limits_usage={"tool_calls": 2},
        termination_reason="completed",
        evidence_refs=(),
        generated_at=_utc("2026-08-11T10:00:12"),
    )
    trace = _knowledge_trace(run_id)
    trace_path = storage.store_large_payload(run_id, "knowledge-trace", trace.to_dict(), sequence=1)
    report = FinalReport(
        run_id=run_id,
        final_state=RunStatus.COMPLETED,
        summary="summary",
        project=str(tmp_path / "project"),
        requested_task="repair the mod",
        files_changed=("src/main/java/dev/p/A.java",),
        build_attempts=run_state.build_results,
        final_build=run_state.build_results[-1],
        artifact=run_state.artifact_result,
        limits_usage={"tool_calls": 2},
        termination_reason="completed",
        evidence_refs=(trace_path.relative_to(storage.paths_for(run_id).root).as_posix(),),
        generated_at=_utc("2026-08-11T10:00:12"),
    )
    storage.write_final_report(report)
    writer = storage.event_writer(run_id)
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.MODEL_CALLED, payload={"model_config": {"max_output_tokens": 512}}))
    writer.append(
        RunEvent(
            run_id=run_id,
            event_type=RunEventType.MODEL_RESPONDED,
            payload={
                "assistant_message": "plan",
                "tool_call_count": 1,
                "provider_metadata": {"provider": "gemini", "model": "gemini-3.1-flash-lite"},
                "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
            },
        )
    )
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-1", "tool_name": "write_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_EXECUTED, payload={"call": {"call_id": "call-1", "tool_name": "write_file"}, "result": {"status": "success"}}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-2", "tool_name": "read_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REJECTED, payload={"call": {"call_id": "call-2", "tool_name": "read_file"}, "reason": "blocked"}))

    collector = BenchmarkCollector()
    collection = collector.collect(
        storage=storage,
        run_id=run_id,
        project_snapshot=ProjectSnapshot(
            project_root=tmp_path / "project",
            detected_versions={"minecraft": DetectedValue("1.21.11", "fabric.mod.json")},
        ),
        config=_config(),
        task=_task(),
        minecraft_result=_minecraft_result(run_id),
    )

    assert collection.run_id == run_id
    assert collection.provider == "gemini"
    assert collection.model == "gemini-3.1-flash-lite"
    assert collection.tool_call_count == 2
    assert collection.tool_names == ("write_file", "read_file")
    assert collection.usage == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
    assert collection.provider_metadata == {"provider": "gemini", "model": "gemini-3.1-flash-lite"}
    assert collection.retrieved_item_ids == ("yarn:item:1",)
    assert collection.selected_item_ids == ("yarn:item:1",)
    assert collection.injected_item_ids == ("yarn:item:1",)
    assert collection.provenance_refs == ("yarn|artifact|https://maven.fabricmc.net|build.6|abc123",)
    assert collection.metrics.input_tokens == 11
    assert collection.metrics.output_tokens == 7
    assert collection.metrics.total_tokens == 18
    assert collection.metrics.build_count == 1
    assert collection.minecraft_result is not None and collection.minecraft_result.passed
    assert collection.environment_identity is not None
    assert collection.environment_identity["detected_versions"]["minecraft"] == "1.21.11"
    assert collection.inconsistencies == ()


def test_collects_structured_provider_error_from_run_state(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "44444444-4444-4444-8444-444444444444"
    run_state = RunState(
        run_id=run_id,
        task="repair",
        project_root=tmp_path / "project",
        state=RunStatus.FAILED,
        started_at=_utc("2026-08-11T13:00:00"),
        provider_error_kind="rate_limit",
        provider_error_message="provider rate limit",
        termination_reason="provider error",
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.FAILED,
            summary="summary",
            termination_reason="provider error",
            generated_at=_utc("2026-08-11T13:00:01"),
        )
    )

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id)

    assert collection.provider_metadata is not None
    assert collection.provider_metadata["provider_error"] == {
        "kind": "rate_limit",
        "message": "provider rate limit",
    }


def test_collects_none_semantics_and_brain_off_zeroes(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "22222222-2222-4222-8222-222222222222"
    run_state = RunState(
        run_id=run_id,
        task="inspect",
        project_root=tmp_path / "project",
        state=RunStatus.FAILED,
        started_at=_utc("2026-08-11T11:00:00"),
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.FAILED,
            summary="summary",
            termination_reason="no-op",
            generated_at=_utc("2026-08-11T11:00:01"),
        )
    )

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id, config=BenchmarkConfig(
        config_id="cfg-off",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=False,
        model_config={},
        provider_config={},
        knowledge_config={},
        execution_limits=None,
        target_repetition_count=1,
    ))

    assert collection.provider == "gemini"
    assert collection.usage is None
    assert collection.provider_metadata is None
    assert collection.retrieved_count == 0
    assert collection.selected_count == 0
    assert collection.injected_count == 0
    assert collection.inconsistencies == ()


def test_collects_contradictions_as_inconsistencies(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "33333333-3333-4333-8333-333333333333"
    run_state = RunState(
        run_id=run_id,
        task="repair",
        project_root=tmp_path / "project",
        state=RunStatus.COMPLETED,
        started_at=_utc("2026-08-11T12:00:00"),
        build_attempt_count=1,
        build_results=(
            BuildResult(
                attempt=1,
                command_display="gradlew build",
                cwd=tmp_path / "project",
                started_at=_utc("2026-08-11T12:00:10"),
                duration_seconds=2.0,
                exit_code=0,
                stdout_log="ok",
                stderr_log="",
            ),
        ),
        artifact_result=ArtifactResult(
            path=tmp_path / "project" / "build" / "libs" / "mod.jar",
            size=10,
            timestamp=_utc("2026-08-11T12:00:11"),
            classification="VALID",
            metadata={},
        ),
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.COMPLETED,
            summary="summary",
            build_attempts=run_state.build_results,
            final_build=BuildResult(
                attempt=1,
                command_display="gradlew build",
                cwd=tmp_path / "project",
                started_at=_utc("2026-08-11T12:00:10"),
                duration_seconds=2.0,
                exit_code=1,
                stdout_log="ok",
                stderr_log="boom",
            ),
            artifact=run_state.artifact_result,
            generated_at=_utc("2026-08-11T12:00:12"),
        )
    )

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id)

    assert "final_build_contradiction" in collection.inconsistencies
    assert collection.final_build is not None


def test_tool_call_count_uses_logical_call_ids_for_success(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "44444444-4444-4444-8444-444444444444"
    run_state = RunState(
        run_id=run_id,
        task="repair",
        project_root=tmp_path / "project",
        state=RunStatus.COMPLETED,
        started_at=_utc("2026-08-11T13:00:00"),
        build_attempt_count=1,
        tool_call_count=1,
        build_results=(),
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.COMPLETED,
            summary="summary",
            termination_reason="completed",
            generated_at=_utc("2026-08-11T13:00:01"),
        )
    )
    writer = storage.event_writer(run_id)
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-1", "tool_name": "write_file", "arguments": {"path": "a"}}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_EXECUTED, payload={"call": {"call_id": "call-1", "tool_name": "write_file"}, "result": {"status": "success"}}))

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id)

    assert collection.tool_call_count == 1
    assert collection.tool_names == ("write_file",)
    assert collection.inconsistencies == ()


def test_tool_call_count_uses_logical_call_ids_for_rejected_call(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "55555555-5555-4555-8555-555555555555"
    run_state = RunState(
        run_id=run_id,
        task="repair",
        project_root=tmp_path / "project",
        state=RunStatus.FAILED,
        started_at=_utc("2026-08-11T14:00:00"),
        tool_call_count=1,
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.FAILED,
            summary="summary",
            termination_reason="tool rejected",
            generated_at=_utc("2026-08-11T14:00:01"),
        )
    )
    writer = storage.event_writer(run_id)
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "a"}}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REJECTED, payload={"call": {"call_id": "call-1", "tool_name": "read_file"}, "reason": "blocked"}))

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id)

    assert collection.tool_call_count == 1
    assert collection.tool_names == ("read_file",)
    assert collection.inconsistencies == ()


def test_tool_call_count_handles_two_logical_calls(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "66666666-6666-4666-8666-666666666666"
    run_state = RunState(
        run_id=run_id,
        task="repair",
        project_root=tmp_path / "project",
        state=RunStatus.COMPLETED,
        started_at=_utc("2026-08-11T15:00:00"),
        tool_call_count=2,
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.COMPLETED,
            summary="summary",
            termination_reason="completed",
            generated_at=_utc("2026-08-11T15:00:01"),
        )
    )
    writer = storage.event_writer(run_id)
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-1", "tool_name": "write_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_EXECUTED, payload={"call": {"call_id": "call-1", "tool_name": "write_file"}}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-2", "tool_name": "read_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_EXECUTED, payload={"call": {"call_id": "call-2", "tool_name": "read_file"}}))

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id)

    assert collection.tool_call_count == 2
    assert collection.tool_names == ("write_file", "read_file")
    assert collection.inconsistencies == ()


def test_tool_call_mismatch_detects_unique_ids_only(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "77777777-7777-4777-8777-777777777777"
    run_state = RunState(
        run_id=run_id,
        task="repair",
        project_root=tmp_path / "project",
        state=RunStatus.COMPLETED,
        started_at=_utc("2026-08-11T16:00:00"),
        tool_call_count=1,
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.COMPLETED,
            summary="summary",
            termination_reason="completed",
            generated_at=_utc("2026-08-11T16:00:01"),
        )
    )
    writer = storage.event_writer(run_id)
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-1", "tool_name": "write_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_EXECUTED, payload={"call": {"call_id": "call-1", "tool_name": "write_file"}}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-2", "tool_name": "read_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_EXECUTED, payload={"call": {"call_id": "call-2", "tool_name": "read_file"}}))

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id)

    assert "tool_call_mismatch" in collection.inconsistencies
    assert collection.tool_names == ("write_file", "read_file")


def test_tool_names_do_not_duplicate_for_lifecycle_events(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "88888888-8888-4888-8888-888888888888"
    run_state = RunState(
        run_id=run_id,
        task="repair",
        project_root=tmp_path / "project",
        state=RunStatus.COMPLETED,
        started_at=_utc("2026-08-11T17:00:00"),
        tool_call_count=1,
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.COMPLETED,
            summary="summary",
            termination_reason="completed",
            generated_at=_utc("2026-08-11T17:00:01"),
        )
    )
    writer = storage.event_writer(run_id)
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-1", "tool_name": "write_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_EXECUTED, payload={"call": {"call_id": "call-1", "tool_name": "write_file"}}))

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id)

    assert collection.tool_names == ("write_file",)


def test_mixed_tool_outcomes_still_count_logical_calls(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    run_id = "99999999-9999-4999-8999-999999999999"
    run_state = RunState(
        run_id=run_id,
        task="repair",
        project_root=tmp_path / "project",
        state=RunStatus.FAILED,
        started_at=_utc("2026-08-11T18:00:00"),
        tool_call_count=2,
    )
    storage.write_run_state(run_state)
    storage.write_final_report(
        FinalReport(
            run_id=run_id,
            final_state=RunStatus.FAILED,
            summary="summary",
            termination_reason="tool rejected",
            generated_at=_utc("2026-08-11T18:00:01"),
        )
    )
    writer = storage.event_writer(run_id)
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-1", "tool_name": "write_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_EXECUTED, payload={"call": {"call_id": "call-1", "tool_name": "write_file"}}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REQUESTED, payload={"call_id": "call-2", "tool_name": "delete_file"}))
    writer.append(RunEvent(run_id=run_id, event_type=RunEventType.TOOL_REJECTED, payload={"call": {"call_id": "call-2", "tool_name": "delete_file"}, "reason": "blocked"}))

    collection = BenchmarkCollector().collect(storage=storage, run_id=run_id)

    assert collection.tool_call_count == 2
    assert collection.tool_names == ("write_file", "delete_file")
    assert collection.inconsistencies == ()
