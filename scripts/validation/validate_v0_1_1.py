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

import validate_v0_1 as base
from pd_agent.providers import GeminiProvider


REPO_ROOT = base.REPO_ROOT
DEFAULT_CANDIDATE_ROOT = base.DEFAULT_CANDIDATE_ROOT
DEFAULT_VALIDATION_ROOT = Path(base.tempfile.gettempdir()) / "pd-agent-v0.1.1-validation"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_PYTEST_TIMEOUT_SECONDS = 1800
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_TASK = (
    "Abre y lee primero `src/main/java/dev/pdpunto/l11/ExampleMod.java`. "
    "Luego cambia solo el string existente de acceptance en ExampleMod.message() "
    "de \"\" a \"PD Agent Gemini 3 v0.1.1 live acceptance\" usando write_file sobre el mismo archivo. "
    "No cambies Gradle ni la arquitectura. "
    "Despues compila y valida el artefacto."
)
DEFAULT_EXPECTED_FINAL_TEXT = 'return "PD Agent Gemini 3 v0.1.1 live acceptance";'


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
class RecordedGenerateContentCall:
    request: dict[str, Any]
    response: dict[str, Any] | None


class RecordingGenerateContent:
    def __init__(self, real: Any, calls: list[RecordedGenerateContentCall]) -> None:
        self._real = real
        self._calls = calls

    def generate_content(self, **kwargs: Any) -> Any:
        response = self._real.generate_content(**kwargs)
        self._calls.append(
            RecordedGenerateContentCall(
                request=_sanitize_request(kwargs),
                response=_sanitize_response(response),
            )
        )
        return response


class RecordingGeminiClient:
    def __init__(self, client: Any) -> None:
        self._client = client
        self.calls: list[RecordedGenerateContentCall] = []
        self.models = RecordingGenerateContent(client.models, self.calls)


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
    _check_git_clean(summary, REPO_ROOT)
    base._check_java()
    candidate = args.candidate_root.resolve()
    if not candidate.exists():
        raise base.ScenarioBlocked(f"no existe candidate root: {candidate}")
    wrapper = candidate / "gradlew.bat"
    if not wrapper.exists():
        raise base.ScenarioBlocked(f"falta gradlew.bat en: {candidate}")
    provider = os.environ.get("PD_AGENT_PROVIDER", "").strip().lower()
    env_model = os.environ.get("PD_AGENT_MODEL")
    api_key = os.environ.get("GEMINI_API_KEY")
    if provider != "gemini":
        raise base.ScenarioBlocked("PD_AGENT_PROVIDER must be gemini")
    if not api_key:
        raise base.ScenarioBlocked("GEMINI_API_KEY missing")
    summary.notes.append("prechecks: ok")
    summary.notes.append("provider: gemini")
    summary.notes.append(f"PD_AGENT_MODEL env: {env_model if env_model else 'missing'}")
    summary.notes.append(f"selected model: {DEFAULT_GEMINI_MODEL}")
    summary.notes.append("GEMINI_API_KEY: present")


def _check_git_clean(summary: LiveSummary, root: Path) -> None:
    result = base._run_command(["git", "status", "--short"], cwd=root, timeout_seconds=30)
    if result.timed_out:
        raise base.ScenarioBlocked("git status timeout")
    if result.exit_code != 0:
        raise base.ScenarioBlocked("git status fallo")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    allowed = {"?? docs/validation/PD_AGENT_V0.1.1_VALIDATION.md"}
    unexpected = [line for line in lines if line not in allowed]
    if unexpected:
        raise base.ScenarioBlocked(f"working tree sucio: {unexpected[0]}")
    if any(line in allowed for line in lines):
        summary.notes.append("untracked preexisting: docs/validation/PD_AGENT_V0.1.1_VALIDATION.md")


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
    api_key = os.environ["GEMINI_API_KEY"]
    model = DEFAULT_GEMINI_MODEL
    provider = GeminiProvider(model=model, api_key=api_key, provider_retry_limit=0)
    recording_client = RecordingGeminiClient(provider._client)  # noqa: SLF001
    provider._client = recording_client  # noqa: SLF001
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
    continuation_summary = _continuation_summary(recording_client.calls)
    tool_call_count = sum(1 for item in _tool_call_sequence(recording_client.calls) if item["type"] == "function_call")
    live_details = {
        "run_id": run_state.run_id,
        "provider": "gemini",
        "model": model,
        "selected_model": DEFAULT_GEMINI_MODEL,
        "env_model": os.environ.get("PD_AGENT_MODEL"),
        "source_path": str(edit.relative_path),
        "before_hash": edit.before_hash,
        "after_hash": after_hash,
        "source_changed": source_changed,
        "expected_final_text": expected_final_text,
        "tool_calls": _tool_call_sequence(recording_client.calls),
        "tool_call_count": tool_call_count,
        "continuation": continuation_summary,
        "usage": usage_summary,
        "event_types": event_types,
        "final_report_json": str(paths.final_report_json),
        "final_report_md": str(paths.final_report_md),
        "events_jsonl": str(paths.events_jsonl),
        "final_report_json_exists": paths.final_report_json.exists(),
        "final_report_md_exists": paths.final_report_md.exists(),
        "events_jsonl_exists": paths.events_jsonl.exists(),
        "artifact_path": str(report.artifact.path) if report.artifact and report.artifact.path else None,
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
        and continuation_summary["replay_success"]
        and tool_call_count > 0
        and not secret_found
    ):
        return _scenario_result(
            "Gemini live E2E",
            "PASS",
            "completed",
            run_id=run_state.run_id,
            provider="gemini",
            model=model,
            continuation_replay_success=continuation_summary["replay_success"],
            tool_call_count=tool_call_count,
            source_path=str(edit.relative_path),
            before_hash=edit.before_hash,
            after_hash=after_hash,
            artifact=str(report.artifact.path) if report.artifact and report.artifact.path else None,
            usage=usage_summary,
            secret_found=secret_found,
        )
    reason = "source edit not verified" if not source_changed else evaluation.reason
    if secret_found:
        reason = "secret found in evidence"
    return _scenario_result(
        "Gemini live E2E",
        "FAIL",
        reason,
        run_id=run_state.run_id,
        final_state=run_state.state.value,
        provider="gemini",
        source_path=str(edit.relative_path),
        before_hash=edit.before_hash,
        after_hash=after_hash,
        source_changed=source_changed,
        continuation_replay_success=continuation_summary["replay_success"],
        tool_call_count=tool_call_count,
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


def _usage_summary(calls: Sequence[RecordedGenerateContentCall]) -> dict[str, Any] | None:
    for call in calls:
        response = call.response or {}
        usage = response.get("usage")
        if isinstance(usage, Mapping):
            summary = {key: usage.get(key) for key in ("input_tokens", "output_tokens", "total_tokens", "cached_tokens")}
            return {key: value for key, value in summary.items() if value is not None}
    return None


def _tool_call_sequence(calls: Sequence[RecordedGenerateContentCall]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for call in calls:
        for content_index, item in enumerate(call.request.get("contents", [])):
            if not isinstance(item, Mapping):
                continue
            for part_index, part in enumerate(item.get("parts", []) or []):
                if not isinstance(part, Mapping):
                    continue
                function_call = part.get("function_call")
                function_response = part.get("function_response")
                if function_call is None and function_response is None:
                    continue
                entry = {
                    "request_index": len(sequence),
                    "content_index": content_index,
                    "part_index": part_index,
                    "type": "function_call" if function_call is not None else "function_call_output",
                }
                payload = function_call if function_call is not None else function_response
                if isinstance(payload, Mapping):
                    for key in ("call_id", "name", "arguments", "output"):
                        if key in payload:
                            entry[key] = payload[key]
                sequence.append(entry)
    return sequence


def _continuation_summary(calls: Sequence[RecordedGenerateContentCall]) -> dict[str, Any]:
    response_hashes: list[str] = []
    request_hashes: list[str] = []
    response_records: list[dict[str, Any]] = []
    request_records: list[dict[str, Any]] = []

    for call_index, call in enumerate(calls):
        for content_index, item in enumerate(call.response.get("output", []) if call.response else []):
            parts = item.get("content", []) if isinstance(item, Mapping) else []
            for part_index, part in enumerate(parts):
                if not isinstance(part, Mapping):
                    continue
                hash_value = part.get("thought_signature_sha256")
                if not hash_value:
                    continue
                record = {
                    "call_index": call_index,
                    "content_index": content_index,
                    "part_index": part_index,
                    "provider": "gemini",
                    "target": part.get("function_call", {}).get("call_id") if isinstance(part.get("function_call"), Mapping) else None,
                    "position": part.get("thought_signature_position"),
                    "payload_present": True,
                    "payload_sha256": hash_value,
                }
                response_records.append(record)
                response_hashes.append(str(hash_value))

        for content_index, item in enumerate(call.request.get("contents", [])):
            if not isinstance(item, Mapping):
                continue
            for part_index, part in enumerate(item.get("parts", []) or []):
                if not isinstance(part, Mapping):
                    continue
                hash_value = part.get("thought_signature_sha256")
                if not hash_value:
                    continue
                record = {
                    "call_index": call_index,
                    "content_index": content_index,
                    "part_index": part_index,
                    "provider": "gemini",
                    "target": part.get("function_call", {}).get("call_id") if isinstance(part.get("function_call"), Mapping) else None,
                    "position": part.get("thought_signature_position"),
                    "payload_present": True,
                    "payload_sha256": hash_value,
                }
                request_records.append(record)
                request_hashes.append(str(hash_value))

    replay_success = bool(response_hashes and response_hashes == request_hashes[: len(response_hashes)])
    return {
        "continuation_detected": bool(response_records),
        "provider": "gemini" if response_records else None,
        "response_records": response_records,
        "request_records": request_records,
        "payload_present": bool(response_records),
        "replay_success": replay_success,
    }


def _sanitize_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "model": payload.get("model"),
        "contents": [_sanitize_content_item(item) for item in payload.get("contents", []) or []],
        "config": _sanitize_config(payload.get("config")),
    }


def _sanitize_content_item(item: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": getattr(item, "type", None),
        "role": _item_value(item, "role"),
    }
    parts = _item_value(item, "parts") or []
    data["parts"] = [_sanitize_part_item(part, position=index) for index, part in enumerate(parts) if part is not None]
    return data


def _sanitize_part_item(item: Any, *, position: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"type": _item_value(item, "type")}
    text = _item_value(item, "text")
    if text is not None:
        data["text"] = text
    function_call = _item_value(item, "function_call") or _item_value(item, "functionCall")
    if function_call is not None:
        data["function_call"] = {
            key: value
            for key, value in {
                "call_id": _item_value(function_call, "id"),
                "name": _item_value(function_call, "name"),
                "arguments": _item_value(function_call, "args") if _item_value(function_call, "args") is not None else _item_value(function_call, "arguments"),
            }.items()
            if value is not None
        }
        thought_signature = _item_value(item, "thought_signature") or _item_value(item, "thoughtSignature")
        if thought_signature is not None:
            data["thought_signature_present"] = True
            data["thought_signature_sha256"] = _sha256_bytes(_coerce_signature_bytes(thought_signature))
            data["thought_signature_position"] = position
    function_response = _item_value(item, "function_response") or _item_value(item, "functionResponse")
    if function_response is not None:
        data["function_response"] = {
            key: value
            for key, value in {
                "call_id": _item_value(function_response, "id"),
                "name": _item_value(function_response, "name"),
                "output": _item_value(function_response, "response"),
            }.items()
            if value is not None
        }
    return data


def _sanitize_config(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    keys = ("system_instruction", "automatic_function_calling", "tools", "http_options", "temperature", "top_p", "max_output_tokens")
    data = {key: _item_value(value, key) for key in keys}
    return {key: val for key, val in data.items() if val is not None}


def _sanitize_response(response: Any) -> dict[str, Any]:
    return {
        "id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "status": getattr(response, "status", None),
        "usage": _mapping_or_none(getattr(response, "usage_metadata", None) or getattr(response, "usage", None)),
        "output": [_sanitize_output_item(item) for item in (getattr(response, "candidates", None) or [])],
    }


def _sanitize_output_item(item: Any) -> dict[str, Any]:
    data = {"type": getattr(item, "type", None)}
    content = getattr(item, "content", None)
    if content is not None:
        data["content"] = [_sanitize_part_item(part, position=index) for index, part in enumerate(getattr(content, "parts", None) or [])]
    return data


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _coerce_signature_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")


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


def _item_value(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        if key in item:
            return item[key]
        camel = _snake_to_camel(key)
        return item.get(camel)
    value = getattr(item, key, None)
    if value is not None:
        return value
    camel = _snake_to_camel(key)
    return getattr(item, camel, None)


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(piece.title() for piece in tail)


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
        f"- Provider usado: {summary.live_run.details.get('provider') if summary.live_run else 'missing'}",
        f"- Modelo usado: {summary.live_run.details.get('selected_model') if summary.live_run else 'missing'}",
        f"- PD_AGENT_MODEL env: {summary.live_run.details.get('env_model') if summary.live_run else 'missing'}",
        f"- GEMINI_API_KEY: {'present' if os.environ.get('GEMINI_API_KEY') else 'missing'}",
        f"- Fixture: {summary.candidate_root}",
        f"- Run id: {summary.live_run.details.get('run_id') if summary.live_run else 'n/a'}",
        f"- Source hash before: {summary.live_run.details.get('before_hash') if summary.live_run else 'n/a'}",
        f"- Source hash after: {summary.live_run.details.get('after_hash') if summary.live_run else 'n/a'}",
        f"- Source changed: {summary.live_run.details.get('source_changed') if summary.live_run else 'n/a'}",
        f"- Tool call count: {summary.live_run.details.get('tool_call_count') if summary.live_run else 'n/a'}",
        f"- Continuation detected: {summary.live_run.details.get('continuation', {}).get('continuation_detected') if summary.live_run else 'n/a'}",
        f"- Continuation replay: {summary.live_run.details.get('continuation', {}).get('replay_success') if summary.live_run else 'n/a'}",
        f"- Gradle result: {summary.live_run.reason if summary.live_run else 'n/a'}",
        f"- Artifact result: {summary.live_run.details.get('artifact') if summary.live_run else 'n/a'}",
        f"- Final state: {summary.live_run.details.get('final_state') if summary.live_run else 'n/a'}",
        f"- PASS evaluation: {summary.live_run.details.get('evaluation_passed') if summary.live_run else 'n/a'}",
        f"- Secret scan: {summary.live_run.details.get('secret_found') if summary.live_run else 'n/a'}",
        f"- Usage: {json.dumps(summary.live_run.details.get('usage'), ensure_ascii=False) if summary.live_run else 'n/a'}",
        "- OpenAI live: NOT RUN (blocked by billing)",
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
    print(f"Gemini live E2E: {_scenario_status(summary.live_run)}")
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
