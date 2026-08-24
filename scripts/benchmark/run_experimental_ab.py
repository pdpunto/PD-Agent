"""Run or resume the isolated, non-official Gemini/Luna mini A/B study."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pd_agent import ArtifactValidator, GradleBuildRunner, YarnKnowledgeSource
from pd_agent.benchmark import (
    BenchmarkCatalog,
    BenchmarkConfig,
    BenchmarkExecutor,
    BenchmarkGradleEnvironment,
)
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
TASK_ID = "F6-T2"
TASK_VERSION = "5"
FIXTURE_IDENTITY = "3c27fd809429bc57637b3d930733d5cc7c1891073e9307325d30d25058161396"
F9_EXECUTION_ID = "bbfe2a82-fda5-4f7a-bc08-fba8ce66b524"


def _load_configs(path: Path) -> list[BenchmarkConfig]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("experimental A/B configs must be a JSON list of two configs")
    configs = [BenchmarkConfig.from_dict(dict(item)) for item in payload]
    validate_ab_configs(configs)
    return configs


def _read_json(path: Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write(path: Path, payload: object) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _build_manifest(*, args: argparse.Namespace, execution_id: str, configs: list[BenchmarkConfig], schedule: ExperimentalABSchedule, task: object, dataset: object, seed_manifest: object) -> dict:
    return {
        "schema_version": 1, "experimental": True, "non_official": True, "execution_id": execution_id,
        "pd_agent_commit": args.pd_agent_commit, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
        "task_id": TASK_ID, "task_version": TASK_VERSION, "fixture_identity": FIXTURE_IDENTITY,
        "configs": [config.to_dict() for config in configs], "config_hashes": {config.config_id: config.config_hash() for config in configs},
        "schedule_hash": schedule.hash, "target_valid_runs_per_provider": 2, "max_attempts_per_provider": 3,
        "max_total_attempts": 6, "hard_budget_usd_per_luna_run": "1.00", "global_openai_exposure_cap_usd": "3.00",
        "scheduling_seed": 0, "seed_manifest": seed_manifest.to_dict(),
        "seed_root": str(args.gradle_seed_root), "seed_manifest_path": str(args.gradle_seed_manifest),
        "task": task.to_dict(), "dataset": dataset.to_dict(),
    }


def _validate_resume(*, execution_root: Path, args: argparse.Namespace) -> tuple[dict, ExperimentalABSchedule, ExperimentalABController, list[BenchmarkConfig]]:
    manifest = _read_json(execution_root / "experimental-manifest.json")
    if manifest.get("experimental") is not True or manifest.get("non_official") is not True:
        raise ValueError("resume refused: experimental/non_official flags missing")
    if manifest.get("execution_id") != execution_root.name or manifest.get("execution_id") == F9_EXECUTION_ID:
        raise ValueError("resume refused: execution identity drift or F9 execution")
    if manifest.get("pd_agent_commit") != args.pd_agent_commit:
        raise ValueError("resume refused: commit drift")
    if manifest.get("dataset_id") != DATASET_ID or manifest.get("dataset_version") != DATASET_VERSION:
        raise ValueError("resume refused: dataset drift")
    if manifest.get("task_id") != TASK_ID or manifest.get("task_version") != TASK_VERSION:
        raise ValueError("resume refused: task drift")
    if manifest.get("fixture_identity") != FIXTURE_IDENTITY:
        raise ValueError("resume refused: fixture drift")
    if manifest.get("scheduling_seed") != 0 or manifest.get("hard_budget_usd_per_luna_run") != "1.00" or manifest.get("global_openai_exposure_cap_usd") != "3.00":
        raise ValueError("resume refused: schedule or budget drift")
    configs = [BenchmarkConfig.from_dict(dict(item)) for item in manifest.get("configs", [])]
    validate_ab_configs(configs)
    expected_hashes = {config.config_id: config.config_hash() for config in configs}
    if manifest.get("config_hashes") != expected_hashes:
        raise ValueError("resume refused: config hash drift")
    schedule = ExperimentalABSchedule.from_dict(_read_json(execution_root / "schedule.json"))
    if manifest.get("schedule_hash") != schedule.hash:
        raise ValueError("resume refused: schedule drift")
    if manifest.get("target_valid_runs_per_provider") != 2 or manifest.get("max_attempts_per_provider") != 3 or manifest.get("max_total_attempts") != 6:
        raise ValueError("resume refused: repetition/attempt drift")
    state_data = _read_json(execution_root / "execution-state.json")
    controller = ExperimentalABController.from_dict(schedule, state_data)
    if controller.state.execution_id != execution_root.name:
        raise ValueError("resume refused: state execution identity drift")
    if not controller.state.pending_attempt_id:
        raise ValueError("resume refused: no exact pending attempt")
    return manifest, schedule, controller, configs


def _restore_gradle_environment(execution_root: Path, manifest: dict) -> BenchmarkGradleEnvironment:
    from pd_agent.benchmark.environment import BenchmarkGradleSeedManifest

    bootstrap = _read_json(execution_root / "environment" / "bootstrap.json")
    seed_manifest_path = execution_root / "environment" / "gradle-seed" / "manifest.json"
    seed_manifest = BenchmarkGradleSeedManifest.from_dict(_read_json(seed_manifest_path))
    return BenchmarkGradleEnvironment(
        seed_root=Path(manifest["seed_root"]), execution_root=execution_root, seed_manifest=seed_manifest,
        materialization_root=execution_root / "environment", gradle_user_home=Path(bootstrap["materialization_root"]) / "gradle-user-home",
        source_manifest_path=Path(manifest["seed_manifest_path"]), seed_manifest_path=seed_manifest_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Experimental non-official Gemini/Luna mini A/B")
    parser.add_argument("--catalog-root", required=True, type=Path)
    parser.add_argument("--pd-agent-commit", required=True)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--configs-json", type=Path)
    parser.add_argument("--launch-root", type=Path)
    parser.add_argument("--gradle-seed-root", type=Path)
    parser.add_argument("--gradle-seed-manifest", type=Path)
    return parser


def _executor(*, config: BenchmarkConfig, execution_root: Path, gradle_environment: BenchmarkGradleEnvironment, repo_root: Path):
    guard = LunaBudgetGuard() if config.provider.casefold() == "openai" else None
    key_name = "GEMINI_API_KEY" if config.provider.casefold() == "gemini" else "OPENAI_API_KEY"
    api_key = os.environ.get(key_name)
    if not api_key:
        raise ValueError(f"{key_name} missing")
    provider = BenchmarkPacedProvider(provider=provider_for_config(config, api_key=api_key, budget_guard=guard), pacer=BenchmarkRequestPacer(min_interval_seconds=4.5))
    executor = BenchmarkExecutor(provider=provider, build_runner=GradleBuildRunner(environment_overrides=gradle_environment.environment_overrides),
        artifact_validator=ArtifactValidator(), tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        knowledge_source=YarnKnowledgeSource() if config.brain_enabled else None,
        minecraft_runner=MinecraftTestRunner(project_root=execution_root, harness_root=repo_root / "tests" / "fixtures" / "l11_minecraft_harness",
                                              environment_overrides=gradle_environment.environment_overrides), gradle_environment=gradle_environment)
    return executor, guard


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    if args.resume is not None:
        execution_root = args.resume.resolve(strict=True)
        manifest, _schedule, controller, configs = _validate_resume(execution_root=execution_root, args=args)
        catalog = BenchmarkCatalog.load(args.catalog_root)
        dataset = catalog.dataset_for(DATASET_ID, DATASET_VERSION)
        task = catalog.task_for(TASK_ID, TASK_VERSION)
        if task.fixture.fixture_identity != FIXTURE_IDENTITY or dataset.dataset_id != DATASET_ID:
            raise ValueError("resume refused: catalog freeze drift")
        gradle_environment = _restore_gradle_environment(execution_root, manifest)
    else:
        required = (args.configs_json, args.launch_root, args.gradle_seed_root, args.gradle_seed_manifest)
        if any(item is None for item in required):
            raise ValueError("fresh launch requires configs-json, launch-root and Gradle seed arguments")
        launch_root = args.launch_root.resolve(strict=False)
        if launch_root.exists():
            raise ValueError("--launch-root must be new and unused")
        configs = _load_configs(args.configs_json)
        catalog = BenchmarkCatalog.load(args.catalog_root)
        dataset = catalog.dataset_for(DATASET_ID, DATASET_VERSION)
        task = catalog.task_for(TASK_ID, TASK_VERSION)
        if task.fixture.fixture_identity != FIXTURE_IDENTITY:
            raise ValueError("fixture identity drift")
        launch_root.mkdir(parents=True)
        execution_root = launch_root / "ExecutionRoot"
        execution_root.mkdir()
        execution_id = execution_root.name
        seed_manifest = BenchmarkGradleEnvironment._load_expected_manifest(args.gradle_seed_root, args.gradle_seed_manifest, seed_id="gradle-wrapper-caches", seed_version="1")
        if seed_manifest is None:
            raise ValueError("Gradle seed manifest missing")
        gemini = next(c for c in configs if c.provider.casefold() == "gemini")
        luna = next(c for c in configs if c.provider.casefold() == "openai")
        schedule = ExperimentalABSchedule.create(gemini_config_id=gemini.config_id, gemini_config_hash=gemini.config_hash(), luna_config_id=luna.config_id, luna_config_hash=luna.config_hash())
        cells = {c.config_id: ExperimentalABCell(provider=c.provider, model=c.model, config_id=c.config_id, config_hash=c.config_hash()) for c in configs}
        controller = ExperimentalABController(schedule=schedule, state=ExperimentalABState(execution_id=execution_id), cells=cells)
        gradle_environment = BenchmarkGradleEnvironment.prepare(seed_root=args.gradle_seed_root, execution_root=execution_root, seed_manifest_path=args.gradle_seed_manifest, offline=True)
        manifest = _build_manifest(args=args, execution_id=execution_id, configs=configs, schedule=schedule, task=task, dataset=dataset, seed_manifest=gradle_environment.seed_manifest)
        _write(execution_root / "experimental-manifest.json", manifest)
        _write(execution_root / "schedule.json", schedule.to_dict())
        _write(execution_root / "execution-state.json", controller.to_dict())

    fixture_root = repo_root / "benchmarks" / "projects" / "v0_5_fabric_base"
    while True:
        scheduled = controller.next_attempt()
        if scheduled is None:
            break
        config = next(config for config in configs if config.config_id == scheduled.config_id)
        executor, guard = _executor(config=config, execution_root=execution_root, gradle_environment=gradle_environment, repo_root=repo_root)
        if guard is not None:
            controller.state.reserve_luna_attempt(attempt_id=scheduled.scheduled_attempt_id)
        try:
            result = executor.execute(task, config, scheduled, fixture_root=fixture_root, execution_root=execution_root, pd_agent_commit=args.pd_agent_commit, preserve_workspace=True)
        except Exception as exc:
            controller.pause(scheduled, rate_limit="rate_limit" in str(exc).casefold(), reason=str(exc))
            _write(execution_root / "execution-state.json", controller.to_dict())
            break
        if str(getattr(result.classification, "failure_code", "")).casefold().endswith("rate_limit"):
            controller.pause(scheduled, rate_limit=True, reason="provider rate limit")
            _write(execution_root / "execution-state.json", controller.to_dict())
            break
        controller.record(scheduled, {"provider": config.provider, "status": result.benchmark_run.execution_status.value, "outcome": result.benchmark_run.task_outcome.value, "run_id": result.run_state.run_id, "cost_usd": guard.metadata().get("accumulated_cost_usd") if guard else None})
        _write(execution_root / "execution-state.json", controller.to_dict())
    if controller.state.status == ExperimentalABStatus.RUNNING:
        controller.state.status = ExperimentalABStatus.COMPLETED if all(cell.complete for cell in controller.cells.values()) else ExperimentalABStatus.INCOMPLETE
    runs = [summary for cell in controller.cells.values() for summary in cell.attempts]
    _write(execution_root / "comparison.json", aggregate_experimental_runs(runs) | {"status": controller.state.status.value})
    _write(execution_root / "comparison.md", "# Experimental Gemini/Luna mini A/B\n\nThis report is non-official and isolated from F9.\n")
    _write(execution_root / "execution-state.json", controller.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
