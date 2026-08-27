"""Final report model and serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from ..core import ArtifactResult, BuildResult, RunStatus, ValidationResult, ValidationStage
from .redaction import Redactor, json_ready

MINECRAFT_RUNTIME_VALIDATION_NOTE = "NOT PERFORMED (v0.1)"


def runtime_validation_summary(validation_results: tuple[ValidationResult, ...]) -> str:
    """Use the latest persisted runtime validation as the report authority."""
    runtime_results = tuple(
        result for result in validation_results if result.stage is ValidationStage.RUNTIME
    )
    if not runtime_results:
        return MINECRAFT_RUNTIME_VALIDATION_NOTE
    return runtime_results[-1].status.value


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
    validation_results: tuple[ValidationResult, ...] = ()
    limits_usage: Mapping[str, int] | None = None
    warnings: tuple[str, ...] = ()
    termination_reason: str | None = None
    evidence_refs: tuple[str, ...] = ()
    minecraft_runtime_validation: str = MINECRAFT_RUNTIME_VALIDATION_NOTE
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    contract_identity: tuple[str, str, str] | None = None
    completion_status: str | None = None
    pending_requirement_ids: tuple[str, ...] = ()
    active_failure_ids: tuple[str, ...] = ()
    benchmark_outcome: str | None = None

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
            "validation_results": [item.to_dict() for item in self.validation_results],
            "limits_usage": dict(self.limits_usage) if self.limits_usage is not None else None,
            "warnings": list(self.warnings),
            "termination_reason": self.termination_reason,
            "evidence_refs": list(self.evidence_refs),
            "minecraft_runtime_validation": self.minecraft_runtime_validation,
            "generated_at": self.generated_at.isoformat(),
            "contract_identity": list(self.contract_identity) if self.contract_identity is not None else None,
            "completion_status": self.completion_status,
            "pending_requirement_ids": list(self.pending_requirement_ids),
            "active_failure_ids": list(self.active_failure_ids),
            "benchmark_outcome": self.benchmark_outcome,
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
            f"- Completion Status: `{data.get('completion_status') or data['final_state']}`",
            f"- Contract Identity: `{data.get('contract_identity')}`",
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
        lines.extend(
            [
                "",
                "## Minecraft Runtime Validation",
                f"- {data.get('minecraft_runtime_validation', MINECRAFT_RUNTIME_VALIDATION_NOTE)}",
            ]
        )
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
            validation_results=tuple(
                ValidationResult.from_dict(item) for item in data.get("validation_results", [])
            ),
            limits_usage=(
                dict(data["limits_usage"])
                if data.get("limits_usage") is not None
                else None
            ),
            warnings=tuple(data.get("warnings", [])),
            termination_reason=data.get("termination_reason"),
            evidence_refs=tuple(data.get("evidence_refs", [])),
            minecraft_runtime_validation=str(
                data.get("minecraft_runtime_validation", MINECRAFT_RUNTIME_VALIDATION_NOTE)
            ),
            generated_at=datetime.fromisoformat(
                str(data.get("generated_at", datetime.now(timezone.utc).isoformat()))
            ),
            contract_identity=(
                tuple(str(item) for item in data["contract_identity"])
                if data.get("contract_identity") is not None
                else None
            ),
            completion_status=data.get("completion_status"),
            pending_requirement_ids=tuple(str(item) for item in data.get("pending_requirement_ids", [])),
            active_failure_ids=tuple(str(item) for item in data.get("active_failure_ids", [])),
            benchmark_outcome=data.get("benchmark_outcome"),
        )
