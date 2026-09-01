"""Productive v0.9 application composition root."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from pd_agent.bootstrap import RuntimeBundle, build_runtime_bundle
from pd_agent.brain import FrozenKnowledgePackSource, KnowledgeEnvironment, KnowledgeService, load_frozen_knowledge_pack
from pd_agent.config import AppConfig, load_config
from pd_agent.fabric import FabricNormalOrchestrator
from pd_agent.experimental import LunaSharedBudgetSession

from .catalog import ProductCatalog
from .delivery import DeliveryService
from .evidence import EvidenceService
from .execution import ExecutionService
from .fabric import FabricProductExecutionRunner, ProductFabricTaskContractResolver
from .projects import ProjectService


@dataclass(slots=True)
class ProductApplication:
    """Own application-scoped services without owning a second lifecycle."""

    catalog: ProductCatalog
    project_service: ProjectService
    execution_service: ExecutionService
    evidence_service: EvidenceService
    delivery_service: DeliveryService
    fabric_resolver: ProductFabricTaskContractResolver
    fabric_runner: FabricProductExecutionRunner
    fabric_orchestrator: FabricNormalOrchestrator
    runtime: RuntimeBundle
    web_services: WebServices
    _shutdown: bool = False
    _lock: RLock | None = None

    def __post_init__(self) -> None:
        if self._lock is None:
            self._lock = RLock()

    def shutdown(self, *, wait: bool = True) -> None:
        """Close owned background resources once; no execution is fabricated."""
        lock = self._lock
        if lock is None:  # pragma: no cover - defensive for unusual construction
            return
        with lock:
            if self._shutdown:
                return
            self._shutdown = True
        self.execution_service.shutdown(wait=wait)

    close = shutdown


def build_product_application(
    config: AppConfig | None = None,
    *,
    catalog: ProductCatalog | None = None,
    storage: Any | None = None,
    provider_factory: Callable[[AppConfig], Any] | None = None,
    build_runner: Any | None = None,
    artifact_validator: Any | None = None,
    context_manager: Any | None = None,
    economic_budget_usd: Decimal | str | None = None,
    economic_session: LunaSharedBudgetSession | None = None,
    attempt_ceiling_usd: Decimal | str | None = None,
    product_data_root: Path | str | None = None,
    minecraft_runner: Any | None = None,
    minecraft_runner_factory: Callable[[Path], Any] | None = None,
    gradle_user_home: Path | str | None = None,
    minecraft_harness_root: Path | str | None = None,
    knowledge_service: KnowledgeService | None = None,
    knowledge_pack_path: Path | str | None = None,
    knowledge_pack_id: str | None = None,
) -> ProductApplication:
    """Construct the real product graph without starting any work."""
    config = config or load_config()
    from pd_agent.web import WebServices

    runtime = build_runtime_bundle(
        config,
        provider_factory=provider_factory or _default_provider_factory(),
        storage=storage,
        build_runner=build_runner,
        artifact_validator=artifact_validator,
        context_manager=context_manager,
        economic_budget_usd=economic_budget_usd,
        economic_session=economic_session,
        attempt_ceiling_usd=attempt_ceiling_usd,
    )
    runtime.controller.model_config = {
        "max_output_tokens": 16_384,
        "reasoning": {"effort": "medium"},
        "service_tier": "default",
    }
    if knowledge_service is not None and knowledge_pack_path is not None:
        raise ValueError("knowledge service and knowledge pack cannot both be provided")
    productive_knowledge = knowledge_service
    if knowledge_pack_path is not None:
        pack = load_frozen_knowledge_pack(knowledge_pack_path, expected_pack_id=knowledge_pack_id)
        productive_knowledge = KnowledgeService((FrozenKnowledgePackSource(pack),))
    catalog = catalog or ProductCatalog(product_data_root or config.runs_dir.parent / "product-data")
    projects = ProjectService(catalog)
    resolver = ProductFabricTaskContractResolver()
    effective_gradle_home = (
        Path(gradle_user_home)
        if gradle_user_home is not None
        else Path(os.environ["GRADLE_USER_HOME"])
        if os.environ.get("GRADLE_USER_HOME")
        else Path.home() / ".gradle"
    )
    effective_minecraft_runner_factory = minecraft_runner_factory
    if minecraft_runner is None and effective_minecraft_runner_factory is None:
        from pd_agent.minecraft import MinecraftTestRunner

        effective_harness_root = (
            Path(minecraft_harness_root)
            if minecraft_harness_root is not None
            else Path(os.environ["PD_AGENT_MINECRAFT_HARNESS_ROOT"])
            if os.environ.get("PD_AGENT_MINECRAFT_HARNESS_ROOT")
            else Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "l11_minecraft_harness"
        )
        effective_minecraft_runner_factory = lambda root: MinecraftTestRunner(
            project_root=root,
            harness_root=effective_harness_root,
        )
    orchestrator = FabricNormalOrchestrator(
        provider=runtime.provider,
        build_runner=runtime.controller.build_runner,
        artifact_validator=runtime.controller.artifact_validator,
        context_manager=runtime.controller.context_manager,
        project_inspector=runtime.controller.project_inspector,
        tool_executor=runtime.controller.tool_executor,
        reporting=runtime.storage,
        model_config=runtime.controller.model_config,
        limits=runtime.controller.limits,
        pre_build_validator=runtime.controller.pre_build_validator,
        functional_validator=runtime.controller.functional_validator,
        knowledge_service=productive_knowledge,
        repair_knowledge_source=(productive_knowledge.sources[0] if productive_knowledge is not None else None),
        repair_knowledge_environment=KnowledgeEnvironment(),
        validation_contract=None,
        minecraft_runner=minecraft_runner,
        minecraft_runner_factory=effective_minecraft_runner_factory,
        gradle_user_home=effective_gradle_home,
    )
    fabric_runner = FabricProductExecutionRunner(
        orchestrator=orchestrator,
        resolver=resolver,
        inspector=runtime.controller.project_inspector,
    )
    delivery = DeliveryService(catalog, runtime.storage)
    execution = ExecutionService(
        catalog,
        runtime.controller,
        projects,
        product_runner=fabric_runner,
        delivery_service=delivery,
    )
    evidence = EvidenceService(runtime.storage, execution)
    application = ProductApplication(
        catalog=catalog,
        project_service=projects,
        execution_service=execution,
        evidence_service=evidence,
        delivery_service=delivery,
        fabric_resolver=resolver,
        fabric_runner=fabric_runner,
        fabric_orchestrator=orchestrator,
        runtime=runtime,
        web_services=WebServices(project=projects, execution=execution, evidence=evidence, delivery=delivery),
    )
    object.__setattr__(application.web_services, "application", application)
    return application


def _default_provider_factory() -> Callable[[AppConfig], Any]:
    from pd_agent.bootstrap import create_provider

    return create_provider


__all__ = ["ProductApplication", "build_product_application"]
