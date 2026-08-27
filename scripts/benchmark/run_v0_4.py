from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pd_agent import ArtifactValidator, GradleBuildRunner, YarnKnowledgeSource
from pd_agent.benchmark import (
    BenchmarkCatalog,
    BenchmarkConfig,
    BenchmarkExecutionManifest,
    BenchmarkExecutionRunner,
    BenchmarkExecutor,
    BenchmarkGradleEnvironment,
    BenchmarkPacedProvider,
    BenchmarkRequestPacer,
)
from pd_agent.minecraft import MinecraftTestRunner
from pd_agent.providers import GeminiProvider, OpenAIProvider
from pd_agent.experimental import LunaBudgetGuard, LunaSharedBudgetSession
from pd_agent.tools import ToolExecutor, create_filesystem_tools


MIN_PROVIDER_INTERVAL_SECONDS = 4.5
GEMINI_DAILY_REQUEST_BUDGET = 500


def _load_configs(path: Path) -> tuple[BenchmarkConfig, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("configs JSON must be a list")
    return tuple(BenchmarkConfig.from_dict(dict(item)) for item in data)


def _shared_config_payload(config: BenchmarkConfig) -> dict[str, Any]:
    payload = config.to_dict()
    payload.pop("schema_version", None)
    payload.pop("config_id", None)
    payload.pop("brain_enabled", None)
    payload.pop("notes", None)
    return payload


def _validate_configs(configs: tuple[BenchmarkConfig, ...]) -> BenchmarkConfig:
    if not configs:
        raise ValueError("configs JSON must contain at least one config")
    canonical = configs[0]
    payload = _shared_config_payload(canonical)
    for config in configs[1:]:
        if config.provider.casefold() != canonical.provider.casefold():
            raise ValueError("all benchmark configs must share the same provider")
        if config.model != canonical.model:
            raise ValueError("all benchmark configs must share the same model")
        if _shared_config_payload(config) != payload:
            raise ValueError(
                "benchmark configs must match on model/provider settings, limits and knowledge policy; "
                "only config_id, brain_enabled and notes may differ"
            )
    return canonical


def _provider_setting(source: dict[str, str], key: str, fallback: Any) -> Any:
    value = source.get(key)
    if value is None or not str(value).strip():
        return fallback
    return value


def _build_provider(config: BenchmarkConfig, *, budget_guard: LunaBudgetGuard | None = None) -> Any:
    env = os.environ
    provider_name = env.get("PD_AGENT_PROVIDER", config.provider).strip().lower()
    model = env.get("PD_AGENT_MODEL", config.model).strip()
    if provider_name != config.provider.casefold():
        raise ValueError(
            f"PD_AGENT_PROVIDER must match benchmark configs: env={provider_name!r} config={config.provider!r}"
        )
    if model != config.model:
        raise ValueError(f"PD_AGENT_MODEL must match benchmark configs: env={model!r} config={config.model!r}")

    provider_config = dict(config.provider_config)
    timeout_seconds = float(
        _provider_setting(env, "PD_AGENT_PROVIDER_TIMEOUT_SECONDS", provider_config.get("timeout_seconds", 60))
    )
    retry_limit = int(
        _provider_setting(env, "PD_AGENT_PROVIDER_RETRY_LIMIT", provider_config.get("provider_retry_limit", 2))
    )

    if provider_name == "gemini":
        api_key = env.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY missing")
        return GeminiProvider(
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            provider_retry_limit=retry_limit,
        )
    if provider_name == "openai":
        api_key = env.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY missing")
        return OpenAIProvider(
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            provider_retry_limit=retry_limit,
            budget_guard=budget_guard or LunaBudgetGuard(experimental=False, non_official=False),
        )
    raise ValueError(f"unsupported provider: {provider_name}")


def _build_request_pacer() -> BenchmarkRequestPacer:
    return BenchmarkRequestPacer(
        min_interval_seconds=MIN_PROVIDER_INTERVAL_SECONDS,
        daily_request_budget=GEMINI_DAILY_REQUEST_BUDGET,
    )


def _wrap_provider_for_benchmark(provider: Any, pacer: BenchmarkRequestPacer) -> BenchmarkPacedProvider:
    return BenchmarkPacedProvider(provider=provider, pacer=pacer)


def _build_knowledge_source(configs: tuple[BenchmarkConfig, ...]) -> YarnKnowledgeSource | None:
    if any(config.brain_enabled for config in configs):
        return YarnKnowledgeSource()
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PD Agent v0.4 benchmarks")
    parser.add_argument("--catalog-root", required=True, type=Path)
    parser.add_argument("--resume", type=Path, default=None)
    parser.add_argument("--dataset-id", default=None)
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--configs-json", type=Path, default=None)
    parser.add_argument("--execution-root", type=Path, default=None)
    parser.add_argument("--gradle-seed-root", type=Path, default=None)
    parser.add_argument("--gradle-seed-manifest", required=False, type=Path, default=None)
    parser.add_argument("--pd-agent-commit", default=None)
    parser.add_argument("--target-valid-repetitions", type=int, default=3)
    parser.add_argument("--max-attempts-per-cell", type=int, default=5)
    parser.add_argument("--scheduling-seed", type=int, default=None)
    parser.add_argument(
        "--shared-economic-state",
        type=Path,
        default=None,
        help="Persist one I16 economic ceiling shared by separate executions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = BenchmarkCatalog.load(args.catalog_root)

    if args.resume is not None:
        execution_dir = args.resume.resolve(strict=True)
        if args.execution_root is not None and execution_dir.parent.resolve(strict=False) != args.execution_root.resolve(strict=False):
            raise ValueError("--execution-root must match the parent of --resume when both are provided")
        manifest = BenchmarkExecutionManifest.from_dict(json.loads((execution_dir / "manifest.json").read_text(encoding="utf-8")))
        configs = manifest.configs
        canonical_config = _validate_configs(configs)
        execution_root = execution_dir.parent
        gradle_environment = BenchmarkGradleEnvironment.restore(execution_root=execution_root)
    else:
        if args.dataset_id is None or args.dataset_version is None or args.configs_json is None or args.execution_root is None or args.gradle_seed_root is None:
            raise ValueError("dataset-id, dataset-version, configs-json, execution-root and gradle-seed-root are required unless --resume is used")
        configs = _load_configs(args.configs_json)
        canonical_config = _validate_configs(configs)
        execution_root = args.execution_root
        execution_root.mkdir(parents=True, exist_ok=True)
        gradle_environment = BenchmarkGradleEnvironment.prepare(
            seed_root=args.gradle_seed_root,
            execution_root=execution_root,
            seed_manifest_path=args.gradle_seed_manifest,
            offline=True,
        )

    shared_session = (
        LunaSharedBudgetSession.open_or_create(args.shared_economic_state)
        if args.shared_economic_state is not None
        else None
    )
    if shared_session is not None and canonical_config.provider.casefold() != "openai":
        raise ValueError("--shared-economic-state is supported only for OpenAI I16 runs")
    shared_guard = (
        shared_session.guard(consumer_id=canonical_config.config_id)
        if shared_session is not None
        else None
    )
    provider = _build_provider(canonical_config)
    if shared_guard is not None:
        provider = _build_provider(canonical_config, budget_guard=shared_guard)
    provider = _wrap_provider_for_benchmark(provider, _build_request_pacer())
    knowledge_source = _build_knowledge_source(configs)
    repo_root = Path(__file__).resolve().parents[2]
    minecraft_runner = MinecraftTestRunner(
        project_root=execution_root,
        harness_root=repo_root / "tests" / "fixtures" / "l11_minecraft_harness",
        environment_overrides=gradle_environment.environment_overrides,
    )
    executor = BenchmarkExecutor(
        provider=provider,
        build_runner=GradleBuildRunner(environment_overrides=gradle_environment.environment_overrides),
        artifact_validator=ArtifactValidator(),
        tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        knowledge_source=knowledge_source,
        minecraft_runner=minecraft_runner,
        gradle_environment=gradle_environment,
    )
    runner = BenchmarkExecutionRunner(
        executor=executor,
        target_valid_repetitions=args.target_valid_repetitions,
        max_attempts_per_cell=args.max_attempts_per_cell,
        scheduling_seed=args.scheduling_seed,
    )
    if args.resume is not None:
        batch = runner.resume(
            catalog,
            execution_dir=execution_dir,
            pd_agent_commit=args.pd_agent_commit,
        )
    else:
        batch = runner.run(
            catalog,
            dataset_id=args.dataset_id,
            dataset_version=args.dataset_version,
            configs=configs,
            execution_root=execution_root,
            pd_agent_commit=args.pd_agent_commit,
        )
    print(batch.comparison_json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
