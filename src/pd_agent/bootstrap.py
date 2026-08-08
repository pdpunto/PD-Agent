"""Composition helpers for the PD Agent CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pd_agent.artifacts import ArtifactValidator
from pd_agent.build import GradleBuildRunner
from pd_agent.config import AppConfig
from pd_agent.context import ContextManager
from pd_agent.core.errors import ConfigurationError
from pd_agent.providers import OpenAIProvider
from pd_agent.reporting import RunStorage
from pd_agent.runtime import RunController


@dataclass(frozen=True, slots=True)
class RuntimeBundle:
    """CLI wiring bundle."""

    config: AppConfig
    storage: RunStorage
    controller: RunController
    provider: Any


def create_openai_provider(config: AppConfig) -> OpenAIProvider:
    """Create the only v0.1 provider adapter."""

    if config.provider != "openai":
        raise ConfigurationError(f"unsupported provider: {config.provider}")
    if not config.model:
        raise ConfigurationError("OpenAI model is required")
    if not config.openai_api_key:
        raise ConfigurationError("OPENAI_API_KEY is required")
    return OpenAIProvider(
        model=config.model,
        api_key=config.openai_api_key,
        provider_retry_limit=config.execution_limits.provider_retry_limit,
    )


def build_runtime_bundle(
    config: AppConfig,
    *,
    provider_factory: Callable[[AppConfig], Any] = create_openai_provider,
    storage: RunStorage | None = None,
    build_runner: GradleBuildRunner | None = None,
    artifact_validator: ArtifactValidator | None = None,
    context_manager: ContextManager | None = None,
    controller_factory: Callable[..., RunController] = RunController,
) -> RuntimeBundle:
    """Compose the runtime graph outside the core runtime."""

    storage = storage or RunStorage(config.runs_dir)
    provider = provider_factory(config)
    controller = controller_factory(
        provider=provider,
        storage=storage,
        build_runner=build_runner or GradleBuildRunner(reporting=storage),
        artifact_validator=artifact_validator or ArtifactValidator(reporting=storage),
        context_manager=context_manager or ContextManager(),
        limits=config.execution_limits,
        model_config={},
    )
    return RuntimeBundle(config=config, storage=storage, controller=controller, provider=provider)
