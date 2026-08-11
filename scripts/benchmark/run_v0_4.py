from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Callable

from pd_agent import ArtifactValidator, ContextManager, GradleBuildRunner
from pd_agent.benchmark import BenchmarkCatalog, BenchmarkConfig, BenchmarkExecutionRunner, BenchmarkExecutor
from pd_agent.tools import ToolExecutor, create_filesystem_tools


def _load_callable(spec: str) -> Callable[..., Any]:
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ValueError("callable spec must look like module:callable")
    module = importlib.import_module(module_name)
    value = module
    for part in attr.split("."):
        value = getattr(value, part)
    if not callable(value):
        raise TypeError(f"{spec} is not callable")
    return value


def _load_configs(path: Path) -> tuple[BenchmarkConfig, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("configs JSON must be a list")
    return tuple(BenchmarkConfig.from_dict(dict(item)) for item in data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PD Agent v0.4 benchmarks")
    parser.add_argument("--catalog-root", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--configs-json", required=True, type=Path)
    parser.add_argument("--execution-root", required=True, type=Path)
    parser.add_argument("--provider-factory", required=True)
    parser.add_argument("--pd-agent-commit", default=None)
    parser.add_argument("--target-valid-repetitions", type=int, default=3)
    parser.add_argument("--max-attempts-per-cell", type=int, default=5)
    parser.add_argument("--scheduling-seed", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider_factory = _load_callable(args.provider_factory)
    provider = provider_factory()
    catalog = BenchmarkCatalog.load(args.catalog_root)
    configs = _load_configs(args.configs_json)
    executor = BenchmarkExecutor(
        provider=provider,
        build_runner=GradleBuildRunner(),
        artifact_validator=ArtifactValidator(),
        tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        context_manager_factory=lambda brain_enabled: ContextManager(),
    )
    runner = BenchmarkExecutionRunner(
        executor=executor,
        target_valid_repetitions=args.target_valid_repetitions,
        max_attempts_per_cell=args.max_attempts_per_cell,
        scheduling_seed=args.scheduling_seed,
    )
    batch = runner.run(
        catalog,
        dataset_id=args.dataset_id,
        dataset_version=args.dataset_version,
        configs=configs,
        execution_root=args.execution_root,
        pd_agent_commit=args.pd_agent_commit,
    )
    print(batch.comparison_json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
