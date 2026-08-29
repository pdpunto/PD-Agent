"""Thin, fail-closed I16 validation driver.

This driver owns one integrated validation run, not benchmark scheduling or
aggregation. PRECHECK and DRY-RUN never construct a provider request or start
Minecraft; LIVE requires both explicit mode and authorization flags.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping
from uuid import uuid4

from pd_agent.project import ProjectInspectionStatus, ProjectInspector, resolve_logical_resource_path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_FIXTURE = "3c27fd809429bc57637b3d930733d5cc7c1891073e9307325d30d25058161396"
EXPECTED_SEED = "eb211b00633cbbc909d2494c777c1070ad0db668aa0e64896e9691d2f3bfba83"
EXPECTED_PACK = "9f1ef7ac14fa63b79aa8ef3decd1fce232729b4eefee6f2292382db4f3f4f3a5"
EXPECTED_CONFIG_ID = "openai-official-gpt-5.6-luna-brain-on"
EXPECTED_TASK_ID = "F6-T3"


class PrecheckError(ValueError):
    """A fail-closed preflight violation."""


def _parse_global_budget_ceiling(value: str) -> Decimal:
    try:
        ceiling = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError("global budget ceiling must be a decimal") from exc
    if not ceiling.is_finite() or ceiling <= 0:
        raise argparse.ArgumentTypeError("global budget ceiling must be positive and finite")
    return ceiling


def _runtime_observation(
    observation_id: str,
    observation_type: str,
    observation_params: Mapping[str, Any],
    requirement_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Map I16 acceptance data to the closed productive observation envelope."""

    if observation_type != "REGISTRY_ENTRY_PRESENT":
        raise PrecheckError(f"unsupported I16 observation type: {observation_type}")
    if set(observation_params) != {"registry_kind", "identifier"}:
        raise PrecheckError("I16 registry observation parameters are incomplete")
    if not requirement_ids:
        raise PrecheckError("I16 runtime observation requires requirement IDs")
    return {
        "observation_id": observation_id,
        "observation_type": observation_type,
        "profile": "registry_entry",
        "selector": {
            "kind": "registry",
            "registry_kind": observation_params["registry_kind"],
            "identifier": observation_params["identifier"],
        },
        "expected": {"present": True},
        "parameters": {},
        "phase": "RUNTIME",
        "metadata": {},
        "requirement_ids": list(requirement_ids),
    }


def validate_baseline(expected: str | None, state: Mapping[str, Any]) -> None:
    """Require an explicit commit that matches both local and remote main."""

    if not expected:
        raise PrecheckError("pd-agent commit must be supplied explicitly")
    if expected != state.get("head") or expected != state.get("origin_main"):
        raise PrecheckError("repository baseline or cleanliness mismatch")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PrecheckError(f"JSON object required: {path}")
    return value


def _fixture_identity(root: Path) -> str:
    ignored_dirs = {".git", ".gradle", "build", "dist", "runs", "validation_runs", "__pycache__", ".pytest_cache"}
    ignored_files = {".DS_Store", "Thumbs.db"}
    text_suffixes = {".bat", ".cmd", ".gradle", ".java", ".json", ".kts", ".md", ".properties", ".sh", ".txt", ".xml", ".yaml", ".yml"}
    digest = hashlib.sha256()
    for current, dirs, files in os.walk(root, topdown=True):
        dirs[:] = sorted((d for d in dirs if d.casefold() not in ignored_dirs), key=str.casefold)
        for name in sorted(files, key=str.casefold):
            if name in ignored_files:
                continue
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                raise PrecheckError(f"fixture contains invalid file: {path}")
            relative = path.relative_to(root).as_posix()
            data = path.read_bytes()
            if path.name.casefold() == "gradlew" or path.suffix.casefold() in text_suffixes:
                data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(data)
            digest.update(b"\0")
    return digest.hexdigest()


def _git_state(repo_root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(("git", *args), cwd=repo_root, text=True, capture_output=True, check=True)
        return result.stdout.strip()

    status = git("status", "--short")
    unexpected = [line for line in status.splitlines() if line and not line.startswith("?? scripts/benchmark/diagnostics/")]
    return {"head": git("rev-parse", "HEAD"), "origin_main": git("rev-parse", "origin/main"), "status": status, "tracked_clean": not unexpected}


def validate_config(config: Mapping[str, Any]) -> None:
    model_config = config.get("model_config", {})
    limits = config.get("execution_limits", {})
    if config.get("config_id") != EXPECTED_CONFIG_ID or config.get("provider") != "openai" or config.get("model") != "gpt-5.6-luna":
        raise PrecheckError("provider/model/config identity mismatch")
    if config.get("brain_enabled") is not True:
        raise PrecheckError("I16 requires Brain ON")
    if model_config.get("reasoning", {}).get("effort") != "medium" or model_config.get("service_tier") != "default" or model_config.get("store") is not False or model_config.get("max_output_tokens") != 16384:
        raise PrecheckError("frozen model configuration mismatch")
    expected_limits = {"max_agent_steps": 25, "max_tool_calls": 50, "max_build_attempts": 5, "max_context_bytes": 2_000_000, "max_tool_output_bytes": 1_000_000, "process_timeout_seconds": 600, "provider_retry_limit": 2}
    if any(limits.get(key) != value for key, value in expected_limits.items()):
        raise PrecheckError("execution limits mismatch")


def validate_task(task: Mapping[str, Any], fixture_root: Path) -> dict[str, Any]:
    if task.get("task_id") != EXPECTED_TASK_ID or str(task.get("task_version")) != "5":
        raise PrecheckError("task identity mismatch")
    fixture = task.get("fixture", {})
    if fixture.get("fixture_identity") != EXPECTED_FIXTURE or fixture.get("identity_algorithm") != "sha256-tree-v2":
        raise PrecheckError("fixture contract mismatch")
    actual = _fixture_identity(fixture_root)
    if actual != EXPECTED_FIXTURE:
        raise PrecheckError(f"fixture identity mismatch: {actual}")
    snapshot = ProjectInspector().inspect(fixture_root)
    if snapshot.status is not ProjectInspectionStatus.READY:
        raise PrecheckError(f"fixture project inspection blocked: {snapshot.issues}")
    spec = task["acceptance"]["spec"]
    targets = ["role:source"]
    for item in spec.get("required_resources", []):
        try:
            targets.append(resolve_logical_resource_path(snapshot, item["path"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise PrecheckError(f"resource target cannot be resolved: {item!r}") from exc
    return {"targets": tuple(dict.fromkeys(targets)), "spec": spec, "resource_roots": tuple(snapshot.resource_roots)}


def validate_seed(seed_root: Path, manifest_path: Path) -> None:
    from pd_agent.core import portable_seed_identity

    manifest = _load_json(manifest_path)
    identity = portable_seed_identity(seed_root)
    if identity != EXPECTED_SEED or manifest.get("identity_hash") != EXPECTED_SEED:
        raise PrecheckError("Gradle seed identity mismatch")
    if manifest.get("component_count") != 10453:
        raise PrecheckError("Gradle seed component count mismatch")
    jar = seed_root / "caches" / "fabric-loom" / "1.21.11" / "minecraft-server.jar"
    if not jar.is_file() or hashlib.sha256(jar.read_bytes()).hexdigest().upper() != "F83B8E093865806F931C7E34AAE41B177D4C076335263DD124C75D6D65DD1726":
        raise PrecheckError("minecraft-server.jar identity mismatch")


def validate_pack(pack_path: Path) -> None:
    from pd_agent.brain.frozen import load_frozen_knowledge_pack

    load_frozen_knowledge_pack(pack_path, expected_pack_id=EXPECTED_PACK)


def validate_budget(path: Path, expected_global_ceiling: Decimal | str) -> dict[str, Any]:
    from pd_agent.experimental.luna_budget import LunaSharedBudgetSession

    expected_ceiling = Decimal(str(expected_global_ceiling))
    session = LunaSharedBudgetSession.load(path, expected_global_ceiling=expected_ceiling)
    if session.ceiling_usd != expected_ceiling or session.state.global_remaining_usd < 0:
        raise PrecheckError("shared I16 budget is not valid")
    if session.state.reconciliation_state == "UNCERTAIN_CONSUMED":
        raise PrecheckError("shared I16 budget is uncertain")
    if session.state.active_attempt_id is not None and (
        session.state.attempt_accumulated_usd
        or session.state.attempt_reserved_usd
        or session.state.attempt_uncertain_consumed_usd
    ):
        raise PrecheckError("shared I16 budget has an active consumed attempt")
    probe = session.preview_budget(
        consumer_id="precheck",
        input_tokens=0,
        output_limit=16384,
    )
    if probe["decision"] != "ALLOW":
        raise PrecheckError(
            "shared I16 budget blocks the next request: "
            f"required={probe['reservation_usd']} "
            f"attempt_remaining={probe['attempt_remaining_usd']} "
            f"global_remaining={probe['global_remaining_usd']}"
        )
    return {
        "session_id": session.session_id,
        "global_ceiling_usd": str(session.ceiling_usd),
        "remaining_usd": str(session.state.global_remaining_usd),
        "next_request_probe": probe,
    }


def build_contract(task: Mapping[str, Any], fixture_root: Path) -> Any:
    from pd_agent.core import FabricEnvironmentConstraints, FabricKnowledgeSignal, FabricMutationExpectation, FabricRequirement, FabricTaskContract, FabricValidationRequirement

    spec = task["acceptance"]["spec"]
    environment = task["environment"]
    observations = [_runtime_observation("F6-T3:primary", spec["observation_type"], spec["observation_params"], ("runtime",))]
    observations.extend(
        _runtime_observation(item["test_id"], item["observation_type"], item["observation_params"], ("runtime",))
        for item in spec["required_minecraft_observations"]
    )
    requirements = tuple(FabricRequirement(requirement_id=key, description=value) for key, value in {"source": task["prompt"], "build": "Build the changed Fabric project.", "artifact": "Produce a current valid artifact.", "runtime": "Validate the required Minecraft observations."}.items())
    validation = FabricValidationRequirement(validation_requirement_id="minecraft-runtime", requirement_ids=("runtime",), kind="minecraft", spec={"target_mod_id": "examplemod", "minecraft_version": environment["minecraft_version"], "loader_version": environment["loader_version"], "test_id": "F6-T3", "observation_type": spec["observation_type"], "observation_params": spec["observation_params"], "observations": observations})
    snapshot = ProjectInspector().inspect(fixture_root)
    mutations = tuple(
        FabricMutationExpectation(expectation_id=f"F6-T3:{path}", role="source", path=path)
        for path in [
            "src/main/java",
            *[resolve_logical_resource_path(snapshot, item["path"]) for item in spec["required_resources"]],
        ]
    )
    return FabricTaskContract(task_id="F6-T3@5", revision="5", goal=task["prompt"], requirements=requirements, required_capabilities=("Fabric 1.21.11", "craftable utility block"), validation_requirements=(validation,), knowledge_signals=tuple(FabricKnowledgeSignal(signal_id=item["id"], query=item["query"], category=item["type"]) for item in spec["knowledge_needs"]), mutation_expectations=mutations, environment_constraints=FabricEnvironmentConstraints(minecraft_version=environment["minecraft_version"], loader_version=environment["loader_version"], fabric_api_version=environment["fabric_api_version"], yarn_version=environment["yarn_version"], java_version=environment["java_version"], extra={"loom_version": environment["loom_version"]}))


def _redacted_manifest(path: Path, args: argparse.Namespace, config: Mapping[str, Any], task: Mapping[str, Any]) -> None:
    payload = {"schema_version": 1, "mode": args.mode.upper(), "experimental": bool(getattr(args, "experimental", False)), "non_official": bool(getattr(args, "non_official", False)), "task_id": task["task_id"], "config_id": config["config_id"], "provider": config["provider"], "model": config["model"], "brain_enabled": config["brain_enabled"], "authorization": bool(args.authorize_i16), "api_key_present": bool(os.environ.get("OPENAI_API_KEY")), "secret_values_persisted": False}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def precheck(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo_root).resolve()
    config = _load_json(Path(args.config_json))
    task = _load_json(Path(args.task_json))
    state = _git_state(repo)
    validate_baseline(args.pd_agent_commit, state)
    if not state["tracked_clean"]:
        raise PrecheckError("repository baseline or cleanliness mismatch")
    validate_config(config)
    task_info = validate_task(task, Path(args.fixture_root).resolve())
    validate_seed(Path(args.seed_root).resolve(), Path(args.seed_manifest).resolve())
    validate_pack(Path(args.knowledge_pack).resolve())
    budget = validate_budget(Path(args.budget_state).resolve(), args.global_budget_ceiling)
    if not os.environ.get("OPENAI_API_KEY"):
        raise PrecheckError("OPENAI_API_KEY is not present")
    launch = Path(args.launch_root).resolve()
    if launch.exists() or (launch / "ExecutionRoot").exists():
        raise PrecheckError("LaunchRoot must be new")
    return {"baseline": state["head"], "config_id": config["config_id"], "task_id": task["task_id"], "fixture_identity": EXPECTED_FIXTURE, "seed_identity": EXPECTED_SEED, "knowledge_pack": EXPECTED_PACK, "mutation_targets": list(task_info["targets"]), "budget": budget, "launch_root": str(launch), "api_key_present": True}


def run_live(args: argparse.Namespace, checks: Mapping[str, Any]) -> dict[str, Any]:
    from pd_agent.artifacts import ArtifactValidator
    from pd_agent.bootstrap import FabricBootstrap
    from pd_agent.brain import FrozenKnowledgePackSource, KnowledgeEnvironment, KnowledgeService, load_frozen_knowledge_pack
    from pd_agent.build import GradleBuildRunner
    from pd_agent.context import ContextManager
    from pd_agent.fabric import FabricNormalOrchestrator
    from pd_agent.minecraft import MinecraftTestRunner
    from pd_agent.providers.openai_provider import OpenAIProvider
    from pd_agent.reporting import RunStorage
    from pd_agent.core import ExecutionLimits
    from pd_agent.validation import PreBuildWorkspaceValidator
    from pd_agent.experimental.luna_budget import LunaSharedBudgetSession

    launch = Path(checks["launch_root"])
    launch.mkdir(parents=True, exist_ok=False)
    execution_root = launch / "ExecutionRoot"
    execution_root.mkdir()
    run_id = str(uuid4())
    workspace = execution_root / "workspace"
    shutil.copytree(args.fixture_root, workspace)
    gradle_home = execution_root / "environment" / "gradle-user-home"
    shutil.copytree(args.seed_root, gradle_home)
    config = _load_json(Path(args.config_json))
    task = _load_json(Path(args.task_json))
    pack = load_frozen_knowledge_pack(args.knowledge_pack, expected_pack_id=EXPECTED_PACK)
    storage = RunStorage(execution_root / "evidence", secrets=(os.environ["OPENAI_API_KEY"],))
    budget_session = LunaSharedBudgetSession.load(
        args.budget_state,
        expected_global_ceiling=args.global_budget_ceiling,
    )
    budget_guard = budget_session.guard(
        consumer_id=run_id,
        experimental=bool(args.experimental),
        non_official=bool(args.non_official),
    )
    budget_guard.begin_attempt(run_id)
    provider = OpenAIProvider(model=config["model"], api_key=os.environ["OPENAI_API_KEY"], provider_retry_limit=2, service_tier="default", budget_guard=budget_guard)
    environment = KnowledgeEnvironment.from_dict(task["acceptance"]["spec"]["knowledge_needs"][0]["environment"])
    snapshot = ProjectInspector().inspect(workspace)
    orchestrator = FabricNormalOrchestrator(provider=provider, build_runner=GradleBuildRunner(reporting=storage, environment_overrides={"GRADLE_USER_HOME": str(gradle_home)}), artifact_validator=ArtifactValidator(reporting=storage), context_manager=ContextManager(), limits=ExecutionLimits.from_dict(config["execution_limits"]), model_config=config["model_config"], reporting=storage, knowledge_service=KnowledgeService((FrozenKnowledgePackSource(pack),)), knowledge_environment=environment, pre_build_validator=PreBuildWorkspaceValidator(resource_roots=tuple(snapshot.resource_roots)), validation_contract=task["acceptance"]["spec"], minecraft_runner=MinecraftTestRunner(project_root=workspace, evidence_root=execution_root / "minecraft", harness_root=REPO_ROOT / "tests" / "fixtures" / "l11_minecraft_harness", environment_overrides={"GRADLE_USER_HOME": str(gradle_home)}))
    contract = build_contract(task, workspace)
    result = orchestrator.run(contract, workspace, brain_enabled=True, pending_mutation_targets=tuple(checks["mutation_targets"]))
    budget_guard.end_attempt()
    _redacted_manifest(launch / "i16-manifest.json", args, config, task)
    return {"execution_id": run_id, "result": result.to_dict(), "manifest": str(launch / "i16-manifest.json")}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("precheck", "dry-run", "live"), default="precheck")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--task-json", type=Path, default=REPO_ROOT / "benchmarks/tasks/F6-T3-v5.json")
    parser.add_argument("--config-json", type=Path, default=REPO_ROOT / "benchmarks/configs/openai-official-gpt-5.6-luna-brain-on.json")
    parser.add_argument("--fixture-root", type=Path, default=REPO_ROOT / "benchmarks/projects/v0_5_fabric_base")
    parser.add_argument("--seed-root", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--knowledge-pack", type=Path, required=True)
    parser.add_argument("--budget-state", type=Path, required=True)
    parser.add_argument("--global-budget-ceiling", type=_parse_global_budget_ceiling, required=True)
    parser.add_argument("--gradle-home", type=Path, required=True, help="reserved fresh Gradle-home path; LIVE uses ExecutionRoot/environment/gradle-user-home")
    parser.add_argument("--launch-root", type=Path, required=True)
    parser.add_argument("--pd-agent-commit", default=None)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--authorize-i16", action="store_true")
    parser.add_argument("--experimental", action="store_true")
    parser.add_argument("--non-official", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "live" and not args.live:
        raise SystemExit("LIVE requires --live")
    if args.mode == "live" and not args.authorize_i16:
        raise SystemExit("LIVE requires --authorize-i16")
    try:
        checks = precheck(args)
        if args.mode != "live":
            print(json.dumps({"status": "PRECHECK_PASS", **checks}, indent=2, sort_keys=True))
            return 0
        print(json.dumps(run_live(args, checks), indent=2, sort_keys=True, default=str))
        return 0
    except (PrecheckError, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
