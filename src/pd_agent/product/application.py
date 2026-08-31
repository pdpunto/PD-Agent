"""Productive v0.9 application composition root."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from pd_agent.bootstrap import RuntimeBundle, build_runtime_bundle
from pd_agent.config import AppConfig, load_config
from pd_agent.fabric import FabricNormalOrchestrator

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
    product_data_root: Path | str | None = None,
    minecraft_runner: Any | None = None,
    minecraft_runner_factory: Callable[[Path], Any] | None = None,
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
    )
    runtime.controller.model_config = {
        "max_output_tokens": 16_384,
        "reasoning": {"effort": "medium"},
        "service_tier": "default",
    }
    catalog = catalog or ProductCatalog(product_data_root or config.runs_dir.parent / "product-data")
    projects = ProjectService(catalog)
    resolver = ProductFabricTaskContractResolver()
    effective_minecraft_runner_factory = minecraft_runner_factory
    if minecraft_runner is None and effective_minecraft_runner_factory is None:
        from pd_agent.minecraft import MinecraftTestRunner

        effective_minecraft_runner_factory = lambda root: MinecraftTestRunner(project_root=root)
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
        validation_contract=None,
        repair_knowledge_source=runtime.controller.repair_knowledge_source,
        repair_knowledge_environment=runtime.controller.repair_knowledge_environment,
        minecraft_runner=minecraft_runner,
        minecraft_runner_factory=effective_minecraft_runner_factory,
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
