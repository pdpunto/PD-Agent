"""Validacion externa reproducible de PD Agent v0.3."""

from __future__ import annotations

import argparse
import difflib
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Iterator, Mapping, Sequence

import validate_v0_1 as base
from pd_agent import ArtifactValidator, FileKnowledgeCache, GradleBuildRunner, MinecraftBrain, ProjectInspector, YarnKnowledgeSource
from pd_agent.brain import KnowledgeEnvironmentResolver, KnowledgeNeed, KnowledgeType
from pd_agent.config import ExecutionLimits
from pd_agent.context import ContextManager
from pd_agent.minecraft import MinecraftTestRunner, MinecraftTestSpec
from pd_agent.pass_policy import evaluate_pass
from pd_agent.providers import GeminiProvider
from pd_agent.reporting import RunStorage
from pd_agent.runtime import RunController


REPO_ROOT = base.REPO_ROOT
DEFAULT_CANDIDATE_ROOT = base.DEFAULT_CANDIDATE_ROOT
DEFAULT_HARNESS_ROOT = REPO_ROOT / "tests" / "fixtures" / "l11_minecraft_harness"
DEFAULT_VALIDATION_ROOT = Path(base.tempfile.gettempdir()) / "pd-agent-v0.3-validation"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_PYTEST_TIMEOUT_SECONDS = 1800
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_TASK = (
    "Convierte src/main/java/dev/pdpunto/l11/ExampleMod.java para resolver el bloque de prueba por registro "
    "usando la API exacta de Minecraft 1.21.11 (identificador + registro vanilla), sin cambiar el "
    "comportamiento observable del harness. El archivo ahora contiene "
    "private static final BlockState PROBE_STATE = Blocks.DIAMOND_BLOCK.getDefaultState(); "
    "y ese acceso directo debe ser reemplazado por la solución de registro generada por el agente."
)
DEFAULT_TARGET_MOD_ID = "pdagentl11"
DEFAULT_MINECRAFT_VERSION = "1.21.11"
DEFAULT_LOADER_VERSION = "0.19.3"
DEFAULT_TEST_ID = "block_state_probe"
WORKSPACE_TARGET_ROOT = Path("tests/fixtures/l11_fabric_fixture")
WORKSPACE_HARNESS_ROOT = Path("tests/fixtures/l11_minecraft_harness")
WORKSPACE_TARGET_JAR = Path("build/libs/pd-agent-l11-fixture.jar")
IGNORED_COPY_DIRS = tuple(sorted(name for name in base.IGNORED_COPY_DIRS if name != ".gradle"))


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


@dataclass(slots=True)
class ValidationSummary:
    started_at: datetime
    finished_at: datetime | None = None
    candidate_root: Path | None = None
    validation_root: Path | None = None
    working_root: Path | None = None
    target_root: Path | None = None
    harness_root: Path | None = None
    evidence_root: Path | None = None
    repository_commit: str | None = None
    environment_resolution: base.ScenarioResult | None = None
    brain_retrieval: base.ScenarioResult | None = None
    knowledge_result: Any | None = None
    baseline_target_build: base.ScenarioResult | None = None
    baseline_harness_build: base.ScenarioResult | None = None
    brain_off_acceptance: base.ScenarioResult | None = None
    acceptance_main: base.ScenarioResult | None = None
    comparison: base.ScenarioResult | None = None
    minecraft_runtime: base.ScenarioResult | None = None
    suite: base.ScenarioResult | None = None
    accepted_target_root: Path | None = None
    accepted_harness_root: Path | None = None
    notes: list[str] = field(default_factory=list)

    def final_status(self) -> str:
        results = [
            self.environment_resolution,
            self.brain_retrieval,
            self.baseline_target_build,
            self.baseline_harness_build,
            self.comparison,
            self.acceptance_main,
            self.minecraft_runtime,
            self.suite,
        ]
        if any(result is not None and result.status == "BLOCKED" for result in results):
            return "BLOCKED"
        if any(result is None or result.status != "PASS" for result in results):
            return "FAIL"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "candidate_root": str(self.candidate_root) if self.candidate_root else None,
            "validation_root": str(self.validation_root) if self.validation_root else None,
            "working_root": str(self.working_root) if self.working_root else None,
            "target_root": str(self.target_root) if self.target_root else None,
            "harness_root": str(self.harness_root) if self.harness_root else None,
            "evidence_root": str(self.evidence_root) if self.evidence_root else None,
            "repository_commit": self.repository_commit,
            "environment_resolution": _scenario_to_dict(self.environment_resolution),
            "brain_retrieval": _scenario_to_dict(self.brain_retrieval),
            "baseline_target_build": _scenario_to_dict(self.baseline_target_build),
            "baseline_harness_build": _scenario_to_dict(self.baseline_harness_build),
            "brain_off_acceptance": _scenario_to_dict(self.brain_off_acceptance),
            "acceptance_main": _scenario_to_dict(self.acceptance_main),
            "comparison": _scenario_to_dict(self.comparison),
            "minecraft_runtime": _scenario_to_dict(self.minecraft_runtime),
            "suite": _scenario_to_dict(self.suite),
            "accepted_target_root": str(self.accepted_target_root) if self.accepted_target_root else None,
            "accepted_harness_root": str(self.accepted_harness_root) if self.accepted_harness_root else None,
            "notes": list(self.notes),
            "final_status": self.final_status(),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_v0_3.py",
        description="Runner externo reproducible de validacion PD Agent v0.3.",
    )
    parser.add_argument("--candidate-root", type=Path, default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--validation-root", type=Path, default=DEFAULT_VALIDATION_ROOT)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--pytest-timeout-seconds", type=int, default=DEFAULT_PYTEST_TIMEOUT_SECONDS)
    parser.add_argument("--brain-off", action="store_true", help="Run only the Brain OFF comparison case")
    parser.add_argument("--brain-on", action="store_true", help="Run only the Brain ON acceptance case")
    parser.add_argument("--keep-working-copy", action="store_true")
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
        _prepare_workspace(summary)
        _seed_gradle_home(summary)
        summary.environment_resolution = _resolve_environment(summary)
        if summary.environment_resolution.status != "PASS":
            raise base.ScenarioBlocked(summary.environment_resolution.reason)
        knowledge = _run_brain_retrieval(summary)
        summary.brain_retrieval = knowledge
        summary.baseline_target_build = _run_gradle_build(summary.target_root, args.timeout_seconds, summary.validation_root / "gradle-home")
        if summary.baseline_target_build.status != "PASS":
            raise base.ScenarioBlocked(f"target build failed: {summary.baseline_target_build.reason}")
        summary.baseline_harness_build = _run_gradle_build(summary.harness_root, args.timeout_seconds, summary.validation_root / "gradle-home")
        if summary.baseline_harness_build.status != "PASS":
            raise base.ScenarioBlocked(f"harness build failed: {summary.baseline_harness_build.reason}")
        run_brain_off = args.brain_off or not args.brain_on
        run_brain_on = args.brain_on or not args.brain_off
        if run_brain_off:
            summary.brain_off_acceptance = _run_acceptance_case(
                summary,
                args,
                knowledge,
                case_name="brain-off",
                brain_enabled=False,
            )
        else:
            summary.brain_off_acceptance = _scenario_result("Brain OFF comparison", "NOT RUN", "not requested")
        if run_brain_on:
            summary.acceptance_main = _run_acceptance_case(
                summary,
                args,
                knowledge,
                case_name="brain-on",
                brain_enabled=True,
            )
        else:
            summary.acceptance_main = _scenario_result("Brain ON acceptance", "NOT RUN", "not requested")
        summary.comparison = _run_comparison(summary, run_brain_off=run_brain_off, run_brain_on=run_brain_on)
        summary.minecraft_runtime = _run_minecraft_runtime(summary)
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


def _run_prechecks(summary: ValidationSummary, args: argparse.Namespace) -> None:
    if base.sys.version_info < (3, 13):
        raise base.ScenarioBlocked("Python >= 3.13 requerido")
    base._check_pd_agent_import()
    base._check_java()
    base._check_git_clean(REPO_ROOT)
    head = base._run_command(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, timeout_seconds=30)
    origin = base._run_command(["git", "rev-parse", "origin/main"], cwd=REPO_ROOT, timeout_seconds=30)
    if head.timed_out or origin.timed_out or head.exit_code != 0 or origin.exit_code != 0:
        raise base.ScenarioBlocked("git rev-parse failed")
    if head.stdout.strip() != origin.stdout.strip():
        raise base.ScenarioBlocked("HEAD != origin/main")
    if not args.candidate_root.resolve().exists():
        raise base.ScenarioBlocked(f"no existe candidate root: {args.candidate_root.resolve()}")
    if not DEFAULT_HARNESS_ROOT.exists():
        raise base.ScenarioBlocked(f"falta harness root: {DEFAULT_HARNESS_ROOT}")
    summary.repository_commit = head.stdout.strip()
    summary.notes.append("prechecks: ok")
    summary.notes.append(f"head: {head.stdout.strip()}")
    summary.notes.append(f"origin/main: {origin.stdout.strip()}")


def _prepare_workspace(summary: ValidationSummary) -> None:
    if summary.working_root is None or summary.candidate_root is None:
        raise base.ScenarioBlocked("workspace not initialized")
    if summary.working_root.exists():
        shutil.rmtree(summary.working_root)
    summary.working_root.mkdir(parents=True, exist_ok=True)
    summary.target_root = summary.working_root / WORKSPACE_TARGET_ROOT
    summary.harness_root = summary.working_root / WORKSPACE_HARNESS_ROOT
    shutil.copytree(
        summary.candidate_root,
        summary.target_root,
        ignore=shutil.ignore_patterns(*IGNORED_COPY_DIRS),
    )
    shutil.copytree(
        DEFAULT_HARNESS_ROOT,
        summary.harness_root,
        ignore=shutil.ignore_patterns(*IGNORED_COPY_DIRS),
    )


def _seed_gradle_home(summary: ValidationSummary) -> None:
    if summary.validation_root is None or summary.target_root is None:
        raise base.ScenarioBlocked("workspace not initialized")
    gradle_home = summary.validation_root / "gradle-home"
    gradle_home.mkdir(parents=True, exist_ok=True)
    base._seed_gradle_home(summary.target_root, gradle_home)


def _resolve_environment(summary: ValidationSummary) -> base.ScenarioResult:
    if summary.target_root is None:
        raise base.ScenarioBlocked("target root missing")
    resolution = KnowledgeEnvironmentResolver().resolve(summary.target_root)
    details = {
        "resolution_status": resolution.status.value,
        "environment": resolution.environment.to_dict(),
        "evidence": list(resolution.evidence),
        "conflicts": list(resolution.conflicts),
    }
    _write_json(summary.evidence_root / "environment.json", details)
    if resolution.status.value == "DETECTED":
        return _scenario_result("Environment resolution", "PASS", "detected", **details)
    if resolution.status.value == "CONFLICT":
        return _scenario_result("Environment resolution", "BLOCKED", "environment conflict", **details)
    return _scenario_result("Environment resolution", "BLOCKED", "environment unknown", **details)


def _build_knowledge_need(summary: ValidationSummary) -> KnowledgeNeed:
    if summary.environment_resolution is None:
        raise base.ScenarioBlocked("environment missing")
    env = KnowledgeEnvironmentResolver().resolve(summary.target_root).environment if summary.target_root else None
    if env is None:
        raise base.ScenarioBlocked("environment unavailable")
    return KnowledgeNeed(
        id="l4-block-registry-lookup",
        type=KnowledgeType.SYMBOL,
        query="Identifier Registries Block registry lookup",
        environment=env,
        hints=("Identifier", "Registries", "Block registry lookup"),
    )


def _run_brain_retrieval(summary: ValidationSummary) -> base.ScenarioResult:
    if summary.validation_root is None:
        raise base.ScenarioBlocked("validation root missing")
    need = _build_knowledge_need(summary)
    source = YarnKnowledgeSource()
    cache_root = summary.validation_root / "brain-cache"
    brain = MinecraftBrain(source=source, cache=FileKnowledgeCache(cache_root))
    result = brain.retrieve(need)
    details = {
        "need": need.to_dict(),
        "retrieval_status": result.status.value,
        "cache_hit": result.cache_hit,
        "offline": result.offline,
        "error": result.error,
        "artifact_coordinate": source.artifact_coordinate,
        "artifact_url": source.artifact_url,
        "artifact_checksum": source.artifact_checksum,
        "retrieved_item_ids": [item.id for item in result.items],
        "source_results": [source_result.to_dict() for source_result in result.source_results],
        "provenance": [item.provenance.to_dict() for item in result.items[:1]],
        "raw_result": result.to_dict(),
    }
    _write_json(summary.evidence_root / "knowledge.json", details)
    summary.knowledge_result = result
    if result.status == result.status.SUCCESS and result.items:
        return _scenario_result("Brain retrieval", "PASS", "retrieved", **details)
    return _scenario_result("Brain retrieval", "FAIL", result.error or "retrieval failed", **details)


def _run_acceptance_main(
    summary: ValidationSummary,
    args: argparse.Namespace,
    knowledge: base.ScenarioResult,
) -> base.ScenarioResult:
    return _run_acceptance_case(summary, args, knowledge, case_name="brain-on", brain_enabled=True)


def _prepare_acceptance_workspace(summary: ValidationSummary, case_name: str) -> tuple[Path, Path]:
    if summary.working_root is None or summary.candidate_root is None:
        raise base.ScenarioBlocked("workspace missing")
    case_root = summary.working_root / case_name
    target_root = case_root / WORKSPACE_TARGET_ROOT
    harness_root = case_root / WORKSPACE_HARNESS_ROOT
    if case_root.exists():
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        summary.candidate_root,
        target_root,
        ignore=shutil.ignore_patterns(*IGNORED_COPY_DIRS),
    )
    shutil.copytree(
        DEFAULT_HARNESS_ROOT,
        harness_root,
        ignore=shutil.ignore_patterns(*IGNORED_COPY_DIRS),
    )
    return target_root, harness_root


def _run_acceptance_case(
    summary: ValidationSummary,
    args: argparse.Namespace,
    knowledge: base.ScenarioResult,
    *,
    case_name: str,
    brain_enabled: bool,
) -> base.ScenarioResult:
    if summary.target_root is None or summary.validation_root is None or summary.evidence_root is None:
        raise base.ScenarioBlocked("workspace missing")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        details = {"provider": "gemini", "model": DEFAULT_GEMINI_MODEL, "block_reason": "GEMINI_API_KEY missing", "brain_enabled": brain_enabled}
        _write_json(summary.evidence_root / f"{case_name}-provider.json", details)
        return _scenario_result(
            "Brain ON acceptance" if brain_enabled else "Brain OFF comparison",
            "BLOCKED",
            "GEMINI_API_KEY missing",
            **details,
        )

    provider = GeminiProvider(model=DEFAULT_GEMINI_MODEL, api_key=api_key, provider_retry_limit=1)
    recording_client = RecordingGeminiClient(provider._client)  # noqa: SLF001
    provider._client = recording_client  # noqa: SLF001
    target_root, harness_root = _prepare_acceptance_workspace(summary, case_name)
    if brain_enabled:
        summary.accepted_target_root = target_root
        summary.accepted_harness_root = harness_root
    storage = RunStorage(summary.evidence_root / "acceptance" / case_name)
    controller = RunController(
        provider=provider,
        storage=storage,
        build_runner=GradleBuildRunner(reporting=storage),
        artifact_validator=ArtifactValidator(reporting=storage),
        context_manager=ContextManager(),
        project_inspector=ProjectInspector(),
        limits=ExecutionLimits(max_agent_steps=24, max_tool_calls=24, max_build_attempts=2, provider_retry_limit=1),
    )
    gradle_home = summary.validation_root / "gradle-home"
    task = DEFAULT_TASK
    source_path = target_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"
    before_text = source_path.read_text(encoding="utf-8")
    with _temp_env(GRADLE_USER_HOME=str(gradle_home)):
        run_state, report = controller.run(
            target_root,
            task,
            external_context=(summary.knowledge_result,) if brain_enabled else (),
        )
    evaluation = evaluate_pass(storage, run_state.run_id)
    after_text = source_path.read_text(encoding="utf-8")
    before_hash = _sha256_text(before_text)
    after_hash = _sha256_text(after_text)
    source_changed = before_hash != after_hash
    before_contains_direct_block = "Blocks.DIAMOND_BLOCK" in before_text
    after_contains_registry_lookup = _contains_registry_lookup(after_text)
    diff_text = "\n".join(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile="before/ExampleMod.java",
            tofile="after/ExampleMod.java",
            lineterm="",
        )
    )
    provider_details = {
        "provider": "gemini",
        "model": DEFAULT_GEMINI_MODEL,
        "brain_enabled": brain_enabled,
        "external_context_count": 1 if brain_enabled else 0,
        "request_count": len(recording_client.calls),
        "tool_call_count": run_state.tool_call_count,
        "continuation_count": sum(1 for call in recording_client.calls if call.request.get("tool_calls")),
    }
    code_details = {
        "workspace_root": str(target_root.parents[3]),
        "target_root": str(target_root),
        "harness_root": str(harness_root),
        "source_path": str(source_path.relative_to(target_root)),
        "before_hash": before_hash,
        "after_hash": after_hash,
        "source_changed": source_changed,
        "before_contains_direct_block": before_contains_direct_block,
        "after_contains_registry_lookup": after_contains_registry_lookup,
        "before_excerpt": _source_excerpt(before_text, "Blocks.DIAMOND_BLOCK"),
        "after_excerpt": _source_excerpt(after_text, "Registries.BLOCK"),
        "diff": diff_text,
    }
    build_details = {
        "run_id": run_state.run_id,
        "final_state": run_state.state.value,
        "termination_reason": run_state.termination_reason,
        "evaluate_pass": evaluation.passed,
        "evaluate_reason": evaluation.reason,
        "report_artifact": report.artifact.to_dict() if report.artifact else None,
        "report_final_build": report.final_build.to_dict() if report.final_build else None,
        "evidence_refs": list(report.evidence_refs),
    }
    _write_json(summary.evidence_root / case_name / "provider.json", provider_details)
    _write_json(summary.evidence_root / case_name / "code.json", code_details)
    _write_json(summary.evidence_root / case_name / "build.json", build_details)
    if (
        run_state.state.value == "COMPLETED"
        and evaluation.passed
        and report.final_build is not None
        and report.final_build.success
        and report.artifact is not None
        and report.artifact.classification == "VALID"
        and source_changed
        and before_contains_direct_block
        and after_contains_registry_lookup
    ):
        return _scenario_result(
            "Brain ON acceptance" if brain_enabled else "Brain OFF comparison",
            "PASS",
            "completed" if brain_enabled else "compared",
            **{**provider_details, **code_details, **build_details},
        )
    return _scenario_result(
        "Brain ON acceptance" if brain_enabled else "Brain OFF comparison",
        "FAIL",
        evaluation.reason if not source_changed else "acceptance failed",
        **{**provider_details, **code_details, **build_details},
    )


def _run_comparison(
    summary: ValidationSummary,
    *,
    run_brain_off: bool,
    run_brain_on: bool,
) -> base.ScenarioResult:
    if not run_brain_off or not run_brain_on:
        return _scenario_result("Brain comparison", "NOT RUN", "both cases required")
    brain_off = summary.brain_off_acceptance
    brain_on = summary.acceptance_main
    if brain_off is None or brain_on is None:
        return _scenario_result("Brain comparison", "FAIL", "missing case result")
    details = {
        "same_task": True,
        "same_provider": brain_off.details.get("provider") == brain_on.details.get("provider"),
        "same_model": brain_off.details.get("model") == brain_on.details.get("model"),
        "same_environment": summary.environment_resolution is not None,
        "environment_details": summary.environment_resolution.details if summary.environment_resolution else None,
        "same_target_fixture": summary.candidate_root.as_posix() if summary.candidate_root else None,
        "brain_off": _scenario_to_dict(brain_off),
        "brain_on": _scenario_to_dict(brain_on),
        "brain_off_external_context_count": brain_off.details.get("external_context_count"),
        "brain_on_external_context_count": brain_on.details.get("external_context_count"),
        "same_build_runner": True,
        "same_harness_fixture": True,
    }
    _write_json(summary.evidence_root / "comparison.json", details)
    if details["same_provider"] and details["same_model"] and details["brain_off_external_context_count"] == 0 and details["brain_on_external_context_count"] == 1:
        return _scenario_result("Brain comparison", "PASS", "brain off/on compared", **details)
    return _scenario_result("Brain comparison", "FAIL", "comparison mismatch", **details)


def _knowledge_result(summary: ValidationSummary) -> Any:
    if summary.knowledge_result is None:
        raise base.ScenarioBlocked("knowledge result missing")
    return summary.knowledge_result


def _source_excerpt(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line.strip()
    return ""


def _contains_registry_lookup(text: str) -> bool:
    return "Registries.BLOCK" in text and (
        'Identifier.of("minecraft", "diamond_block")' in text
        or 'Identifier.ofVanilla("diamond_block")' in text
    )


def _run_minecraft_runtime(summary: ValidationSummary) -> base.ScenarioResult:
    if summary.working_root is None or summary.validation_root is None:
        raise base.ScenarioBlocked("workspace missing")
    project_root = summary.accepted_target_root
    harness_root = summary.accepted_harness_root
    if project_root is None or harness_root is None:
        raise base.ScenarioBlocked("brain on workspace missing")
    runner = MinecraftTestRunner(
        project_root=project_root,
        harness_root=harness_root,
        evidence_root=summary.evidence_root / "minecraft",
    )
    spec = MinecraftTestSpec(
        target_jar=WORKSPACE_TARGET_JAR,
        target_mod_id=DEFAULT_TARGET_MOD_ID,
        minecraft_version=DEFAULT_MINECRAFT_VERSION,
        loader_version=DEFAULT_LOADER_VERSION,
        test_id=DEFAULT_TEST_ID,
        timeout_seconds=120,
    )
    with _temp_env(GRADLE_USER_HOME=str(summary.validation_root / "gradle-home")):
        result = runner.run(spec, run_id="l4-runtime", java_version="21", launch_mode="pass")
    details = {
        "runtime_status": result.status.value,
        "runtime_reason": result.reason,
        "target_jar": str(result.target.path),
        "target_sha256": result.target.sha256,
        "runtime_sha_match": result.metadata.get("target_sha_match"),
        "server_started": result.metadata.get("server_started"),
        "functional_test_result": result.metadata.get("harness_result_state"),
        "process_exit_code": result.process_evidence.exit_code if result.process_evidence else None,
        "process_timed_out": result.process_evidence.timed_out if result.process_evidence else None,
        "shutdown_requested": result.runtime_evidence.metadata.get("shutdown_requested") if result.runtime_evidence else None,
        "harness_result_json": str(result.evidence_paths.harness_result_json),
        "result_json": str(result.evidence_paths.result_json),
    }
    _write_json(summary.evidence_root / "minecraft.json", details)
    if result.status.value == "PASS":
        return _scenario_result("Minecraft harness", "PASS", "observed expected block state", **details)
    return _scenario_result("Minecraft harness", "FAIL", result.reason, **details)


def _run_gradle_build(project_root: Path, timeout_seconds: int, gradle_home: Path) -> base.ScenarioResult:
    command = base._gradle_build_command(project_root, ["build", "--no-daemon", "--stacktrace"])
    with _temp_env(GRADLE_USER_HOME=str(gradle_home)):
        result = base._run_command(command, cwd=project_root, timeout_seconds=timeout_seconds)
    if result.timed_out:
        return _scenario_result(project_root.name, "BLOCKED", "gradle timeout", command=" ".join(command))
    if result.exit_code != 0:
        return _scenario_result(
            project_root.name,
            "FAIL",
            "gradle build failed",
            command=" ".join(command),
            stdout_tail=base._tail(result.stdout),
            stderr_tail=base._tail(result.stderr),
        )
    jar = next((project_root / "build" / "libs").glob("*.jar"), None)
    return _scenario_result(
        project_root.name,
        "PASS",
        "build successful",
        command=" ".join(command),
        jar=str(jar) if jar else None,
    )


def _run_suite(summary: ValidationSummary, args: argparse.Namespace) -> base.ScenarioResult:
    pytest_temp = summary.validation_root / "pytest-tmp"
    if pytest_temp.exists():
        shutil.rmtree(pytest_temp, ignore_errors=True)
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
    _write_json(summary.evidence_root / "pytest-suite.json", {
        "command": command,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "stdout_tail": base._tail(result.stdout),
        "stderr_tail": base._tail(result.stderr),
    })
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


def _scenario_result(name: str, status: str, reason: str, **details: Any) -> base.ScenarioResult:
    return base._scenario_result(name, status, reason, **details)


def _scenario_to_dict(item: base.ScenarioResult | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {"name": item.name, "status": item.status, "reason": item.reason, "details": item.details}


def _write_artifacts(summary: ValidationSummary) -> None:
    assert summary.evidence_root is not None
    base._write_json(summary.evidence_root / "summary.json", summary.to_dict())
    (summary.evidence_root / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")


def _summary_markdown(summary: ValidationSummary) -> str:
    lines = [
        "# PD Agent v0.3 Validation",
        "",
        f"- Final status: `{summary.final_status()}`",
        f"- Repository commit: `{summary.repository_commit}`" if summary.repository_commit else "- Repository commit: unknown",
        "",
        "## Scenarios",
    ]
    for item in (
        summary.environment_resolution,
        summary.brain_retrieval,
        summary.baseline_target_build,
        summary.baseline_harness_build,
        summary.brain_off_acceptance,
        summary.acceptance_main,
        summary.comparison,
        summary.minecraft_runtime,
        summary.suite,
    ):
        if item is not None:
            lines.append(f"- {item.name}: {item.status} - {item.reason}")
    if summary.brain_off_acceptance is not None or summary.acceptance_main is not None:
        lines.extend(["", "## Brain comparison"])
        if summary.brain_off_acceptance is not None:
            lines.append(f"- Brain OFF: {summary.brain_off_acceptance.status} - {summary.brain_off_acceptance.reason}")
        if summary.acceptance_main is not None:
            lines.append(f"- Brain ON: {summary.acceptance_main.status} - {summary.acceptance_main.reason}")
        if summary.comparison is not None:
            lines.append(f"- Comparison: {summary.comparison.status} - {summary.comparison.reason}")
    if summary.notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in summary.notes)
    return "\n".join(lines) + "\n"


def _print_summary(summary: ValidationSummary) -> None:
    print("L4 VALIDATION - PD Agent v0.3")
    print()
    print(f"Target build: {summary.baseline_target_build.status if summary.baseline_target_build else 'NOT RUN'}")
    print(f"Harness build: {summary.baseline_harness_build.status if summary.baseline_harness_build else 'NOT RUN'}")
    print(f"Environment: {summary.environment_resolution.status if summary.environment_resolution else 'NOT RUN'}")
    print(f"Brain retrieval: {summary.brain_retrieval.status if summary.brain_retrieval else 'NOT RUN'}")
    print(f"Brain OFF: {summary.brain_off_acceptance.status if summary.brain_off_acceptance else 'NOT RUN'}")
    print(f"Acceptance main: {summary.acceptance_main.status if summary.acceptance_main else 'NOT RUN'}")
    print(f"Comparison: {summary.comparison.status if summary.comparison else 'NOT RUN'}")
    print(f"Minecraft harness: {summary.minecraft_runtime.status if summary.minecraft_runtime else 'NOT RUN'}")
    print(f"Suite: {summary.suite.status if summary.suite else 'NOT RUN'}")
    print()
    print(f"FINAL: {summary.final_status()}")
    if summary.finished_at is not None:
        duration = max((summary.finished_at - summary.started_at).total_seconds(), 0.0)
        print(f"Duration: {duration:.3f}s")
    print(f"Evidence: {summary.validation_root}")


def _cleanup(summary: ValidationSummary, *, keep_working_copy: bool) -> None:
    if keep_working_copy:
        return
    if summary.working_root and summary.working_root.exists():
        shutil.rmtree(summary.working_root, ignore_errors=True)


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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _sanitize_request(data: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(data, default=str))


def _sanitize_response(response: Any) -> dict[str, Any] | None:
    if response is None:
        return None
    if hasattr(response, "to_dict"):
        try:
            return json.loads(json.dumps(response.to_dict(), default=str))
        except Exception:
            pass
    return {"text": getattr(response, "text", None)}


if __name__ == "__main__":
    raise SystemExit(main())
