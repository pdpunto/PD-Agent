"""CLI for PD Agent v0.1."""

from __future__ import annotations

import argparse
import os
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
from .web.security import policy_for_server_port


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
        help="Provider name. v0.1 supports openai or gemini.",
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
    web_parser = subparsers.add_parser("web", help="Serve the local productive Web application.")
    web_parser.add_argument("--host", default=None, help="Bind host; only 127.0.0.1 is accepted.")
    web_parser.add_argument("--port", default=None, type=int, help="TCP port (1-65535).")
    web_parser.add_argument("--provider", default=None, help="Operational provider configuration.")
    web_parser.add_argument("--model", default=None, help="Operational model configuration.")
    web_parser.add_argument("--runs-dir", default=None, type=Path, help="Directory for run artifacts.")
    web_parser.add_argument("--product-data-root", default=None, type=Path, help="Directory for product metadata.")
    web_parser.add_argument("--frontend-dist", default=None, type=Path, help="Built frontend directory.")
    web_parser.add_argument("--economic-budget-usd", default=None, help="Optional positive provider budget.")
    web_parser.add_argument("--economic-state", default=None, type=Path, help="Shared economic state JSON path.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime_factory: Any = build_runtime_bundle,
    application_factory: Any | None = None,
    server_runner: Any | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "web":
            return _web_command(args, application_factory=application_factory, server_runner=server_runner)
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
        if getattr(args, "log_level", None) is not None:
            overrides["log_level"] = args.log_level
        if getattr(args, "provider", None) is not None:
            overrides["provider"] = args.provider
        if getattr(args, "model", None) is not None:
            overrides["model"] = args.model
        if getattr(args, "runs_dir", None) is not None:
            overrides["runs_dir"] = args.runs_dir
        if overrides:
            config = replace(config, **overrides)
        return config
    except ValueError as exc:
        raise CLIError(str(exc)) from exc


def _web_command(
    args: argparse.Namespace,
    *,
    application_factory: Any | None,
    server_runner: Any | None,
) -> int:
    host = args.host or os.environ.get("PD_AGENT_WEB_HOST", "127.0.0.1")
    if host != "127.0.0.1":
        raise CLIError("web host must be 127.0.0.1")
    port = args.port if args.port is not None else _web_port(os.environ.get("PD_AGENT_WEB_PORT", "8000"))
    if not 1 <= port <= 65_535:
        raise CLIError("web port must be between 1 and 65535")
    config = _resolve_config(args)
    configure_logging(config.log_level)
    frontend = Path(args.frontend_dist or os.environ.get("PD_AGENT_FRONTEND_DIST", "frontend/dist")).expanduser().resolve()
    if not frontend.is_dir():
        raise CLIError(f"frontend dist does not exist: {frontend}")
    product_root = args.product_data_root or os.environ.get("PD_AGENT_PRODUCT_DATA_ROOT")
    budget = args.economic_budget_usd or os.environ.get("PD_AGENT_ECONOMIC_BUDGET_USD")
    economic_state_path = args.economic_state or os.environ.get("PD_AGENT_ECONOMIC_STATE")
    knowledge_pack = os.environ.get("PD_AGENT_KNOWLEDGE_PACK_PATH")
    knowledge_pack_id = os.environ.get("PD_AGENT_KNOWLEDGE_PACK_ID")
    if application_factory is None:
        from .product import build_product_application

        application_factory = build_product_application
    if server_runner is None:
        server_runner = _run_uvicorn
    application = None
    try:
        kwargs: dict[str, Any] = {"economic_budget_usd": budget}
        if economic_state_path is not None:
            from .experimental import LunaSharedBudgetSession

            try:
                economic_session = LunaSharedBudgetSession.load(
                    Path(economic_state_path).expanduser(),
                    expected_global_ceiling=budget,
                )
            except (OSError, ValueError) as exc:
                raise CLIError(f"shared economic state is not usable: {exc}") from exc
            state = economic_session.state
            if (
                state.active_attempt_id is not None
                or state.reconciliation_state != "CLEAR"
                or state.global_reserved_usd != 0
                or state.attempt_reserved_usd != 0
                or state.global_uncertain_consumed_usd != 0
                or state.attempt_uncertain_consumed_usd != 0
            ):
                raise CLIError("shared economic state requires reconciliation before web execution")
            kwargs["economic_session"] = economic_session
        if knowledge_pack is not None:
            kwargs["knowledge_pack_path"] = Path(knowledge_pack).expanduser()
            if knowledge_pack_id is not None:
                kwargs["knowledge_pack_id"] = knowledge_pack_id
        if product_root is not None:
            kwargs["product_data_root"] = Path(product_root).expanduser()
        application = application_factory(config, **kwargs)
        from .web import create_app

        app = create_app(
            services=application.web_services,
            frontend_dist=frontend,
            policy=policy_for_server_port(port),
        )
        server_runner(app, host=host, port=port)
        return EXIT_OK
    finally:
        if application is not None:
            shutdown = getattr(application, "shutdown", None) or getattr(application, "close", None)
            if shutdown is not None:
                shutdown()


def _web_port(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CLIError("web port must be an integer") from exc


def _run_uvicorn(app: Any, *, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


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
