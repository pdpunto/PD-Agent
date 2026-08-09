"""Validacion externa reproducible de PD Agent v0.1.

Este runner no implementa producto. Solo prepara y orquesta una validacion
externa sobre una copia temporal de un proyecto Fabric local real.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterator, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_ROOT = Path(r"C:\dev\proyectos\PD-Ecosystem")
DEFAULT_VALIDATION_ROOT = Path(tempfile.gettempdir()) / "pd-agent-v0.1-validation"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_PYTEST_TIMEOUT_SECONDS = 1800
DEFAULT_TASK = "Edita un string o log existente sin cambiar la arquitectura."

IGNORED_COPY_DIRS = {
    ".git",
    ".gradle",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    ".venv-l0fix",
    ".idea",
    ".vs",
    "runs",
    "validation_runs",
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
class ScenarioResult:
    name: str
    status: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationSummary:
    started_at: datetime
    finished_at: datetime | None = None
    candidate_root: Path | None = None
    validation_root: Path | None = None
    working_root: Path | None = None
    evidence_root: Path | None = None
    baseline_build: ScenarioResult | None = None
    acceptance_main: ScenarioResult | None = None
    repair: ScenarioResult | None = None
    security: ScenarioResult | None = None
    negative_artifact: ScenarioResult | None = None
    openai_live: ScenarioResult | None = None
    suite: ScenarioResult | None = None
    notes: list[str] = field(default_factory=list)

    def final_status(self) -> str:
        results = [
            self.baseline_build,
            self.acceptance_main,
            self.repair,
            self.security,
            self.negative_artifact,
            self.suite,
        ]
        if any(result is not None and result.status == "BLOCKED" for result in results):
            return "BLOCKED"
        if any(result is None or result.status != "PASS" for result in results):
            return "FAIL"
        if self.openai_live is not None and self.openai_live.status == "FAIL":
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
            "baseline_build": self._scenario_to_dict(self.baseline_build),
            "acceptance_main": self._scenario_to_dict(self.acceptance_main),
            "repair": self._scenario_to_dict(self.repair),
            "security": self._scenario_to_dict(self.security),
            "negative_artifact": self._scenario_to_dict(self.negative_artifact),
            "openai_live": self._scenario_to_dict(self.openai_live),
            "suite": self._scenario_to_dict(self.suite),
            "notes": list(self.notes),
            "final_status": self.final_status(),
        }

    def _scenario_to_dict(self, scenario: ScenarioResult | None) -> dict[str, Any] | None:
        if scenario is None:
            return None
        return {
            "name": scenario.name,
            "status": scenario.status,
            "reason": scenario.reason,
            "details": scenario.details,
        }


class ScenarioBlocked(RuntimeError):
    """Precheck o validacion bloqueada."""


class ScriptedProvider:
    """Provider fake determinista para el runtime real."""

    def __init__(self, responses: Sequence[Any]) -> None:
        self._responses = tuple(responses)
        self._index = 0

    def execute(self, request: Any) -> Any:  # noqa: ANN401 - interfaz provider
        if self._index < len(self._responses):
            response = self._responses[self._index]
            self._index += 1
            return response
        return self._responses[-1] if self._responses else _agent_response()


def _agent_response(message: str | None = None, tool_calls: Sequence[Any] = ()) -> Any:
    from pd_agent.core import AgentResponse

    return AgentResponse(assistant_message=message, tool_calls=tuple(tool_calls))


def _tool_call(call_id: str, tool_name: str, arguments: Mapping[str, Any]) -> Any:
    from pd_agent.core import ToolCall

    return ToolCall(call_id=call_id, tool_name=tool_name, arguments=dict(arguments))


def _scenario_result(name: str, status: str, reason: str, **details: Any) -> ScenarioResult:
    return ScenarioResult(name=name, status=status, reason=reason, details=dict(details))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_v0_1.py",
        description="Runner externo reproducible de validacion PD Agent v0.1.",
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=DEFAULT_CANDIDATE_ROOT,
        help="Proyecto Fabric real base.",
    )
    parser.add_argument(
        "--validation-root",
        type=Path,
        default=DEFAULT_VALIDATION_ROOT,
        help="Directorio raiz de evidencia y temporales.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Timeout por probe principal de build.",
    )
    parser.add_argument(
        "--pytest-timeout-seconds",
        type=int,
        default=DEFAULT_PYTEST_TIMEOUT_SECONDS,
        help="Timeout para la suite completa.",
    )
    parser.add_argument(
        "--keep-working-copy",
        action="store_true",
        help="No borrar la copia temporal de trabajo al final.",
    )
    parser.add_argument(
        "--skip-openai-live",
        action="store_true",
        help="No ejecutar el smoke live aunque exista OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--task",
        default=DEFAULT_TASK,
        help="Tarea pequena para la acceptance principal.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    summary = ValidationSummary(
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
        summary.acceptance_main = _run_acceptance_main(summary, args)
        summary.repair = _run_repair_scenario(summary, args)
        summary.security = _run_security_scenario(summary, args)
        summary.negative_artifact = _run_negative_artifact(summary, args)
        summary.openai_live = _run_openai_live(summary, args)
        summary.suite = _run_suite(summary, args)
    except ScenarioBlocked as exc:
        _record_note(summary, f"BLOCKED: {exc}")
        _finalize(summary)
        _write_artifacts(summary)
        _print_summary(summary)
        _cleanup(summary, keep_working_copy=args.keep_working_copy)
        return 2
    except Exception as exc:  # pragma: no cover - safety net
        _record_note(summary, f"FAIL: {type(exc).__name__}: {exc}")
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


def _run_prechecks(summary: ValidationSummary, args: argparse.Namespace) -> None:
    if sys.version_info < (3, 13):
        raise ScenarioBlocked("Python >= 3.13 requerido")
    _check_pd_agent_import()
    _check_git_clean(REPO_ROOT)
    _check_java()
    candidate = args.candidate_root.resolve()
    if not candidate.exists():
        raise ScenarioBlocked(f"no existe candidate root: {candidate}")
    wrapper = candidate / "gradlew.bat"
    if not wrapper.exists():
        raise ScenarioBlocked(f"falta gradlew.bat en: {candidate}")
    summary.notes.append("prechecks: ok")


def _check_pd_agent_import() -> None:
    try:
        __import__("pd_agent")
    except Exception as exc:  # pragma: no cover - environment issue
        raise ScenarioBlocked(f"pd_agent no importable: {exc}") from exc


def _check_java() -> None:
    result = _run_command(["java", "-version"], cwd=REPO_ROOT, timeout_seconds=30)
    text = "\n".join(filter(None, [result.stdout, result.stderr]))
    if "version \"21" not in text and " version \"21" not in text:
        raise ScenarioBlocked(f"Java 21 requerido, visto: {text.strip()}")


def _check_git_clean(root: Path) -> None:
    result = _run_command(["git", "status", "--short"], cwd=root, timeout_seconds=30)
    if result.timed_out:
        raise ScenarioBlocked("git status timeout")
    if result.exit_code != 0:
        raise ScenarioBlocked("git status fallo")
    if result.stdout.strip():
        raise ScenarioBlocked("working tree sucio")


def _run_baseline_build(summary: ValidationSummary, args: argparse.Namespace) -> ScenarioResult:
    work_root = _prepare_working_copy(summary, suffix="baseline")
    command = _gradle_build_command(work_root, ["build", "--no-daemon"])
    result = _run_command(command, cwd=work_root, timeout_seconds=args.timeout_seconds)
    _write_command_evidence(summary, "baseline-build", result)
    if result.timed_out:
        return _scenario_result("Baseline Fabric build", "BLOCKED", "timeout", command=" ".join(command))
    if result.exit_code != 0:
        return _scenario_result(
            "Baseline Fabric build",
            "FAIL",
            "build failed",
            command=" ".join(command),
            stdout_tail=_tail(result.stdout),
            stderr_tail=_tail(result.stderr),
        )
    return _scenario_result("Baseline Fabric build", "PASS", "build successful", command=" ".join(command))


def _run_acceptance_main(summary: ValidationSummary, args: argparse.Namespace) -> ScenarioResult:
    work_root = _prepare_working_copy(summary, suffix="acceptance")
    from pd_agent import ArtifactValidator, GradleBuildRunner, ProjectInspector, RunStorage
    from pd_agent.config import ExecutionLimits
    from pd_agent.context import ContextManager
    from pd_agent.core import AgentMessage, AgentRequest
    from pd_agent.pass_policy import evaluate_pass
    from pd_agent.reporting import FinalReport
    from pd_agent.runtime import RunController

    target = _pick_markdown_target(work_root)
    original = target.read_text(encoding="utf-8")
    modified = _append_marker(original, "Validation note: external L11 runner.")
    provider = ScriptedProvider(
        [
            _agent_response(
                "Edito un string existente y sigo con build real.",
                [
                    _tool_call(
                        "call-1",
                        "write_file",
                        {"path": str(target.relative_to(work_root)), "content": modified},
                    )
                ],
            )
        ]
    )
    storage = RunStorage(summary.evidence_root / "acceptance-main")
    controller = RunController(
        provider=provider,
        storage=storage,
        build_runner=GradleBuildRunner(reporting=storage),
        artifact_validator=ArtifactValidator(reporting=storage),
        context_manager=ContextManager(),
        limits=ExecutionLimits(),
        project_inspector=ProjectInspector(),
    )
    with _temp_env(GRADLE_USER_HOME=str(summary.validation_root / "gradle-home-acceptance")):
        run_state, report = controller.run(work_root, args.task)
    evaluation = evaluate_pass(storage, run_state.run_id)
    _write_json(summary.evidence_root / "acceptance-main" / "evaluation.json", {
        "run_state": run_state.to_dict(),
        "report": report.to_dict(),
        "evaluation": {
            "passed": evaluation.passed,
            "reason": evaluation.reason,
        },
    })
    if evaluation.passed and report.final_state.value == "COMPLETED":
        return _scenario_result(
            "Fake provider + real Gradle",
            "PASS",
            "completed",
            run_id=run_state.run_id,
            report=str(storage.paths_for(run_state.run_id).final_report_json),
        )
    return _scenario_result(
        "Fake provider + real Gradle",
        "FAIL",
        evaluation.reason,
        run_id=run_state.run_id,
        final_state=run_state.state.value,
    )


def _run_repair_scenario(summary: ValidationSummary, args: argparse.Namespace) -> ScenarioResult:
    work_root = _prepare_working_copy(summary, suffix="repair")
    source = _pick_source_target(work_root)
    original = source.read_text(encoding="utf-8")
    broken = "BROKEN_SYNTAX\n" + original
    provider = ScriptedProvider(
        [
            _agent_response(
                "Rompo y luego reparo.",
                [
                    _tool_call(
                        "call-1",
                        "write_file",
                        {"path": str(source.relative_to(work_root)), "content": broken},
                    )
                ],
            ),
            _agent_response(
                "Corrijo el archivo roto.",
                [
                    _tool_call(
                        "call-2",
                        "write_file",
                        {"path": str(source.relative_to(work_root)), "content": original},
                    )
                ],
            ),
            _agent_response("Termino sin mas herramientas.", ()),
        ]
    )
    from pd_agent import ArtifactValidator, GradleBuildRunner, ProjectInspector, RunStorage
    from pd_agent.config import ExecutionLimits
    from pd_agent.context import ContextManager
    from pd_agent.pass_policy import evaluate_pass
    from pd_agent.runtime import RunController

    storage = RunStorage(summary.evidence_root / "repair")
    controller = RunController(
        provider=provider,
        storage=storage,
        build_runner=GradleBuildRunner(reporting=storage),
        artifact_validator=ArtifactValidator(reporting=storage),
        context_manager=ContextManager(),
        limits=ExecutionLimits(),
        project_inspector=ProjectInspector(),
    )
    with _temp_env(GRADLE_USER_HOME=str(summary.validation_root / "gradle-home-repair")):
        run_state, report = controller.run(work_root, "Repair controlled compile break")
    evaluation = evaluate_pass(storage, run_state.run_id)
    _write_json(summary.evidence_root / "repair" / "evaluation.json", {
        "run_state": run_state.to_dict(),
        "report": report.to_dict(),
        "evaluation": {
            "passed": evaluation.passed,
            "reason": evaluation.reason,
        },
    })
    if evaluation.passed and report.final_state.value == "COMPLETED":
        return _scenario_result(
            "Repair scenario",
            "PASS",
            "repair succeeded",
            run_id=run_state.run_id,
        )
    return _scenario_result(
        "Repair scenario",
        "FAIL",
        evaluation.reason,
        run_id=run_state.run_id,
        final_state=run_state.state.value,
    )


def _run_security_scenario(summary: ValidationSummary, args: argparse.Namespace) -> ScenarioResult:
    work_root = _prepare_working_copy(summary, suffix="security")
    provider = ScriptedProvider(
        [
            _agent_response(
                "Intento salir del root y espero rechazo.",
                [
                    _tool_call(
                        "call-1",
                        "write_file",
                        {"path": r"..\outside.txt", "content": "nope"},
                    )
                ],
            )
        ]
    )
    from pd_agent import ArtifactValidator, GradleBuildRunner, ProjectInspector, RunStorage
    from pd_agent.config import ExecutionLimits
    from pd_agent.context import ContextManager
    from pd_agent.runtime import RunController

    storage = RunStorage(summary.evidence_root / "security")
    controller = RunController(
        provider=provider,
        storage=storage,
        build_runner=GradleBuildRunner(reporting=storage),
        artifact_validator=ArtifactValidator(reporting=storage),
        context_manager=ContextManager(),
        limits=ExecutionLimits(max_build_attempts=1),
        project_inspector=ProjectInspector(),
    )
    with _temp_env(GRADLE_USER_HOME=str(summary.validation_root / "gradle-home-security")):
        run_state, report = controller.run(work_root, "Security boundary check")
    _write_json(summary.evidence_root / "security" / "evaluation.json", {
        "run_state": run_state.to_dict(),
        "report": report.to_dict(),
    })
    if run_state.state.value == "FAILED" and run_state.termination_reason == "tool rejected":
        return _scenario_result(
            "Security scenario",
            "PASS",
            "outside write rejected",
            run_id=run_state.run_id,
        )
    return _scenario_result(
        "Security scenario",
        "FAIL",
        "boundary not enforced",
        run_id=run_state.run_id,
        final_state=run_state.state.value,
    )


def _run_negative_artifact(summary: ValidationSummary, args: argparse.Namespace) -> ScenarioResult:
    work_root = _prepare_working_copy(summary, suffix="negative-artifact")
    from pd_agent import ArtifactValidator, GradleBuildRunner, ProjectInspector, RunStorage
    from pd_agent.config import ExecutionLimits
    from pd_agent.core import RunState
    from pd_agent.context import ContextManager

    storage = RunStorage(summary.evidence_root / "negative-artifact")
    inspector = ProjectInspector()
    snapshot = inspector.inspect(work_root)
    state = RunState(project_root=work_root, task="Negative artifact check")
    with _temp_env(GRADLE_USER_HOME=str(summary.validation_root / "gradle-home-negative")):
        build = GradleBuildRunner(reporting=storage).run(snapshot, state, ExecutionLimits())
    jars = tuple((work_root / "build" / "libs").glob("*.jar"))
    for jar in jars:
        jar.unlink()
    artifact = ArtifactValidator(reporting=storage).validate(snapshot, build, run_id=state.run_id)
    _write_json(summary.evidence_root / "negative-artifact" / "evaluation.json", {
        "build": build.to_dict(),
        "artifact": artifact.to_dict(),
    })
    if artifact.classification != "VALID":
        return _scenario_result(
            "Negative artifact",
            "PASS",
            "invalid or missing artifact detected",
            classification=artifact.classification,
        )
    return _scenario_result(
        "Negative artifact",
        "FAIL",
        "artifact unexpectedly valid",
        classification=artifact.classification,
    )


def _run_openai_live(summary: ValidationSummary, args: argparse.Namespace) -> ScenarioResult:
    if args.skip_openai_live:
        return _scenario_result("OpenAI live", "NOT RUN", "skipped by flag")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _scenario_result("OpenAI live", "NOT RUN", "OPENAI_API_KEY missing")
    model = os.environ.get("PD_AGENT_MODEL", "gpt-4.1-mini")
    from pd_agent.core import AgentMessage, AgentRequest
    from pd_agent.providers import OpenAIProvider

    provider = OpenAIProvider(model=model, api_key=api_key, provider_retry_limit=0)
    request = AgentRequest(messages=(AgentMessage(role="user", content="Respond with OK."),))
    response = provider.execute(request)
    _write_json(summary.evidence_root / "openai-live" / "response.json", response.to_dict())
    return _scenario_result(
        "OpenAI live",
        "PASS" if response.assistant_message is not None else "FAIL",
        "provider responded",
        model=model,
    )


def _run_suite(summary: ValidationSummary, args: argparse.Namespace) -> ScenarioResult:
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    result = _run_command(command, cwd=REPO_ROOT, timeout_seconds=args.pytest_timeout_seconds)
    _write_command_evidence(summary, "pytest-suite", result)
    if result.timed_out:
        return _scenario_result(
            "Suite PD Agent",
            "BLOCKED",
            "pytest timeout",
            command=" ".join(command),
        )
    if result.exit_code == 0:
        return _scenario_result(
            "Suite PD Agent",
            "PASS",
            "pytest passed",
            command=" ".join(command),
        )
    return _scenario_result(
        "Suite PD Agent",
        "FAIL",
        "pytest failed",
        command=" ".join(command),
        stdout_tail=_tail(result.stdout),
        stderr_tail=_tail(result.stderr),
    )


def _prepare_working_copy(summary: ValidationSummary, *, suffix: str) -> Path:
    candidate = summary.candidate_root
    if candidate is None:
        raise ScenarioBlocked("candidate root missing")
    work_root = summary.working_root / suffix
    if work_root.exists():
        shutil.rmtree(work_root)
    shutil.copytree(candidate, work_root, ignore=shutil.ignore_patterns(*IGNORED_COPY_DIRS))
    return work_root


def _pick_markdown_target(root: Path) -> Path:
    preferred = [root / "README.md", *root.rglob("*.md")]
    for path in preferred:
        if path.is_file():
            return path
    raise ScenarioBlocked("no markdown target found")


def _pick_source_target(root: Path) -> Path:
    for pattern in ("*.java", "*.kt", "*.kts"):
        for path in root.rglob(pattern):
            if any(part in IGNORED_COPY_DIRS for part in path.parts):
                continue
            if path.is_file():
                return path
    raise ScenarioBlocked("no source target found")


def _append_marker(text: str, marker: str) -> str:
    if marker in text:
        return text
    if text.endswith("\n"):
        return text + f"\n{marker}\n"
    return text + f"\n\n{marker}\n"


def _gradle_build_command(project_root: Path, args: Sequence[str]) -> list[str]:
    wrapper = project_root / "gradlew.bat"
    return ["cmd", "/c", str(wrapper), *args]


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    extra_env: Mapping[str, str] | None = None,
) -> CommandResult:
    started = datetime.now(timezone.utc)
    env = os.environ.copy()
    if extra_env:
        env.update({key: str(value) for key, value in extra_env.items()})
    proc = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(proc.pid)
        stdout, stderr = proc.communicate() if proc.poll() is not None else ("", "")
    finished = datetime.now(timezone.utc)
    return CommandResult(
        command=tuple(command),
        cwd=cwd,
        exit_code=proc.returncode,
        timed_out=timed_out,
        stdout=stdout or "",
        stderr=stderr or "",
        duration_seconds=max((finished - started).total_seconds(), 0.0),
    )


def _kill_process_tree(pid: int) -> None:
    if platform.system().lower().startswith("win"):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        return
    try:
        os.kill(pid, 9)
    except OSError:
        pass


@contextmanager
def _temp_env(**changes: str) -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in changes}
    try:
        for key, value in changes.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _write_command_evidence(summary: ValidationSummary, name: str, result: CommandResult) -> None:
    payload = {
        "command": list(result.command),
        "cwd": str(result.cwd),
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_seconds": result.duration_seconds,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    _write_json(summary.evidence_root / f"{name}.json", payload)


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _tail(text: str, lines: int = 40) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def _record_note(summary: ValidationSummary, note: str) -> None:
    summary.notes.append(note)


def _finalize(summary: ValidationSummary) -> None:
    summary.finished_at = datetime.now(timezone.utc)


def _write_artifacts(summary: ValidationSummary) -> None:
    assert summary.evidence_root is not None
    _write_json(summary.evidence_root / "summary.json", summary.to_dict())
    summary.evidence_root.joinpath("summary.md").write_text(_summary_markdown(summary), encoding="utf-8")


def _summary_markdown(summary: ValidationSummary) -> str:
    lines = [
        "# L11 Validation",
        "",
        f"- Candidate root: `{summary.candidate_root}`",
        f"- Validation root: `{summary.validation_root}`",
        f"- Working root: `{summary.working_root}`",
        f"- Final status: `{summary.final_status()}`",
        "",
        "## Scenarios",
    ]
    for item in (
        summary.baseline_build,
        summary.acceptance_main,
        summary.repair,
        summary.security,
        summary.negative_artifact,
        summary.openai_live,
        summary.suite,
    ):
        if item is None:
            continue
        lines.append(f"- {item.name}: {item.status} - {item.reason}")
    if summary.notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in summary.notes)
    return "\n".join(lines) + "\n"


def _print_summary(summary: ValidationSummary) -> None:
    print("L11 VALIDATION")
    print()
    print(f"Baseline Fabric build: {_scenario_status(summary.baseline_build)}")
    print(f"Fake provider + real Gradle: {_scenario_status(summary.acceptance_main)}")
    print(f"Repair scenario: {_scenario_status(summary.repair)}")
    print(f"Security scenario: {_scenario_status(summary.security)}")
    print(f"Negative artifact: {_scenario_status(summary.negative_artifact)}")
    print(f"OpenAI live: {_openai_status(summary.openai_live)}")
    print(f"Suite PD Agent: {_scenario_status(summary.suite)}")
    print()
    print(f"FINAL: {summary.final_status()}")
    print(f"Evidence: {summary.evidence_root}")


def _cleanup(summary: ValidationSummary, *, keep_working_copy: bool) -> None:
    if keep_working_copy:
        return
    if summary.working_root and summary.working_root.exists():
        shutil.rmtree(summary.working_root, ignore_errors=True)
    if summary.validation_root and summary.validation_root.exists():
        for path in summary.validation_root.glob("gradle-home-*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


def _scenario_status(item: ScenarioResult | None) -> str:
    if item is None:
        return "NOT RUN"
    return item.status


def _openai_status(item: ScenarioResult | None) -> str:
    if item is None:
        return "NOT RUN"
    return item.status


if __name__ == "__main__":
    raise SystemExit(main())
