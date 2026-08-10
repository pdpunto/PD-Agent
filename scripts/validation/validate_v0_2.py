"""Validacion externa reproducible de PD Agent v0.2 Batch D."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any, Iterator

import validate_v0_1 as base
from pd_agent.minecraft import MinecraftTestRunner, MinecraftTestSpec
from pd_agent.minecraft.errors import MinecraftTestValidationError


REPO_ROOT = base.REPO_ROOT
DEFAULT_VALIDATION_ROOT = Path(base.tempfile.gettempdir()) / "pd-agent-v0.2-validation"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_TARGET_ROOT = REPO_ROOT / "tests" / "fixtures" / "l11_fabric_fixture"
DEFAULT_HARNESS_ROOT = REPO_ROOT / "tests" / "fixtures" / "l11_minecraft_harness"
DEFAULT_TARGET_JAR = Path("tests/fixtures/l11_fabric_fixture/build/libs/pd-agent-l11-fixture.jar")
DEFAULT_TARGET_MOD_ID = "pdagentl11"
DEFAULT_MINECRAFT_VERSION = "1.21.11"
DEFAULT_LOADER_VERSION = "0.19.3"
DEFAULT_TEST_ID = "block_state_probe"
WORKSPACE_COPY_IGNORED_DIRS = tuple(sorted(name for name in base.IGNORED_COPY_DIRS if name != ".gradle"))


@dataclass(slots=True)
class ValidationSummary:
    started_at: datetime
    finished_at: datetime | None = None
    repository_commit: str | None = None
    validation_root: Path | None = None
    workspace_root: Path | None = None
    target_root: Path | None = None
    harness_root: Path | None = None
    build_target: base.ScenarioResult | None = None
    build_harness: base.ScenarioResult | None = None
    pass_run_1: base.ScenarioResult | None = None
    pass_run_2: base.ScenarioResult | None = None
    wrong_mod_id: base.ScenarioResult | None = None
    wrong_sha: base.ScenarioResult | None = None
    functional_fail: base.ScenarioResult | None = None
    crash: base.ScenarioResult | None = None
    timeout: base.ScenarioResult | None = None
    missing_result: base.ScenarioResult | None = None
    malformed_result: base.ScenarioResult | None = None
    notes: list[str] = field(default_factory=list)

    def final_status(self) -> str:
        scenarios = [
            self.build_target,
            self.build_harness,
            self.pass_run_1,
            self.pass_run_2,
            self.wrong_mod_id,
            self.wrong_sha,
            self.functional_fail,
            self.crash,
            self.timeout,
            self.missing_result,
            self.malformed_result,
        ]
        if any(item is not None and item.status == "BLOCKED" for item in scenarios):
            return "BLOCKED"
        if any(item is None or item.status != "PASS" for item in scenarios):
            return "FAIL"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "repository_commit": self.repository_commit,
            "validation_root": str(self.validation_root) if self.validation_root else None,
            "workspace_root": str(self.workspace_root) if self.workspace_root else None,
            "target_root": str(self.target_root) if self.target_root else None,
            "harness_root": str(self.harness_root) if self.harness_root else None,
            "build_target": _scenario_to_dict(self.build_target),
            "build_harness": _scenario_to_dict(self.build_harness),
            "pass_run_1": _scenario_to_dict(self.pass_run_1),
            "pass_run_2": _scenario_to_dict(self.pass_run_2),
            "wrong_mod_id": _scenario_to_dict(self.wrong_mod_id),
            "wrong_sha": _scenario_to_dict(self.wrong_sha),
            "functional_fail": _scenario_to_dict(self.functional_fail),
            "crash": _scenario_to_dict(self.crash),
            "timeout": _scenario_to_dict(self.timeout),
            "missing_result": _scenario_to_dict(self.missing_result),
            "malformed_result": _scenario_to_dict(self.malformed_result),
            "notes": list(self.notes),
            "final_status": self.final_status(),
            "total_duration_seconds": (
                max((self.finished_at - self.started_at).total_seconds(), 0.0)
                if self.finished_at is not None
                else None
            ),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_v0_2.py",
        description="Runner externo reproducible de validacion PD Agent v0.2 Batch D.",
    )
    parser.add_argument("--validation-root", type=Path, default=DEFAULT_VALIDATION_ROOT)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--keep-working-copy", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = ValidationSummary(
        started_at=datetime.now(timezone.utc),
        validation_root=args.validation_root.resolve(),
    )
    summary.workspace_root = summary.validation_root / "workspace"
    summary.workspace_root.mkdir(parents=True, exist_ok=True)
    summary.target_root = summary.workspace_root / "tests" / "fixtures" / "l11_fabric_fixture"
    summary.harness_root = summary.workspace_root / "tests" / "fixtures" / "l11_minecraft_harness"

    try:
        _check_preconditions(summary)
        _prepare_workspace(summary)
        _seed_gradle_home(summary.validation_root)
        summary.build_target = _run_gradle_build(summary.target_root, args.timeout_seconds, summary.validation_root / "gradle-home")
        if summary.build_target.status != "PASS":
            raise base.ScenarioBlocked(f"target build failed: {summary.build_target.reason}")
        summary.build_harness = _run_gradle_build(summary.harness_root, args.timeout_seconds, summary.validation_root / "gradle-home")
        if summary.build_harness.status != "PASS":
            raise base.ScenarioBlocked(f"harness build failed: {summary.build_harness.reason}")
        summary.pass_run_1 = _run_positive(summary, run_id="pass-1", launch_mode="pass")
        summary.pass_run_2 = _run_positive(summary, run_id="pass-2", launch_mode="pass")
        summary.wrong_mod_id = _run_wrong_mod_id(summary)
        summary.wrong_sha = _run_wrong_sha(summary, run_id="wrong-sha")
        summary.functional_fail = _run_positive(summary, run_id="functional-fail", launch_mode="functional_fail")
        summary.crash = _run_positive(summary, run_id="crash", launch_mode="crash")
        summary.timeout = _run_positive(summary, run_id="timeout", launch_mode="hang", timeout_seconds=30)
        summary.missing_result = _run_positive(summary, run_id="missing-result", launch_mode="missing_result")
        summary.malformed_result = _run_positive(summary, run_id="malformed-result", launch_mode="malformed_result")
    except base.ScenarioBlocked as exc:
        base._record_note(summary, f"BLOCKED: {exc}")
        _finalize(summary)
        _write_artifacts(summary)
        _print_summary(summary)
        _cleanup(summary, keep_working_copy=args.keep_working_copy)
        return 2
    except Exception as exc:  # pragma: no cover - safety net
        base._record_note(summary, f"FAIL: {type(exc).__name__}: {exc}")
        _finalize(summary)
        _write_artifacts(summary)
        _print_summary(summary)
        _cleanup(summary, keep_working_copy=args.keep_working_copy)
        return 1

    _finalize(summary)
    _write_artifacts(summary)
    _print_summary(summary)
    _cleanup(summary, keep_working_copy=args.keep_working_copy)
    return 0 if summary.final_status() == "PASS" else 1


def _check_preconditions(summary: ValidationSummary) -> None:
    base._check_java()
    result = base._run_command(["git", "status", "--short"], cwd=REPO_ROOT, timeout_seconds=30)
    if result.timed_out or result.exit_code != 0:
        raise base.ScenarioBlocked("git status failed")
    commit = base._run_command(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, timeout_seconds=30)
    if commit.timed_out or commit.exit_code != 0:
        raise base.ScenarioBlocked("git rev-parse HEAD failed")
    summary.repository_commit = commit.stdout.strip()
    summary.notes.append("prechecks: ok")
    if summary.repository_commit:
        summary.notes.append(f"repository_commit: {summary.repository_commit}")


def _prepare_workspace(summary: ValidationSummary) -> None:
    if summary.workspace_root is None or summary.target_root is None or summary.harness_root is None:
        raise base.ScenarioBlocked("workspace not initialized")
    if summary.workspace_root.exists():
        shutil.rmtree(summary.workspace_root)
    summary.workspace_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        DEFAULT_TARGET_ROOT,
        summary.target_root,
        ignore=shutil.ignore_patterns(*WORKSPACE_COPY_IGNORED_DIRS),
    )
    shutil.copytree(
        DEFAULT_HARNESS_ROOT,
        summary.harness_root,
        ignore=shutil.ignore_patterns(*WORKSPACE_COPY_IGNORED_DIRS),
    )


def _seed_gradle_home(validation_root: Path) -> None:
    gradle_home = validation_root / "gradle-home"
    gradle_home.mkdir(parents=True, exist_ok=True)
    base._seed_gradle_home(DEFAULT_TARGET_ROOT, gradle_home)


def _run_gradle_build(project_root: Path, timeout_seconds: int, gradle_home: Path) -> base.ScenarioResult:
    command = base._gradle_build_command(project_root, ["build", "--no-daemon", "--stacktrace"])
    with _temp_env(GRADLE_USER_HOME=str(gradle_home)):
        result = base._run_command(command, cwd=project_root, timeout_seconds=timeout_seconds)
    if result.timed_out:
        return base._scenario_result(project_root.name, "BLOCKED", "gradle timeout", command=" ".join(command))
    if result.exit_code != 0:
        return base._scenario_result(
            project_root.name,
            "FAIL",
            "gradle build failed",
            command=" ".join(command),
            stdout_tail=base._tail(result.stdout),
            stderr_tail=base._tail(result.stderr),
        )
    return base._scenario_result(project_root.name, "PASS", "build successful", command=" ".join(command))


def _runner(summary: ValidationSummary) -> MinecraftTestRunner:
    if summary.workspace_root is None or summary.harness_root is None:
        raise base.ScenarioBlocked("workspace missing")
    return MinecraftTestRunner(
        project_root=summary.workspace_root,
        harness_root=summary.harness_root,
        evidence_root=summary.validation_root / "evidence",
    )


def _spec(summary: ValidationSummary) -> MinecraftTestSpec:
    if summary.workspace_root is None:
        raise base.ScenarioBlocked("workspace missing")
    return MinecraftTestSpec(
        target_jar=DEFAULT_TARGET_JAR,
        target_mod_id=DEFAULT_TARGET_MOD_ID,
        minecraft_version=DEFAULT_MINECRAFT_VERSION,
        loader_version=DEFAULT_LOADER_VERSION,
        test_id=DEFAULT_TEST_ID,
        timeout_seconds=120,
    )


def _run_positive(
    summary: ValidationSummary,
    *,
    run_id: str,
    launch_mode: str,
    timeout_seconds: int | None = None,
) -> base.ScenarioResult:
    runner = _runner(summary)
    spec = _spec(summary)
    if timeout_seconds is not None:
        spec = MinecraftTestSpec(
            target_jar=spec.target_jar,
            target_mod_id=spec.target_mod_id,
            minecraft_version=spec.minecraft_version,
            loader_version=spec.loader_version,
            test_id=spec.test_id,
            timeout_seconds=timeout_seconds,
        )
    with _temp_env(GRADLE_USER_HOME=str(summary.validation_root / "gradle-home")):
        result = runner.run(spec, run_id=run_id, java_version="21", launch_mode=launch_mode)
    details = {
        "repository_commit": summary.repository_commit,
        "result_status": result.status.value,
        "result_reason": result.reason,
        "result_json": str(result.evidence_paths.result_json),
        "harness_result_json": str(result.evidence_paths.harness_result_json),
        "stdout_log": str(result.evidence_paths.stdout_log),
        "stderr_log": str(result.evidence_paths.stderr_log),
        "latest_log": str(result.evidence_paths.latest_log),
        "crash_reports_dir": str(result.evidence_paths.crash_reports_dir),
        "target_jar_path": str(result.target.path),
        "target_mod_id": result.target.mod_id,
        "target_sha256": result.target.sha256,
        "minecraft_version": result.spec.minecraft_version,
        "loader_version": result.spec.loader_version,
        "java_version": result.target.java_version,
        "server_started": result.metadata.get("server_started"),
        "runtime_target_sha_match": result.metadata.get("target_sha_match"),
        "functional_test_result": result.metadata.get("harness_result_state"),
        "shutdown_requested": (
            result.runtime_evidence.metadata.get("shutdown_requested")
            if result.runtime_evidence is not None
            else None
        ),
        "process_exit_code": result.process_evidence.exit_code if result.process_evidence else None,
        "process_timed_out": result.process_evidence.timed_out if result.process_evidence else None,
        "duration_seconds": result.duration_seconds,
        "evidence_root": str(result.evidence_paths.root),
    }
    if result.status.value == "PASS" and launch_mode == "pass":
        return base._scenario_result("Positive runtime", "PASS", "completed", **details)
    if result.status.value == "FAIL" and launch_mode == "functional_fail":
        return base._scenario_result("Functional fail", "PASS", "fail classified", **details)
    if result.status.value == "CRASH" and launch_mode == "crash":
        return base._scenario_result("Runtime crash", "PASS", "crash classified", **details)
    if result.status.value == "TIMEOUT" and launch_mode == "hang":
        return base._scenario_result("Runtime timeout", "PASS", "timeout classified", **details)
    if result.status.value == "INFRA_ERROR" and launch_mode in {"missing_result", "malformed_result"}:
        return base._scenario_result("Runtime infra", "PASS", f"{launch_mode} classified", **details)
    if result.status.value == "PASS" and launch_mode != "pass":
        return base._scenario_result("Unexpected PASS", "FAIL", "negative scenario passed", **details)
    return base._scenario_result("Runtime scenario", "FAIL", result.reason, **details)


def _run_wrong_mod_id(summary: ValidationSummary) -> base.ScenarioResult:
    runner = _runner(summary)
    spec = MinecraftTestSpec(
        target_jar=DEFAULT_TARGET_JAR,
        target_mod_id="wrongmod",
        minecraft_version=DEFAULT_MINECRAFT_VERSION,
        loader_version=DEFAULT_LOADER_VERSION,
        test_id=DEFAULT_TEST_ID,
        timeout_seconds=120,
    )
    try:
        with _temp_env(GRADLE_USER_HOME=str(summary.validation_root / "gradle-home")):
            runner.run(spec, run_id="wrong-mod-id", java_version="21")
    except MinecraftTestValidationError:
        return base._scenario_result("Wrong mod id", "PASS", "validation rejected wrong mod id")
    return base._scenario_result("Wrong mod id", "FAIL", "unexpected PASS")


def _run_wrong_sha(summary: ValidationSummary, *, run_id: str) -> base.ScenarioResult:
    runner = _runner(summary)
    spec = _spec(summary)
    with _temp_env(GRADLE_USER_HOME=str(summary.validation_root / "gradle-home")):
        result = runner.run(
            spec,
            run_id=run_id,
            java_version="21",
            expected_sha256="0" * 64,
        )
    target_sha_match = result.metadata.get("target_sha_match")
    runtime_target_sha_match = result.runtime_evidence.metadata.get("target_sha_match") if result.runtime_evidence else None
    if (
        result.reason == "target sha mismatch"
        and (target_sha_match is False or runtime_target_sha_match is False)
    ):
        return base._scenario_result(
            "Wrong SHA",
            "PASS",
            "sha mismatch classified",
            result_status=result.status.value,
            result_reason=result.reason,
        )
    return base._scenario_result("Wrong SHA", "FAIL", result.reason)


def _scenario_to_dict(item: base.ScenarioResult | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {"name": item.name, "status": item.status, "reason": item.reason, "details": item.details}


def _write_artifacts(summary: ValidationSummary) -> None:
    assert summary.validation_root is not None
    base._write_json(summary.validation_root / "summary.json", summary.to_dict())
    (summary.validation_root / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")


def _summary_markdown(summary: ValidationSummary) -> str:
    lines = [
        "# PD Agent v0.2 Batch D Validation",
        "",
        f"- Final status: `{summary.final_status()}`",
        f"- Repository commit: `{summary.repository_commit}`" if summary.repository_commit else "- Repository commit: unknown",
        (
            f"- Total duration: `{max((summary.finished_at - summary.started_at).total_seconds(), 0.0):.3f}s`"
            if summary.finished_at is not None
            else "- Total duration: unknown"
        ),
        "",
        "## Scenarios",
    ]
    for item in (
        summary.build_target,
        summary.build_harness,
        summary.pass_run_1,
        summary.pass_run_2,
        summary.wrong_mod_id,
        summary.wrong_sha,
        summary.functional_fail,
        summary.crash,
        summary.timeout,
        summary.missing_result,
        summary.malformed_result,
    ):
        if item is not None:
            lines.append(f"- {item.name}: {item.status} - {item.reason}")
    if summary.notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in summary.notes)
    return "\n".join(lines) + "\n"


def _print_summary(summary: ValidationSummary) -> None:
    print("L11 v0.2 VALIDATION - BATCH D")
    print()
    print(f"Repository commit: {summary.repository_commit or 'NOT RECORDED'}")
    print(f"Target build: {summary.build_target.status if summary.build_target else 'NOT RUN'}")
    print(f"Harness build: {summary.build_harness.status if summary.build_harness else 'NOT RUN'}")
    print(f"Pass run 1: {summary.pass_run_1.status if summary.pass_run_1 else 'NOT RUN'}")
    print(f"Pass run 2: {summary.pass_run_2.status if summary.pass_run_2 else 'NOT RUN'}")
    print(f"Wrong mod id: {summary.wrong_mod_id.status if summary.wrong_mod_id else 'NOT RUN'}")
    print(f"Wrong SHA: {summary.wrong_sha.status if summary.wrong_sha else 'NOT RUN'}")
    print(f"Functional fail: {summary.functional_fail.status if summary.functional_fail else 'NOT RUN'}")
    print(f"Crash: {summary.crash.status if summary.crash else 'NOT RUN'}")
    print(f"Timeout: {summary.timeout.status if summary.timeout else 'NOT RUN'}")
    print(f"Missing result: {summary.missing_result.status if summary.missing_result else 'NOT RUN'}")
    print(f"Malformed result: {summary.malformed_result.status if summary.malformed_result else 'NOT RUN'}")
    print()
    print(f"FINAL: {summary.final_status()}")
    if summary.finished_at is not None:
        duration = max((summary.finished_at - summary.started_at).total_seconds(), 0.0)
        print(f"Duration: {duration:.3f}s")
    print(f"Evidence: {summary.validation_root}")


def _cleanup(summary: ValidationSummary, *, keep_working_copy: bool) -> None:
    if keep_working_copy:
        return
    if summary.workspace_root and summary.workspace_root.exists():
        shutil.rmtree(summary.workspace_root, ignore_errors=True)


def _finalize(summary: ValidationSummary) -> None:
    summary.finished_at = datetime.now(timezone.utc)


@contextmanager
def _temp_env(**changes: str) -> Iterator[None]:
    old_values = {key: base.os.environ.get(key) for key in changes}
    try:
        for key, value in changes.items():
            base.os.environ[key] = value
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                base.os.environ.pop(key, None)
            else:
                base.os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
