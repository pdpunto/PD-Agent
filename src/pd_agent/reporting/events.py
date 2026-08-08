"""Run event types and JSONL writer."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping

from .redaction import REDACTION_TOKEN, Redactor, json_ready


DEFAULT_LARGE_PAYLOAD_THRESHOLD = 8_192


class RunEventType(StrEnum):
    """Lifecycle and future event catalog."""

    RUN_STARTED = "RUN_STARTED"
    PROJECT_INSPECTED = "PROJECT_INSPECTED"
    STATE_CHANGED = "STATE_CHANGED"
    MODEL_CALLED = "MODEL_CALLED"
    MODEL_RESPONDED = "MODEL_RESPONDED"
    RUN_FINISHED = "RUN_FINISHED"
    TOOL_REQUESTED = "TOOL_REQUESTED"
    TOOL_REJECTED = "TOOL_REJECTED"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    FILE_CHANGED = "FILE_CHANGED"
    BUILD_STARTED = "BUILD_STARTED"
    BUILD_FINISHED = "BUILD_FINISHED"
    ARTIFACT_VALIDATED = "ARTIFACT_VALIDATED"
    LIMIT_REACHED = "LIMIT_REACHED"


@dataclass(frozen=True, slots=True)
class LargePayloadReference:
    """Reference to payload stored outside JSONL."""

    relative_path: str
    size: int
    content_type: str = "application/json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "size": self.size,
            "content_type": self.content_type,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LargePayloadReference":
        return cls(
            relative_path=str(data["relative_path"]),
            size=int(data["size"]),
            content_type=str(data.get("content_type", "application/json")),
        )


@dataclass(frozen=True, slots=True)
class RunEvent:
    """A single trace event."""

    run_id: str
    event_type: RunEventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Mapping[str, Any] = field(default_factory=dict)
    sequence: int | None = None
    payload_ref: LargePayloadReference | None = None

    def to_dict(self, redactor: Redactor | None = None) -> dict[str, Any]:
        payload = json_ready(self.payload)
        if redactor is not None:
            payload = redactor.redact_data(payload)
        return {
            "run_id": self.run_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
            "payload": payload,
            "payload_ref": (
                self.payload_ref.to_dict() if self.payload_ref is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunEvent":
        return cls(
            run_id=str(data["run_id"]),
            event_type=RunEventType(str(data["event_type"])),
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            payload=dict(data.get("payload") or {}),
            sequence=(int(data["sequence"]) if data.get("sequence") is not None else None),
            payload_ref=(
                LargePayloadReference.from_dict(data["payload_ref"])
                if data.get("payload_ref") is not None
                else None
            ),
        )


class JsonlEventWriter:
    """Append-only JSONL writer for run events."""

    def __init__(
        self,
        jsonl_path: Path,
        evidence_dir: Path,
        redactor: Redactor | None = None,
        large_payload_threshold: int = DEFAULT_LARGE_PAYLOAD_THRESHOLD,
    ) -> None:
        self.jsonl_path = jsonl_path
        self.evidence_dir = evidence_dir
        self.redactor = redactor or Redactor()
        self.large_payload_threshold = large_payload_threshold
        self._sequence = self._next_sequence()

    def append(self, event: RunEvent) -> RunEvent:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)

        sequence = self._sequence
        self._sequence += 1
        prepared = self._prepare_event(event, sequence)
        line = json.dumps(prepared.to_dict(self.redactor), ensure_ascii=False, sort_keys=True)
        with self.jsonl_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
        return prepared

    def _prepare_event(self, event: RunEvent, sequence: int) -> RunEvent:
        payload = self.redactor.redact_data(event.payload)
        serialized = json.dumps(json_ready(payload), ensure_ascii=False, sort_keys=True)
        if len(serialized.encode("utf-8")) <= self.large_payload_threshold:
            return replace(event, sequence=sequence, payload=payload, payload_ref=None)

        evidence_name = self._evidence_name(sequence, event.event_type)
        evidence_path = self.evidence_dir / evidence_name
        evidence_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        payload_ref = LargePayloadReference(
            relative_path=f"evidence/{evidence_name}",
            size=evidence_path.stat().st_size,
        )
        return replace(event, sequence=sequence, payload={}, payload_ref=payload_ref)

    def _evidence_name(self, sequence: int, event_type: RunEventType) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"{sequence:04d}-{timestamp}-{event_type.value.lower()}.json"

    def _next_sequence(self) -> int:
        if not self.jsonl_path.exists():
            return 1
        with self.jsonl_path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle if _.strip()) + 1
