"""Validacion externa reproducible de PD Agent v0.1.1."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

from openai import OpenAI

import validate_v0_1 as base


REPO_ROOT = base.REPO_ROOT
DEFAULT_CANDIDATE_ROOT = base.DEFAULT_CANDIDATE_ROOT
DEFAULT_VALIDATION_ROOT = Path(base.tempfile.gettempdir()) / "pd-agent-v0.1.1-validation"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_PYTEST_TIMEOUT_SECONDS = 1800
DEFAULT_TASK = (
    "Inspecciona el archivo Java indicado. "
    "Lee primero el source. "
    "Cambia solo el string existente de acceptance en ExampleMod.message() "
    "de \"\" a \"PD Agent v0.1.1 acceptance\". "
    "No cambies Gradle ni la arquitectura. "
    "Despues compila y valida el artefacto."
)
DEFAULT_EXPECTED_FINAL_TEXT = 'return "PD Agent v0.1.1 acceptance";'


@dataclass(slots=True)
class LiveSummary:
    started_at: datetime
    finished_at: datetime | None = None
    candidate_root: Path | None = None
    validation_root: Path | None = None
    working_root: Path | None = None
    evidence_root: Path | None = None
    baseline_build: base.ScenarioResult | None = None
    live_run: base.ScenarioResult | None = None
    repair: base.ScenarioResult | None = None
    suite: base.ScenarioResult | None = None
    notes: list[str] = field(default_factory=list)

    def final_status(self) -> str:
        results = [self.baseline_build, self.live_run, self.suite]
        if any(result is not None and result.status == "BLOCKED" for result in results):
            return "BLOCKED"
        if any(result is None or result.status != "PASS" for result in results):
            return "FAIL"
        if self.repair is not None and self.repair.status == "FAIL":
            return "FAIL"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "candidate_root": str(self.candidate_root) if self.candidate_root else None,
            "validation_root": str(self.validation_root) if self.validation_root else None,
            "working_root": str(self.working_root) if self.working_root else None,
            "evidence_root": str(self.evidence_root) if self.evidence_root else None,
            "baseline_build": _scenario_to_dict(self.baseline_build),
            "live_run": _scenario_to_dict(self.live_run),
            "repair": _scenario_to_dict(self.repair),
            "suite": _scenario_to_dict(self.suite),
            "notes": list(self.notes),
            "final_status": self.final_status(),
        }


@dataclass(slots=True)
class CommandResult:
    command: tuple[str, ...]
    cwd: Path
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(slots=True)
class RecordedResponsesCall:
    request: dict[str, Any]
    response: dict[str, Any] | None


class RecordingResponses:
    def __init__(self, real: Any, calls: list[RecordedResponsesCall]) -> None:
        self._real = real
        self._calls = calls

    def create(self, **kwargs: Any) -> Any:
        response = self._real.create(**kwargs)
        self._calls.append(
            RecordedResponsesCall(
                request=_sanitize_request(kwargs),
                response=_sanitize_response(response),
            )
        )
        return response


class RecordingOpenAIClient:
    def __init__(self, client: OpenAI) -> None:
        self._client = client
        self.calls: list[RecordedResponsesCall] = []
        self.responses = RecordingResponses(client.responses, self.calls)

    def with_options(self, **kwargs: Any) -> "RecordingOpenAIClient":
        return self


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_v0_1_1.py",
        description="Runner externo reproducible de validacion PD Agent v0.1.1.",
    )
    parser.add_argument("--candidate-root", type=Path, default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--validation-root", type=Path, default=DEFAULT_VALIDATION_ROOT)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--pytest-timeout-seconds", type=int, default=DEFAULT_PYTEST_TIMEOUT_SECONDS)
    parser.add_argument("--keep-working-copy", action="store_true")
    parser.add_argument("--task", default=DEFAULT_TASK)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    summary = LiveSummary(
        started_at=datetime.now(timezone.utc),
        candidate_root=args.candidate_root.resolve(),
        validation_root=args.validation_root.resolve(),
    )
    summary.evidence_root = summary.validation_root / "evidence"
    summary.evidence_root.mkdir(parents=True, exist_ok=True)
    summary.working_root = summary.validation_root / "working"
    summary.working_root.mkdir(parents=True, exist_ok=True)

    try:
        _run_prechecks(summary, args)
        summary.baseline_build = _run_baseline_build(summary, args)
        if summary.baseline_build.status != "PASS":
            raise base.ScenarioBlocked(f"baseline failed: {summary.baseline_build.reason}")
        summary.live_run = _run_live_e2e(summary, args)
        summary.repair = _scenario_result("Repair live", "NOT RUN", "not requested")
        summary.suite = _run_suite(summary, args)
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


def _run_prechecks(summary: LiveSummary, args: argparse.Namespace) -> None:
    if base.sys.version_info < (3, 13):
        raise base.ScenarioBlocked("Python >= 3.13 requerido")
    base._check_pd_agent_import()
    base._check_git_clean(REPO_ROOT)
    base._check_java()
    candidate = args.candidate_root.resolve()
    if not candidate.exists():
        raise base.ScenarioBlocked(f"no existe candidate root: {candidate}")
    wrapper = candidate / "gradlew.bat"
    if not wrapper.exists():
        raise base.ScenarioBlocked(f"falta gradlew.bat en: {candidate}")
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("PD_AGENT_MODEL")
    if not api_key:
        raise base.ScenarioBlocked("OPENAI_API_KEY missing")
    if not model:
        raise base.ScenarioBlocked("PD_AGENT_MODEL missing")
    summary.notes.append("prechecks: ok")
    summary.notes.append(f"model: {model}")
    summary.notes.append("OPENAI_API_KEY: present")


def _run_baseline_build(summary: LiveSummary, args: argparse.Namespace) -> base.ScenarioResult:
    work_root = _prepare_working_copy(summary, suffix="baseline")
    command = base._gradle_build_command(work_root, ["build", "--no-daemon"])
    gradle_home = summary.validation_root / "gradle-home-baseline"
    _seed_gradle_home(work_root, gradle_home)
    result = base._run_command(command, cwd=work_root, timeout_seconds=args.timeout_seconds, extra_env={"GRADLE_USER_HOME": str(gradle_home)})
    base._write_command_evidence(summary, "baseline-build", result)
    if result.timed_out:
        return _scenario_result("Baseline Fabric build", "BLOCKED", "timeout", command=" ".join(command))
    if result.exit_code != 0:
        return _scenario_result(
            "Baseline Fabric build",
            "FAIL",
            "build failed",
            command=" ".join(command),
            stdout_tail=base._tail(result.stdout),
            stderr_tail=base._tail(result.stderr),
        )
    return _scenario_result("Baseline Fabric build", "PASS", "build successful", command=" ".join(command))


def _run_live_e2e(summary: LiveSummary, args: argparse.Namespace) -> base.ScenarioResult:
    work_root = _prepare_working_copy(summary, suffix="live-e2e")
    from pd_agent import ArtifactValidator, GradleBuildRunner, ProjectInspector
    from pd_agent.config import ExecutionLimits
    from pd_agent.context import ContextManager
    from pd_agent.pass_policy import evaluate_pass
    from pd_agent.providers import OpenAIProvider
    from pd_agent.reporting import RunStorage
    from pd_agent.runtime import RunController

    edit = base._prepare_source_edit(work_root)
    expected_final_text = DEFAULT_EXPECTED_FINAL_TEXT
    if expected_final_text not in edit.after_text:
        edit = base.SourceEditResult(
            path=edit.path,
            relative_path=edit.relative_path,
            before_hash=edit.before_hash,
            after_hash=base._sha256_text(edit.after_text.replace('return "";', expected_final_text, 1)),
            before_text=edit.before_text,
            after_text=edit.after_text.replace('return "";', expected_final_text, 1),
            changed=True,
            replacement=expected_final_text,
        )
    api_key = os.environ["OPENAI_API_KEY"]
    model = os.environ["PD_AGENT_MODEL"]
    real_client = OpenAI(api_key=api_key, max_retries=0)
    recording_client = RecordingOpenAIClient(real_client)
    provider = OpenAIProvider(model=model, api_key=api_key, provider_retry_limit=0, client=recording_client)
    storage = RunStorage(summary.evidence_root / "live-e2e")
    controller = RunController(
        provider=provider,
        storage=storage,
        build_runner=GradleBuildRunner(reporting=storage),
        artifact_validator=ArtifactValidator(reporting=storage),
        context_manager=ContextManager(),
        limits=ExecutionLimits(),
        project_inspector=ProjectInspector(),
    )
    gradle_home = summary.validation_root / "gradle-home-live-e2e"
    _seed_gradle_home(work_root, gradle_home)
    with base._temp_env(GRADLE_USER_HOME=str(gradle_home)):
        run_state, report = controller.run(work_root, args.task)
    evaluation = evaluate_pass(storage, run_state.run_id)
    paths = storage.paths_for(run_state.run_id)
    after_text = edit.path.read_text(encoding="utf-8")
    after_hash = base._sha256_text(after_text)
    source_changed = edit.before_hash != after_hash and expected_final_text in after_text
    usage_summary = _usage_summary(recording_client.calls)
    event_types = [event.event_type.value for event in storage.read_events(run_state.run_id)]
    live_details = {
        "run_id": run_state.run_id,
        "model": model,
        "source_path": str(edit.relative_path),
        "before_hash": edit.before_hash,
        "after_hash": after_hash,
        "source_changed": source_changed,
        "expected_final_text": expected_final_text,
        "tool_calls": _tool_call_sequence(recording_client.calls),
        "usage": usage_summary,
        "event_types": event_types,
        "final_report_json": str(paths.final_report_json),
        "final_report_md": str(paths.final_report_md),
        "events_jsonl": str(paths.events_jsonl),
        "final_report_json_exists": paths.final_report_json.exists(),
        "final_report_md_exists": paths.final_report_md.exists(),
        "events_jsonl_exists": paths.events_jsonl.exists(),
        "artifact_path": str(report.final_build.path) if report.final_build and report.final_build.path else None,
        "final_state": run_state.state.value,
        "termination_reason": run_state.termination_reason,
        "evaluation_passed": evaluation.passed,
        "evaluation_reason": evaluation.reason,
    }
    secret_found, redacted_seen = _secret_scan(summary.evidence_root / "live-e2e", api_key)
    live_details["secret_found"] = secret_found
    live_details["redacted_seen"] = redacted_seen
    base._write_json(summary.evidence_root / "live-e2e" / "run.json", live_details)
    if (
        run_state.state.value == "COMPLETED"
        and evaluation.passed
        and report.final_state.value == "COMPLETED"
        and report.final_build is not None
        and report.final_build.exit_code == 0
        and report.artifact is not None
        and report.artifact.classification == "VALID"
        and source_changed
        and not secret_found
    ):
        return _scenario_result(
            "OpenAI live E2E",
            "PASS",
            "completed",
            run_id=run_state.run_id,
            model=model,
            source_path=str(edit.relative_path),
            before_hash=edit.before_hash,
            after_hash=after_hash,
            artifact=str(report.final_build.path) if report.final_build and report.final_build.path else None,
            usage=usage_summary,
            secret_found=secret_found,
        )
    reason = "source edit not verified" if not source_changed else evaluation.reason
    if secret_found:
        reason = "secret found in evidence"
    return _scenario_result(
        "OpenAI live E2E",
        "FAIL",
        reason,
        run_id=run_state.run_id,
        final_state=run_state.state.value,
        source_path=str(edit.relative_path),
        before_hash=edit.before_hash,
        after_hash=after_hash,
        source_changed=source_changed,
        usage=usage_summary,
        secret_found=secret_found,
    )


def _run_suite(summary: LiveSummary, args: argparse.Namespace) -> base.ScenarioResult:
    pytest_temp = summary.validation_root / "pytest-tmp"
    pytest_temp.mkdir(parents=True, exist_ok=True)
    command = [base.sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    result = base._run_command(
        command,
        cwd=REPO_ROOT,
        timeout_seconds=args.pytest_timeout_seconds,
        extra_env={
            "TMP": str(pytest_temp),
            "TEMP": str(pytest_temp),
            "TMPDIR": str(pytest_temp),
            "PYTEST_DEBUG_TEMPROOT": str(pytest_temp),
        },
    )
    base._write_command_evidence(summary, "pytest-suite", result)
    if result.timed_out:
        return _scenario_result("Suite PD Agent", "BLOCKED", "pytest timeout", command=" ".join(command))
    if result.exit_code == 0:
        return _scenario_result("Suite PD Agent", "PASS", "pytest passed", command=" ".join(command))
    return _scenario_result(
        "Suite PD Agent",
        "FAIL",
        "pytest failed",
        command=" ".join(command),
        stdout_tail=base._tail(result.stdout),
        stderr_tail=base._tail(result.stderr),
    )


def _prepare_working_copy(summary: LiveSummary, *, suffix: str) -> Path:
    candidate = summary.candidate_root
    if candidate is None:
        raise base.ScenarioBlocked("candidate root missing")
    work_root = summary.working_root / suffix
    if work_root.exists():
        shutil.rmtree(work_root)
    shutil.copytree(candidate, work_root, ignore=shutil.ignore_patterns(*base.IGNORED_COPY_DIRS))
    return work_root


def _seed_gradle_home(project_root: Path, gradle_home: Path) -> None:
    base._seed_gradle_home(project_root, gradle_home)


def _scenario_result(name: str, status: str, reason: str, **details: Any) -> base.ScenarioResult:
    return base._scenario_result(name, status, reason, **details)


def _scenario_to_dict(scenario: base.ScenarioResult | None) -> dict[str, Any] | None:
    if scenario is None:
        return None
    return {
        "name": scenario.name,
        "status": scenario.status,
        "reason": scenario.reason,
        "details": scenario.details,
    }


def _usage_summary(calls: Sequence[RecordedResponsesCall]) -> dict[str, Any] | None:
    for call in calls:
        response = call.response or {}
        usage = response.get("usage")
        if isinstance(usage, Mapping):
            summary = {key: usage.get(key) for key in ("input_tokens", "output_tokens", "total_tokens", "cached_tokens")}
            return {key: value for key, value in summary.items() if value is not None}
    return None


def _tool_call_sequence(calls: Sequence[RecordedResponsesCall]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for call in calls:
        for item in call.request.get("input", []):
            if not isinstance(item, Mapping):
                continue
            item_type = item.get("type")
            if item_type not in {"function_call", "function_call_output"}:
                continue
            entry = {"request_index": len(sequence), "type": item_type}
            for key in ("call_id", "name", "arguments", "output"):
                if key in item:
                    entry[key] = item[key]
            sequence.append(entry)
    return sequence


def _sanitize_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "model": payload.get("model"),
        "store": payload.get("store"),
        "instructions": payload.get("instructions"),
        "tool_count": len(payload.get("tools", []) or []),
        "input": [_sanitize_input_item(item) for item in payload.get("input", []) or []],
    }


def _sanitize_input_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        return {"type": type(item).__name__}
    data: dict[str, Any] = {"type": item.get("type")}
    for key in ("role", "call_id", "name", "status"):
        if key in item:
            data[key] = item.get(key)
    if item.get("type") == "message":
        data["content_type"] = type(item.get("content")).__name__
    if item.get("type") == "function_call":
        data["arguments"] = item.get("arguments")
    if item.get("type") == "function_call_output":
        data["output"] = item.get("output")
    return data


def _sanitize_response(response: Any) -> dict[str, Any]:
    return {
        "id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "status": getattr(response, "status", None),
        "usage": _mapping_or_none(getattr(response, "usage", None)),
        "output": [_sanitize_output_item(item) for item in (getattr(response, "output", None) or [])],
    }


def _sanitize_output_item(item: Any) -> dict[str, Any]:
    data = {"type": getattr(item, "type", None)}
    for key in ("call_id", "name", "status", "id"):
        value = getattr(item, key, None)
        if value is not None:
            data[key] = value
    return data


def _mapping_or_none(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump") and callable(value.model_dump):
        dumped = value.model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    if hasattr(value, "__dict__"):
        return {key: item for key, item in value.__dict__.items() if not key.startswith("_")}
    return {"value": value}


def _secret_scan(root: Path, api_key: str) -> tuple[bool, bool]:
    secret_found = False
    redacted_seen = False
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if api_key and api_key in text:
            secret_found = True
        if "[REDACTED]" in text:
            redacted_seen = True
    return secret_found, redacted_seen


def _finalize(summary: LiveSummary) -> None:
    summary.finished_at = datetime.now(timezone.utc)


def _write_artifacts(summary: LiveSummary) -> None:
    assert summary.evidence_root is not None
    base._write_json(summary.evidence_root / "summary.json", summary.to_dict())
    _write_validation_doc(summary)
    summary.evidence_root.joinpath("summary.md").write_text(_summary_markdown(summary), encoding="utf-8")


def _write_validation_doc(summary: LiveSummary) -> None:
    doc_path = REPO_ROOT / "docs" / "validation" / "PD_AGENT_V0.1.1_VALIDATION.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# PD Agent v0.1.1 Validation",
        "",
        f"- Fecha: {summary.started_at.isoformat()}",
        f"- Commit validado: {base.subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()}",
        f"- Modelo usado: {os.environ.get('PD_AGENT_MODEL', 'missing')}",
        f"- Fixture: {summary.candidate_root}",
        f"- Run id: {summary.live_run.details.get('run_id') if summary.live_run else 'n/a'}",
        f"- Source hash before: {summary.live_run.details.get('before_hash') if summary.live_run else 'n/a'}",
        f"- Source hash after: {summary.live_run.details.get('after_hash') if summary.live_run else 'n/a'}",
        f"- Gradle result: {summary.baseline_build.status if summary.baseline_build else 'n/a'} / {summary.live_run.reason if summary.live_run else 'n/a'}",
        f"- Artifact result: {summary.live_run.details.get('artifact') if summary.live_run else 'n/a'}",
        f"- Final state: {summary.live_run.details.get('final_state') if summary.live_run else 'n/a'}",
        f"- PASS evaluation: {summary.live_run.details.get('evaluation_passed') if summary.live_run else 'n/a'}",
        f"- Secret scan: {summary.live_run.details.get('secret_found') if summary.live_run else 'n/a'}",
        f"- Usage: {json.dumps(summary.live_run.details.get('usage'), ensure_ascii=False) if summary.live_run else 'n/a'}",
        "- Repair live: NOT RUN",
        "- Minecraft runtime: NOT VALIDATED",
        "",
    ]
    if summary.live_run and summary.live_run.details.get("tool_calls"):
        lines.append("## Tool calls")
        for item in summary.live_run.details["tool_calls"]:
            lines.append(
                f"- {item.get('type')} call_id={item.get('call_id')} name={item.get('name')} status={item.get('status')}"
            )
    doc_path.write_text("\n".join(lines), encoding="utf-8")


def _summary_markdown(summary: LiveSummary) -> str:
    lines = [
        "# L11 Validation v0.1.1",
        "",
        f"- Candidate root: `{summary.candidate_root}`",
        f"- Validation root: `{summary.validation_root}`",
        f"- Working root: `{summary.working_root}`",
        f"- Final status: `{summary.final_status()}`",
        "",
        "## Scenarios",
    ]
    for item in (summary.baseline_build, summary.live_run, summary.repair, summary.suite):
        if item is None:
            continue
        lines.append(f"- {item.name}: {item.status} - {item.reason}")
    if summary.notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in summary.notes)
    return "\n".join(lines) + "\n"


def _print_summary(summary: LiveSummary) -> None:
    print("L11 v0.1.1 VALIDATION")
    print()
    print(f"Baseline Fabric build: {_scenario_status(summary.baseline_build)}")
    print(f"OpenAI live E2E: {_scenario_status(summary.live_run)}")
    print(f"Repair live: {_scenario_status(summary.repair)}")
    print(f"Suite PD Agent: {_scenario_status(summary.suite)}")
    print()
    print(f"FINAL: {summary.final_status()}")
    print(f"Evidence: {summary.evidence_root}")


def _cleanup(summary: LiveSummary, *, keep_working_copy: bool) -> None:
    if keep_working_copy:
        return
    if summary.working_root and summary.working_root.exists():
        shutil.rmtree(summary.working_root, ignore_errors=True)
    if summary.validation_root and summary.validation_root.exists():
        for path in summary.validation_root.glob("gradle-home-*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


def _scenario_status(item: base.ScenarioResult | None) -> str:
    if item is None:
        return "NOT RUN"
    return item.status


if __name__ == "__main__":
    raise SystemExit(main())
