from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pd_agent.bootstrap import FabricBootstrap
from pd_agent.core import RunStatus
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage


def test_observability_event_catalog_covers_i13_lifecycle() -> None:
    expected = {
        "CONTRACT_CREATED", "PLAN_CREATED", "PLAN_REVISED", "REQUIREMENT_RECONCILED",
        "FAILURE_ACTIVE", "FAILURE_RESOLVED", "STALE_EVIDENCE_DETECTED",
        "BUILD_ATTEMPT_RECORDED", "ARTIFACT_VALIDATED", "RUNTIME_VALIDATION_RECORDED",
        "REPAIR_ATTEMPT_RECORDED", "COMPLETION_GATE_EVALUATED", "BOOTSTRAP_COMPLETED",
    }
    assert expected <= {item.value for item in RunEventType}


def test_event_schema_and_payload_round_trip_are_additive(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path, secrets=("api-secret",))
    event = storage.append_event(RunEvent(
        run_id="run-1",
        event_type=RunEventType.CONTRACT_CREATED,
        payload={"contract_identity": ["task", "1", "fp"], "api_key": "api-secret"},
    ))

    raw = json.loads(storage.paths_for("run-1").events_jsonl.read_text(encoding="utf-8"))
    restored = storage.read_events("run-1")[0]
    assert raw["schema_version"] == 1
    assert event.sequence == 1
    assert restored == event
    assert restored.payload["api_key"] == "[REDACTED]"


def test_event_catalog_preserves_failure_and_stale_history(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path)
    for event_type, payload in (
        (RunEventType.FAILURE_ACTIVE, {"failure_id": "f1", "status": "ACTIVE", "evidence_refs": ["e/fail.json"]}),
        (RunEventType.STALE_EVIDENCE_DETECTED, {"evidence_ref": "e/old.json", "reason": "newer source"}),
        (RunEventType.FAILURE_RESOLVED, {"failure_id": "f1", "status": "RESOLVED", "resolution_evidence_refs": ["e/new.json"]}),
    ):
        storage.append_event(RunEvent(run_id="run-1", event_type=event_type, payload=payload))
    assert [event.event_type for event in storage.read_events("run-1")] == [
        RunEventType.FAILURE_ACTIVE, RunEventType.STALE_EVIDENCE_DETECTED, RunEventType.FAILURE_RESOLVED,
    ]


def test_large_event_uses_reference_not_inline_heavy_data(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path, large_payload_threshold=64)
    event = storage.append_event(RunEvent(
        run_id="run-1", event_type=RunEventType.BUILD_ATTEMPT_RECORDED,
        payload={"build_attempt_id": "b1", "stdout": "x" * 500},
    ))
    assert event.payload == {}
    assert event.payload_ref is not None
    assert storage.read_events("run-1")[0].payload["stdout"] == "x" * 500


def test_final_report_records_completion_separately_from_benchmark(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path)
    report = FinalReport(
        run_id="run-1", final_state=RunStatus.COMPLETED, summary="complete",
        contract_identity=("task", "1", "fingerprint"), completion_status="COMPLETE",
        pending_requirement_ids=(), active_failure_ids=(), benchmark_outcome="FAIL",
    )
    storage.write_final_report(report)
    restored = storage.read_final_report("run-1")
    assert restored.contract_identity == report.contract_identity
    assert restored.completion_status == "COMPLETE"
    assert restored.benchmark_outcome == "FAIL"


def test_bootstrap_emits_bounded_event_without_external_path_or_secret(tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "reports", secrets=("secret",))
    result = FabricBootstrap().create(tmp_path / "project", mod_id="examplemod", package="com.example.examplemod", reporting=storage)
    event = storage.read_events(f"bootstrap-{result.project_fingerprint[:16]}")[0]
    assert event.event_type == RunEventType.BOOTSTRAP_COMPLETED
    assert event.payload["workspace_identity"] == result.project_fingerprint
    assert str(tmp_path) not in json.dumps(event.payload)


def test_timestamp_is_informational_not_currentness_identity() -> None:
    first = RunEvent(run_id="run", event_type=RunEventType.PLAN_CREATED, timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc), payload={})
    second = RunEvent(run_id="run", event_type=RunEventType.PLAN_CREATED, timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc), payload={})
    assert first.to_dict()["timestamp"] != second.to_dict()["timestamp"]
    assert first.to_dict()["event_type"] == second.to_dict()["event_type"]
