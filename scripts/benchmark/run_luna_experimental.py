"""Run exactly one isolated, non-official GPT-5.6 Luna smoke when authorized."""

from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from pd_agent import ArtifactValidator, GradleBuildRunner, YarnKnowledgeSource
from pd_agent.benchmark import (
    BenchmarkCatalog,
    BenchmarkConfig,
    BenchmarkExecutor,
    BenchmarkGradleEnvironment,
    BenchmarkPacedProvider,
    BenchmarkRequestPacer,
)
from pd_agent.benchmark.scheduler import BenchmarkScheduledAttempt
from pd_agent.experimental import (
    LUNA_EXPERIMENTAL_HARD_BUDGET_USD,
    LunaBudgetGuard,
    LunaPricingSnapshot,
    build_luna_experimental_manifest,
)
from pd_agent.minecraft import MinecraftTestRunner
from pd_agent.providers import OpenAIProvider
from pd_agent.tools import ToolExecutor, create_filesystem_tools


def _load_one_config(path: Path) -> BenchmarkConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError("experimental Luna smoke requires exactly one config")
    config = BenchmarkConfig.from_dict(dict(data[0]))
    if config.provider.casefold() != "openai" or config.model != "gpt-5.6-luna":
        raise ValueError("experimental config must target openai/gpt-5.6-luna")
    if config.model_config.get("reasoning") != {"effort": "medium"}:
        raise ValueError("experimental config must use reasoning effort medium")
    limits = config.execution_limits
    if limits is None or limits.max_agent_steps != 25 or limits.provider_retry_limit != 2 or limits.max_context_bytes != 2_000_000:
        raise ValueError("experimental config changed the frozen F6-T2 limits")
    return config


def _positive_budget(value: str) -> Decimal:
    try:
        budget = Decimal(value)
    except (InvalidOperation, ValueError):
        raise argparse.ArgumentTypeError("hard budget must be a finite positive decimal") from None
    if not budget.is_finite() or budget <= 0:
        raise argparse.ArgumentTypeError("hard budget must be a finite positive decimal")
    return budget


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one isolated non-official Luna smoke")
    parser.add_argument("--catalog-root", required=True, type=Path)
    parser.add_argument("--configs-json", required=True, type=Path)
    parser.add_argument("--launch-root", required=True, type=Path)
    parser.add_argument("--gradle-seed-root", required=True, type=Path)
    parser.add_argument("--gradle-seed-manifest", required=True, type=Path)
    parser.add_argument("--pd-agent-commit", required=True)
    parser.add_argument(
        "--hard-budget-usd",
        type=_positive_budget,
        default=LUNA_EXPERIMENTAL_HARD_BUDGET_USD,
    )
    return parser


def validate_experimental_prelaunch_paths(launch_root: Path, config_path: Path) -> tuple[Path, Path]:
    """Validate external staging before acquiring the exclusive launch root."""

    launch_root = Path(launch_root).resolve(strict=False)
    config_path = Path(config_path).resolve(strict=False)
    if launch_root.exists():
        raise ValueError("--launch-root must be new and unused")
    try:
        config_path.relative_to(launch_root)
    except ValueError:
        if not config_path.is_file():
            raise FileNotFoundError(f"runtime config does not exist: {config_path}")
        return launch_root, config_path
    raise ValueError("runtime config must be staged outside --launch-root")


def initialize_experimental_roots(launch_root: Path) -> tuple[str, Path]:
    """Create the isolated roots before Gradle resolves the execution path."""

    launch_root = Path(launch_root).resolve(strict=False)
    if launch_root.exists():
        raise ValueError("--launch-root must be new and unused")
    launch_root.mkdir(parents=True, exist_ok=False)
    execution_id = str(uuid4())
    execution_root = launch_root / "ExecutionRoot" / execution_id
    if execution_root.exists():
        raise ValueError("ExecutionRoot already exists")
    execution_root.mkdir(parents=True, exist_ok=False)
    return execution_id, execution_root


def _write_experimental_manifest(
    path: Path,
    *,
    execution_id: str,
    run_id: str,
    launch_root: Path,
    execution_root: Path,
    task_id: str,
    task_version: str,
    hard_budget_usd: Decimal,
    pricing: LunaPricingSnapshot,
    **extra: object,
) -> None:
    manifest = build_luna_experimental_manifest(
        execution_id=execution_id,
        run_id=run_id,
        launch_root=str(launch_root),
        task_id=task_id,
        task_version=task_version,
        hard_budget_usd=hard_budget_usd,
        pricing=pricing,
    )
    manifest.update({"execution_root": str(execution_root), **extra})
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    launch_root, config_path = validate_experimental_prelaunch_paths(args.launch_root, args.configs_json)
    execution_id, execution_root = initialize_experimental_roots(launch_root)
    pricing = LunaPricingSnapshot()
    manifest_path = execution_root / "experimental-manifest.json"
    _write_experimental_manifest(
        manifest_path,
        execution_id=execution_id,
        run_id="pending",
        launch_root=launch_root,
        execution_root=execution_root,
        task_id="F6-T2",
        task_version="5",
        hard_budget_usd=args.hard_budget_usd,
        pricing=pricing,
        lifecycle_status="INITIALIZING",
    )

    catalog = BenchmarkCatalog.load(args.catalog_root)
    config = _load_one_config(config_path)
    dataset = catalog.dataset_for("PD_AGENT_BENCHMARK_DATASET_V0.5_5", "0.5.5")
    task = catalog.task_for("F6-T2", "5")
    if task.fixture.fixture_identity != "3c27fd809429bc57637b3d930733d5cc7c1891073e9307325d30d25058161396":
        raise ValueError("F6-T2 fixture identity drift")

    gradle_environment = BenchmarkGradleEnvironment.prepare(
        seed_root=args.gradle_seed_root,
        execution_root=execution_root,
        seed_manifest_path=args.gradle_seed_manifest,
        offline=True,
    )
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY missing")
    guard = LunaBudgetGuard(hard_budget_usd=args.hard_budget_usd, pricing=pricing)
    provider = BenchmarkPacedProvider(
        provider=OpenAIProvider(
            model=config.model,
            api_key=api_key,
            provider_retry_limit=config.execution_limits.provider_retry_limit,
            budget_guard=guard,
            service_tier=pricing.service_tier,
            prompt_cache_options={"mode": "explicit", "ttl": "30m"},
        ),
        pacer=BenchmarkRequestPacer(min_interval_seconds=4.5),
    )
    repo_root = Path(__file__).resolve().parents[2]
    executor = BenchmarkExecutor(
        provider=provider,
        build_runner=GradleBuildRunner(environment_overrides=gradle_environment.environment_overrides),
        artifact_validator=ArtifactValidator(),
        tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        knowledge_source=YarnKnowledgeSource() if config.brain_enabled else None,
        minecraft_runner=MinecraftTestRunner(
            project_root=execution_root,
            harness_root=repo_root / "tests" / "fixtures" / "l11_minecraft_harness",
            environment_overrides=gradle_environment.environment_overrides,
        ),
        gradle_environment=gradle_environment,
    )
    scheduled = BenchmarkScheduledAttempt(
        scheduled_attempt_id=f"experimental-{execution_id}",
        task_id=task.task_id,
        task_version=task.task_version,
        config_id=config.config_id,
        config_hash=config.config_hash(),
        repetition_index=0,
        attempt_index=1,
        scheduling_position=0,
        replacement=False,
    )
    result = executor.execute(
        task,
        config,
        scheduled,
        fixture_root=repo_root / "benchmarks" / "projects" / "v0_5_fabric_base",
        execution_root=execution_root,
        pd_agent_commit=args.pd_agent_commit,
        preserve_workspace=True,
    )
    _write_experimental_manifest(
        manifest_path,
        execution_id=execution_id,
        run_id=result.run_state.run_id,
        launch_root=launch_root,
        execution_root=execution_root,
        task_id=task.task_id,
        task_version=task.task_version,
        hard_budget_usd=args.hard_budget_usd,
        pricing=pricing,
        lifecycle_status="COMPLETED",
        benchmark_run_path=str(result.benchmark_run_path),
        budget_metadata=guard.metadata(),
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
