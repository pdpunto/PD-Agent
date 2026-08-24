"""Run the isolated, non-official Gemini/Luna mini A/B experiment.

This launcher intentionally does not import or invoke the official batch
runner, scheduler, aggregator, or F9 execution directories.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pd_agent import ArtifactValidator, GradleBuildRunner, YarnKnowledgeSource
from pd_agent.benchmark import BenchmarkCatalog, BenchmarkExecutor, BenchmarkGradleEnvironment
from pd_agent.benchmark.experimental_ab import (
    ExperimentalABCell,
    ExperimentalABController,
    ExperimentalABSchedule,
    ExperimentalABState,
    ExperimentalABStatus,
    aggregate_experimental_runs,
    provider_for_config,
    validate_ab_configs,
)
from pd_agent.benchmark.pacing import BenchmarkPacedProvider, BenchmarkRequestPacer
from pd_agent.experimental import LunaBudgetGuard
from pd_agent.minecraft import MinecraftTestRunner
from pd_agent.tools import ToolExecutor, create_filesystem_tools


DATASET_ID = "PD_AGENT_BENCHMARK_DATASET_V0.5_5"
DATASET_VERSION = "0.5.5"
FIXTURE_IDENTITY = "3c27fd809429bc57637b3d930733d5cc7c1891073e9307325d30d25058161396"


def _configs(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("experimental A/B configs must be a JSON list of two configs")
    configs = [__import__("pd_agent.benchmark", fromlist=["BenchmarkConfig"]).BenchmarkConfig.from_dict(item) for item in payload]
    validate_ab_configs(configs)
    return configs


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Experimental non-official Gemini/Luna mini A/B")
    parser.add_argument("--catalog-root", required=True, type=Path)
    parser.add_argument("--configs-json", required=True, type=Path)
    parser.add_argument("--launch-root", required=True, type=Path)
    parser.add_argument("--gradle-seed-root", required=True, type=Path)
    parser.add_argument("--gradle-seed-manifest", required=True, type=Path)
    parser.add_argument("--pd-agent-commit", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    launch_root = args.launch_root.resolve(strict=False)
    if launch_root.exists():
        raise ValueError("--launch-root must be new and unused")
    launch_root.mkdir(parents=True)
    execution_root = launch_root / "ExecutionRoot"
    if execution_root.exists():
        raise ValueError("ExecutionRoot must not exist before launch")
    execution_root.mkdir()
    execution_id = execution_root.name

    configs = _configs(args.configs_json)
    by_provider = {config.provider.casefold(): config for config in configs}
    catalog = BenchmarkCatalog.load(args.catalog_root)
    dataset = catalog.dataset_for(DATASET_ID, DATASET_VERSION)
    task = catalog.task_for("F6-T2", "5")
    if task.fixture.fixture_identity != FIXTURE_IDENTITY:
        raise ValueError("fixture identity drift")
    schedule = ExperimentalABSchedule.create(
        gemini_config_id=by_provider["gemini"].config_id,
        gemini_config_hash=by_provider["gemini"].config_hash(),
        luna_config_id=by_provider["openai"].config_id,
        luna_config_hash=by_provider["openai"].config_hash(),
    )
    cells = {config.config_id: ExperimentalABCell(provider=config.provider, model=config.model,
              config_id=config.config_id, config_hash=config.config_hash()) for config in configs}
    controller = ExperimentalABController(schedule=schedule, state=ExperimentalABState(execution_id=execution_id), cells=cells)
    _write(execution_root / "experimental-manifest.json", {"experimental": True, "non_official": True,
        "execution_id": execution_id, "pd_agent_commit": args.pd_agent_commit, "dataset": dataset.to_dict(),
        "task": task.to_dict(), "configs": [config.to_dict() for config in configs]})
    _write(execution_root / "schedule.json", schedule.to_dict())
    _write(execution_root / "execution-state.json", controller.state.to_dict())

    repo_root = Path(__file__).resolve().parents[2]
    gradle_environment = BenchmarkGradleEnvironment.prepare(seed_root=args.gradle_seed_root,
        execution_root=execution_root, seed_manifest_path=args.gradle_seed_manifest, offline=True)
    fixture_root = repo_root / "benchmarks" / "projects" / "v0_5_fabric_base"
    runs: list[dict[str, object]] = []
    while True:
        scheduled = controller.next_attempt()
        if scheduled is None:
            break
        config = next(config for config in configs if config.config_id == scheduled.config_id)
        guard = LunaBudgetGuard() if config.provider.casefold() == "openai" else None
        if guard is not None:
            controller.state.reserve_luna_attempt()
        key_name = "GEMINI_API_KEY" if config.provider.casefold() == "gemini" else "OPENAI_API_KEY"
        api_key = os.environ.get(key_name)
        if not api_key:
            raise ValueError(f"{key_name} missing")
        provider = BenchmarkPacedProvider(provider=provider_for_config(config, api_key=api_key, budget_guard=guard),
                                          pacer=BenchmarkRequestPacer(min_interval_seconds=4.5))
        executor = BenchmarkExecutor(provider=provider,
            build_runner=GradleBuildRunner(environment_overrides=gradle_environment.environment_overrides),
            artifact_validator=ArtifactValidator(), tool_executor=ToolExecutor(tools=create_filesystem_tools()),
            knowledge_source=YarnKnowledgeSource() if config.brain_enabled else None,
            minecraft_runner=MinecraftTestRunner(project_root=execution_root,
                harness_root=repo_root / "tests" / "fixtures" / "l11_minecraft_harness",
                environment_overrides=gradle_environment.environment_overrides), gradle_environment=gradle_environment)
        try:
            result = executor.execute(task, config, scheduled, fixture_root=fixture_root,
                execution_root=execution_root, pd_agent_commit=args.pd_agent_commit, preserve_workspace=True)
        except Exception as exc:
            controller.pause(scheduled, rate_limit="rate_limit" in str(exc).casefold(), reason=str(exc))
            _write(execution_root / "execution-state.json", controller.state.to_dict())
            break
        classification = result.classification
        if str(getattr(classification, "failure_code", "")).casefold().endswith("rate_limit"):
            controller.pause(scheduled, rate_limit=True, reason="provider rate limit")
            _write(execution_root / "execution-state.json", controller.state.to_dict())
            break
        summary = {"provider": config.provider, "status": result.benchmark_run.execution_status.value,
                   "outcome": result.benchmark_run.task_outcome.value, "run_id": result.run_state.run_id,
                   "cost_usd": guard.metadata().get("accumulated_cost_usd") if guard else None}
        controller.record(scheduled, summary)
        runs.append(summary)
        _write(execution_root / "execution-state.json", controller.state.to_dict())
    if controller.state.status == "RUNNING":
        controller.state.status = ExperimentalABStatus.COMPLETED if all(cell.complete for cell in cells.values()) else ExperimentalABStatus.INCOMPLETE
    _write(execution_root / "comparison.json", aggregate_experimental_runs(runs) | {"status": controller.state.status.value})
    _write(execution_root / "comparison.md", "# Experimental Gemini/Luna mini A/B\n\nThis report is non-official and isolated from F9.\n")
    _write(execution_root / "execution-state.json", controller.state.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
