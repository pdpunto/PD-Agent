from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from pd_agent.core import ArtifactResult, BuildResult, RunState, RunStatus, generate_run_id
from pd_agent.reporting import (
    FinalReport,
    RunEvent,
    RunEventType,
    RunStorage,
)


def _utc(moment: str) -> datetime:
    return datetime.fromisoformat(moment).replace(tzinfo=timezone.utc)


def test_jsonl_valid_append_only_and_order() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = RunStorage(Path(temp_dir))
        run_id = generate_run_id()
        writer = storage.event_writer(run_id)

        first = writer.append(
            RunEvent(
                run_id=run_id,
                event_type=RunEventType.RUN_STARTED,
                timestamp=_utc("2026-08-08T12:00:00"),
                payload={"kind": "start"},
            )
        )
        second = writer.append(
            RunEvent(
                run_id=run_id,
                event_type=RunEventType.STATE_CHANGED,
                timestamp=_utc("2026-08-08T12:00:01"),
                payload={"state": "INSPECTING"},
            )
        )

        lines = (storage.paths_for(run_id).events_jsonl).read_text(encoding="utf-8").splitlines()

        assert len(lines) == 2
        assert json.loads(lines[0])["event_type"] == RunEventType.RUN_STARTED.value
        assert json.loads(lines[1])["event_type"] == RunEventType.STATE_CHANGED.value
        assert first.sequence == 1
        assert second.sequence == 2


def test_events_can_be_reloaded_with_timestamps() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = RunStorage(Path(temp_dir))
        run_id = generate_run_id()
        writer = storage.event_writer(run_id)
        original = RunEvent(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISHED,
            timestamp=_utc("2026-08-08T12:30:00"),
            payload={"ok": True},
        )
        writer.append(original)

        events = storage.read_events(run_id)

        assert len(events) == 1
        assert events[0].timestamp == original.timestamp
        assert events[0].event_type == original.event_type


def test_run_state_round_trip_via_run_json() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = RunStorage(Path(temp_dir))
        run_state = RunState(
            task="audit docs",
            project_root=Path("C:/dev/example"),
            current_plan="inspect, report",
            changed_files=("README.md",),
            tool_call_count=1,
            agent_step_count=2,
            build_attempt_count=0,
            build_results=(
                BuildResult(
                    attempt=1,
                    command_display="gradlew build",
                    cwd=Path("C:/dev/example"),
                    started_at=_utc("2026-08-08T12:00:00"),
                    duration_seconds=3.2,
                    exit_code=0,
                    stdout_log="ok",
                    stderr_log="",
                ),
            ),
            artifact_result=ArtifactResult(
                path=Path("C:/dev/example/build/libs/mod.jar"),
                size=123,
                timestamp=_utc("2026-08-08T12:05:00"),
                classification="fabric-mod",
                metadata={"kind": "jar"},
            ),
        )

        storage.write_run_state(run_state)
        reloaded = storage.read_run_state(run_state.run_id)

        assert reloaded.to_dict() == run_state.to_dict()
        assert storage.paths_for(run_state.run_id).run_json.exists()


def test_secret_is_redacted_from_events_and_reports() -> None:
    secret = "super-secret-token"
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = RunStorage(Path(temp_dir), secrets=(secret,))
        run_id = generate_run_id()
        writer = storage.event_writer(run_id)

        writer.append(
            RunEvent(
                run_id=run_id,
                event_type=RunEventType.MODEL_CALLED,
                timestamp=_utc("2026-08-08T12:10:00"),
                payload={"api_key": secret, "note": f"value={secret}"},
            )
        )
        storage.write_run_state(
            RunState(run_id=run_id, task=f"task uses {secret}", project_root=Path("C:/x"))
        )
        storage.write_final_report(
            FinalReport(
                run_id=run_id,
                final_state=RunStatus.FAILED,
                summary=f"summary {secret}",
                project=f"project {secret}",
                requested_task=f"task {secret}",
                warnings=(f"warn {secret}",),
                termination_reason=f"reason {secret}",
            )
        )

        run_dir = storage.paths_for(run_id)
        event_text = run_dir.events_jsonl.read_text(encoding="utf-8")
        run_json_text = run_dir.run_json.read_text(encoding="utf-8")
        report_json_text = run_dir.final_report_json.read_text(encoding="utf-8")
        report_md_text = run_dir.final_report_md.read_text(encoding="utf-8")

        assert secret not in event_text
        assert secret not in run_json_text
        assert secret not in report_json_text
        assert secret not in report_md_text
        assert "[REDACTED]" in event_text
        assert "[REDACTED]" in report_json_text


def test_large_outputs_are_referenced() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = RunStorage(Path(temp_dir), large_payload_threshold=64)
        run_id = generate_run_id()
        writer = storage.event_writer(run_id)
        payload = {"blob": "x" * 200}

        event = writer.append(
            RunEvent(
                run_id=run_id,
                event_type=RunEventType.MODEL_RESPONDED,
                timestamp=_utc("2026-08-08T12:15:00"),
                payload=payload,
            )
        )

        assert event.payload_ref is not None
        assert event.payload == {}
        assert event.payload_ref.relative_path.startswith("evidence/")
        evidence_path = storage.paths_for(run_id).root / event.payload_ref.relative_path
        assert evidence_path.exists()
        assert "x" * 50 in evidence_path.read_text(encoding="utf-8")


def test_final_report_json_and_markdown_and_partial_failure() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = RunStorage(Path(temp_dir))
        run_id = generate_run_id()
        build = BuildResult(
            attempt=1,
            command_display="gradlew build",
            cwd=Path("C:/dev/example"),
            started_at=_utc("2026-08-08T12:20:00"),
            duration_seconds=4.0,
            exit_code=1,
            stdout_log="fail",
            stderr_log="boom",
        )
        report = FinalReport(
            run_id=run_id,
            final_state=RunStatus.FAILED,
            summary="partial report",
            project="example",
            requested_task="do thing",
            files_changed=("src/Main.java",),
            build_attempts=(build,),
            final_build=build,
            artifact=None,
            limits_usage={"max_build_attempts": 1},
            warnings=("warning",),
            termination_reason="build failed",
            evidence_refs=("evidence/payload-0001.json",),
        )

        json_path, md_path = storage.write_final_report(report)
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        reloaded = storage.read_final_report(run_id)

        assert loaded["run_id"] == run_id
        assert loaded["final_state"] == RunStatus.FAILED.value
        assert md_path.read_text(encoding="utf-8").startswith("# Final Report")
        assert "partial report" in md_path.read_text(encoding="utf-8")
        assert reloaded.to_dict() == report.to_dict()


def test_run_directories_are_isolated_per_run_id() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = RunStorage(Path(temp_dir))
        run_a = generate_run_id()
        run_b = generate_run_id()

        storage.write_run_state(RunState(run_id=run_a, task="a"))
        storage.write_run_state(RunState(run_id=run_b, task="b"))

        paths_a = storage.paths_for(run_a)
        paths_b = storage.paths_for(run_b)

        assert paths_a.run_dir != paths_b.run_dir
        assert paths_a.run_dir.exists()
        assert paths_b.run_dir.exists()
        assert paths_a.run_json.exists()
        assert paths_b.run_json.exists()
