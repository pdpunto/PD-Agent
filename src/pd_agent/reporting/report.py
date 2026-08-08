"""Final report model and serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from ..core import ArtifactResult, BuildResult, RunStatus
from .redaction import Redactor, json_ready


@dataclass(frozen=True, slots=True)
class FinalReport:
    """Provider-neutral final report."""

    run_id: str
    final_state: RunStatus
    summary: str
    project: str | None = None
    requested_task: str | None = None
    files_changed: tuple[str, ...] = ()
    build_attempts: tuple[BuildResult, ...] = ()
    final_build: BuildResult | None = None
    artifact: ArtifactResult | None = None
    limits_usage: Mapping[str, int] | None = None
    warnings: tuple[str, ...] = ()
    termination_reason: str | None = None
    evidence_refs: tuple[str, ...] = ()
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self, redactor: Redactor | None = None) -> dict[str, Any]:
        data = {
            "run_id": self.run_id,
            "final_state": self.final_state.value,
            "summary": self.summary,
            "project": self.project,
            "requested_task": self.requested_task,
            "files_changed": list(self.files_changed),
            "build_attempts": [item.to_dict() for item in self.build_attempts],
            "final_build": self.final_build.to_dict() if self.final_build else None,
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "limits_usage": dict(self.limits_usage) if self.limits_usage is not None else None,
            "warnings": list(self.warnings),
            "termination_reason": self.termination_reason,
            "evidence_refs": list(self.evidence_refs),
            "generated_at": self.generated_at.isoformat(),
        }
        data = json_ready(data)
        if redactor is not None:
            data = redactor.redact_data(data)
        return data

    def to_json(self, redactor: Redactor | None = None) -> str:
        return json.dumps(self.to_dict(redactor), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, redactor: Redactor | None = None) -> str:
        data = self.to_dict(redactor)
        lines = [
            "# Final Report",
            "",
            f"- Run ID: `{data['run_id']}`",
            f"- Final State: `{data['final_state']}`",
            f"- Summary: {data['summary']}",
            f"- Project: {data['project']}",
            f"- Requested Task: {data['requested_task']}",
            f"- Generated At: `{data['generated_at']}`",
            "",
            "## Files Changed",
        ]
        files_changed = data.get("files_changed", [])
        if files_changed:
            lines.extend(f"- `{item}`" for item in files_changed)
        else:
            lines.append("- None")
        lines.extend(["", "## Build Attempts"])
        build_attempts = data.get("build_attempts", [])
        if build_attempts:
            for build in build_attempts:
                lines.append(
                    f"- Attempt {build['attempt']}: exit_code={build['exit_code']} success={build['success']}"
                )
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Artifact",
                f"- {data['artifact']}" if data["artifact"] is not None else "- None",
                "",
                "## Warnings",
            ]
        )
        warnings = data.get("warnings", [])
        if warnings:
            lines.extend(f"- {item}" for item in warnings)
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Evidence",
            ]
        )
        evidence_refs = data.get("evidence_refs", [])
        if evidence_refs:
            lines.extend(f"- `{item}`" for item in evidence_refs)
        else:
            lines.append("- None")
        if data.get("termination_reason"):
            lines.extend(["", f"Termination reason: {data['termination_reason']}"])
        return "\n".join(lines) + "\n"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FinalReport":
        return cls(
            run_id=str(data["run_id"]),
            final_state=RunStatus(str(data["final_state"])),
            summary=str(data["summary"]),
            project=data.get("project"),
            requested_task=data.get("requested_task"),
            files_changed=tuple(data.get("files_changed", [])),
            build_attempts=tuple(
                BuildResult.from_dict(item) for item in data.get("build_attempts", [])
            ),
            final_build=(
                BuildResult.from_dict(data["final_build"])
                if data.get("final_build") is not None
                else None
            ),
            artifact=(
                ArtifactResult.from_dict(data["artifact"])
                if data.get("artifact") is not None
                else None
            ),
            limits_usage=(
                dict(data["limits_usage"])
                if data.get("limits_usage") is not None
                else None
            ),
            warnings=tuple(data.get("warnings", [])),
            termination_reason=data.get("termination_reason"),
            evidence_refs=tuple(data.get("evidence_refs", [])),
            generated_at=datetime.fromisoformat(
                str(data.get("generated_at", datetime.now(timezone.utc).isoformat()))
            ),
        )
