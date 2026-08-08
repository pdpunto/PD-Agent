"""Authoritative v0.1 PASS policy."""

from __future__ import annotations

from dataclasses import dataclass

from pd_agent.core import ArtifactResult, BuildResult, RunState, RunStatus
from pd_agent.reporting import FinalReport, RunPaths, RunStorage


@dataclass(frozen=True, slots=True)
class PassEvaluation:
    """Result of validating an operational v0.1 PASS."""

    passed: bool
    reason: str
    run_id: str
    run_state: RunState | None = None
    final_report: FinalReport | None = None
    paths: RunPaths | None = None

    @property
    def final_build(self) -> BuildResult | None:
        return self.final_report.final_build if self.final_report is not None else None

    @property
    def artifact(self) -> ArtifactResult | None:
        return self.final_report.artifact if self.final_report is not None else None


def evaluate_pass(storage: RunStorage, run_id: str) -> PassEvaluation:
    """Validate PASS against persisted evidence only."""

    paths = storage.paths_for(run_id)
    missing = _missing_files(paths)
    if missing:
        return _failure(run_id, paths, f"missing persisted file(s): {', '.join(missing)}")

    try:
        run_state = storage.read_run_state(run_id)
    except Exception as exc:
        return _failure(run_id, paths, f"run state unreadable: {exc}")

    try:
        report = storage.read_final_report(run_id)
    except Exception as exc:
        return _failure(run_id, paths, f"final report unreadable: {exc}")

    if run_state.run_id != run_id or report.run_id != run_id:
        return _failure(run_id, paths, "run_id mismatch in persisted evidence")

    if run_state.state != RunStatus.COMPLETED:
        return _failure(run_id, paths, f"final state is {run_state.state.value}")

    if report.final_state != RunStatus.COMPLETED:
        return _failure(run_id, paths, f"report final state is {report.final_state.value}")

    if not run_state.build_results:
        return _failure(run_id, paths, "missing final build in run state")

    if report.final_build is None:
        return _failure(run_id, paths, "missing final build in report")

    if not report.final_build.success:
        return _failure(run_id, paths, "final build did not succeed")

    if report.final_build.to_dict() != run_state.build_results[-1].to_dict():
        return _failure(run_id, paths, "final build does not match persisted run state")

    if run_state.artifact_result is None:
        return _failure(run_id, paths, "missing artifact result in run state")

    if report.artifact is None:
        return _failure(run_id, paths, "missing artifact in report")

    if report.artifact.classification != "VALID":
        return _failure(run_id, paths, f"artifact classification is {report.artifact.classification}")

    if report.artifact.to_dict() != run_state.artifact_result.to_dict():
        return _failure(run_id, paths, "artifact does not match persisted run state")

    return PassEvaluation(
        passed=True,
        reason="pass criteria satisfied",
        run_id=run_id,
        run_state=run_state,
        final_report=report,
        paths=paths,
    )


def _missing_files(paths: RunPaths) -> tuple[str, ...]:
    names = [
        ("run.json", paths.run_json),
        ("events.jsonl", paths.events_jsonl),
        ("final-report.json", paths.final_report_json),
        ("final-report.md", paths.final_report_md),
    ]
    return tuple(name for name, path in names if not path.exists())


def _failure(run_id: str, paths: RunPaths, reason: str) -> PassEvaluation:
    return PassEvaluation(passed=False, reason=reason, run_id=run_id, paths=paths)
