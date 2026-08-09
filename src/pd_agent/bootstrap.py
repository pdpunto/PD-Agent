"""Composition helpers for the PD Agent CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pd_agent.artifacts import ArtifactValidator
from pd_agent.build import GradleBuildRunner
from pd_agent.config import AppConfig
from pd_agent.context import ContextManager
from pd_agent.core.errors import ConfigurationError
from pd_agent.providers import GeminiProvider, OpenAIProvider
from pd_agent.reporting import RunStorage
from pd_agent.reporting.redaction import Redactor
from pd_agent.runtime import RunController


@dataclass(frozen=True, slots=True)
class RuntimeBundle:
    """CLI wiring bundle."""

    config: AppConfig
    storage: RunStorage
    controller: RunController
    provider: Any


def create_openai_provider(config: AppConfig) -> OpenAIProvider:
    """Create the OpenAI provider adapter."""

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


def create_gemini_provider(config: AppConfig) -> GeminiProvider:
    """Create the Gemini provider adapter."""

    if config.provider != "gemini":
        raise ConfigurationError(f"unsupported provider: {config.provider}")
    if not config.model:
        raise ConfigurationError("Gemini model is required")
    if not config.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY is required")
    return GeminiProvider(
        model=config.model,
        api_key=config.gemini_api_key,
        timeout_seconds=float(config.execution_limits.process_timeout_seconds),
        provider_retry_limit=config.execution_limits.provider_retry_limit,
    )


def create_provider(config: AppConfig) -> Any:
    """Create the configured provider adapter."""

    if config.provider == "openai":
        return create_openai_provider(config)
    if config.provider == "gemini":
        return create_gemini_provider(config)
    raise ConfigurationError(f"unsupported provider: {config.provider}")


def build_runtime_bundle(
    config: AppConfig,
    *,
    provider_factory: Callable[[AppConfig], Any] = create_provider,
    storage: RunStorage | None = None,
    build_runner: GradleBuildRunner | None = None,
    artifact_validator: ArtifactValidator | None = None,
    context_manager: ContextManager | None = None,
    controller_factory: Callable[..., RunController] = RunController,
) -> RuntimeBundle:
    """Compose the runtime graph outside the core runtime."""

    storage = _configure_storage(
        storage,
        config.openai_api_key,
        config.gemini_api_key,
        config.runs_dir,
    )
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


def _configure_storage(
    storage: RunStorage | None,
    openai_api_key: str | None,
    gemini_api_key: str | None,
    runs_dir: Path,
) -> RunStorage:
    secrets = tuple(secret for secret in (openai_api_key, gemini_api_key) if secret)
    if storage is None:
        return RunStorage(runs_dir, secrets=secrets)
    if secrets:
        existing = getattr(storage.redactor, "secrets", ())
        storage.redactor = Redactor((*existing, *secrets))
    return storage
