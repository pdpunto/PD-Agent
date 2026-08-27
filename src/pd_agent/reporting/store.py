"""Run directory storage for reporting artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Iterable

from ..core import RunState
from .events import JsonlEventWriter, RunEvent
from .redaction import Redactor
from .report import FinalReport


@dataclass(frozen=True, slots=True)
class RunPaths:
    """Canonical run file layout."""

    root: Path

    @property
    def run_dir(self) -> Path:
        return self.root

    @property
    def evidence_dir(self) -> Path:
        return self.root / "evidence"

    @property
    def builds_dir(self) -> Path:
        return self.root / "builds"

    @property
    def run_json(self) -> Path:
        return self.root / "run.json"

    @property
    def events_jsonl(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def final_report_json(self) -> Path:
        return self.root / "final-report.json"

    @property
    def final_report_md(self) -> Path:
        return self.root / "final-report.md"


class RunStorage:
    """Storage for one reporting root."""

    def __init__(
        self,
        storage_root: Path,
        secrets: Iterable[str] = (),
        large_payload_threshold: int = 8_192,
    ) -> None:
        self.storage_root = storage_root
        self.redactor = Redactor(tuple(secrets))
        self.large_payload_threshold = large_payload_threshold

    def paths_for(self, run_id: str) -> RunPaths:
        run_root = self.storage_root / run_id
        paths = RunPaths(run_root)
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        paths.evidence_dir.mkdir(parents=True, exist_ok=True)
        paths.builds_dir.mkdir(parents=True, exist_ok=True)
        return paths

    def event_writer(self, run_id: str) -> JsonlEventWriter:
        paths = self.paths_for(run_id)
        return JsonlEventWriter(
            jsonl_path=paths.events_jsonl,
            evidence_dir=paths.evidence_dir,
            redactor=self.redactor,
            large_payload_threshold=self.large_payload_threshold,
        )

    def write_run_state(self, run_state: RunState) -> Path:
        paths = self.paths_for(run_state.run_id)
        payload = self.redactor.redact_data(run_state.to_dict())
        paths.run_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return paths.run_json

    def read_run_state(self, run_id: str) -> RunState:
        paths = self.paths_for(run_id)
        data = json.loads(paths.run_json.read_text(encoding="utf-8"))
        return RunState.from_dict(data)

    def append_event(self, event: RunEvent) -> RunEvent:
        return self.event_writer(event.run_id).append(event)

    def read_events(self, run_id: str) -> tuple[RunEvent, ...]:
        paths = self.paths_for(run_id)
        if not paths.events_jsonl.exists():
            return ()
        events: list[RunEvent] = []
        with paths.events_jsonl.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    event = RunEvent.from_dict(json.loads(line))
                    if event.payload_ref is not None:
                        event = self._resolve_event_payload(paths, event)
                    events.append(event)
        return tuple(events)

    def _resolve_event_payload(self, paths: RunPaths, event: RunEvent) -> RunEvent:
        ref_path = paths.root / event.payload_ref.relative_path
        payload = json.loads(ref_path.read_text(encoding="utf-8"))
        return RunEvent(
            run_id=event.run_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            payload=payload,
            sequence=event.sequence,
            payload_ref=event.payload_ref,
            schema_version=event.schema_version,
        )

    def write_final_report(self, report: FinalReport) -> tuple[Path, Path]:
        paths = self.paths_for(report.run_id)
        json_payload = self.redactor.redact_data(report.to_dict(self.redactor))
        paths.final_report_json.write_text(
            json.dumps(json_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        paths.final_report_md.write_text(
            report.to_markdown(self.redactor),
            encoding="utf-8",
        )
        return paths.final_report_json, paths.final_report_md

    def read_final_report(self, run_id: str) -> FinalReport:
        paths = self.paths_for(run_id)
        data = json.loads(paths.final_report_json.read_text(encoding="utf-8"))
        return FinalReport.from_dict(data)

    def store_large_payload(
        self,
        run_id: str,
        name: str,
        payload: Any,
        sequence: int = 1,
    ) -> Path:
        paths = self.paths_for(run_id)
        evidence_name = f"{sequence:04d}-{name}.json"
        evidence_path = paths.evidence_dir / evidence_name
        evidence_path.write_text(
            json.dumps(self.redactor.redact_data(payload), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return evidence_path
