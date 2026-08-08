"""CLI for PD Agent v0.1."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .bootstrap import RuntimeBundle, build_runtime_bundle
from .config import AppConfig, load_config
from .core.errors import ConfigurationError
from .logging import configure_logging
from .pass_policy import PassEvaluation, evaluate_pass


EXIT_OK = 0
EXIT_RUN_FAILED = 1
EXIT_CONFIG_ERROR = 2


class CLIError(Exception):
    """User-facing CLI error."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pd-agent",
        description="PD Agent v0.1 CLI.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Override log level from environment.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"pd-agent {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run PD Agent on a Fabric project.")
    run_parser.add_argument("--project", required=True, type=Path, help="Path to the Fabric project.")
    run_parser.add_argument("--task", required=True, help="Task to execute.")
    run_parser.add_argument(
        "--provider",
        default=None,
        help="Provider name. v0.1 uses openai.",
    )
    run_parser.add_argument(
        "--model",
        default=None,
        help="OpenAI model name.",
    )
    run_parser.add_argument(
        "--runs-dir",
        default=None,
        type=Path,
        help="Directory for run artifacts.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime_factory: Any = build_runtime_bundle,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command != "run":  # pragma: no cover - defensive guard
            raise CLIError(f"unsupported command: {args.command}")
        return _run_command(args, runtime_factory=runtime_factory)
    except CLIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except ConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except Exception as exc:  # pragma: no cover - defensive guard
        print(f"internal error: {exc}", file=sys.stderr)
        return EXIT_RUN_FAILED


def _run_command(args: argparse.Namespace, *, runtime_factory: Any) -> int:
    project_root = _validate_project_root(args.project)
    task = _validate_task(args.task)
    config = _resolve_config(args)
    configure_logging(config.log_level)

    bundle = runtime_factory(config)
    if not hasattr(bundle, "controller") or not hasattr(bundle, "storage"):
        raise CLIError("runtime factory returned an invalid bundle")

    run_state, _report = bundle.controller.run(project_root, task)
    evaluation = evaluate_pass(bundle.storage, run_state.run_id)
    _emit_result(evaluation, bundle)
    return EXIT_OK if evaluation.passed else EXIT_RUN_FAILED


def _resolve_config(args: argparse.Namespace) -> AppConfig:
    try:
        config = load_config()
        overrides: dict[str, Any] = {}
        if args.log_level is not None:
            overrides["log_level"] = args.log_level
        if args.provider is not None:
            overrides["provider"] = args.provider
        if args.model is not None:
            overrides["model"] = args.model
        if args.runs_dir is not None:
            overrides["runs_dir"] = args.runs_dir
        if overrides:
            config = replace(config, **overrides)
        return config
    except ValueError as exc:
        raise CLIError(str(exc)) from exc


def _validate_project_root(project_root: Path) -> Path:
    candidate = project_root.expanduser()
    if not candidate.exists():
        raise CLIError(f"project root does not exist: {candidate}")
    if not candidate.is_dir():
        raise CLIError(f"project root is not a directory: {candidate}")
    return candidate.resolve()


def _validate_task(task: str) -> str:
    value = task.strip()
    if not value:
        raise CLIError("task cannot be empty")
    return value


def _emit_result(evaluation: PassEvaluation, bundle: RuntimeBundle) -> None:
    report_path = bundle.storage.paths_for(evaluation.run_id).final_report_json
    output = [
        f"run_id: {evaluation.run_id}",
        f"final_state: {evaluation.run_state.state.value if evaluation.run_state else 'UNKNOWN'}",
        f"PASS: {'yes' if evaluation.passed else 'no'}",
    ]
    if evaluation.final_build is not None:
        output.append(
            f"build_final: exit_code={evaluation.final_build.exit_code} success={evaluation.final_build.success}"
        )
    else:
        output.append("build_final: missing")
    if evaluation.artifact is not None:
        artifact_path = str(evaluation.artifact.path) if evaluation.artifact.path is not None else "missing"
        output.append(f"artifact: {evaluation.artifact.classification} ({artifact_path})")
    else:
        output.append("artifact: missing")
    output.append(f"report: {report_path}")
    if evaluation.final_report is not None:
        output.append(
            f"Minecraft runtime validation: {evaluation.final_report.minecraft_runtime_validation}"
        )

    stream = sys.stdout if evaluation.passed else sys.stderr
    for line in output:
        print(line, file=stream)
    if not evaluation.passed:
        print(f"reason: {evaluation.reason}", file=stream)


__all__ = [
    "CLIError",
    "EXIT_CONFIG_ERROR",
    "EXIT_OK",
    "EXIT_RUN_FAILED",
    "build_parser",
    "main",
]
