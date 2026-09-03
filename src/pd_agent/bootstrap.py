"""Composition helpers for the PD Agent CLI and pinned Fabric bootstrap."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from pathlib import Path

from pd_agent.artifacts import ArtifactValidator
from pd_agent.build import GradleBuildRunner
from pd_agent.config import AppConfig
from pd_agent.context import ContextManager
from pd_agent.core.errors import ConfigurationError
from pd_agent.core import portable_seed_identity
from pd_agent.providers import GeminiProvider, OpenAIProvider
from pd_agent.experimental import LunaBudgetGuard, LunaEconomicState, LunaSharedBudgetSession
from pd_agent.reporting import RunEvent, RunEventType, RunStorage
from pd_agent.reporting.redaction import Redactor
from pd_agent.runtime import RunController
from pd_agent.project import ProjectInspectionStatus, ProjectInspector
from pd_agent.tools import SecurePathResolver
from pd_agent.validation import PreBuildWorkspaceValidator


class FabricBootstrapError(ValueError):
    """Fail-closed bootstrap validation error."""


class FabricBootstrapStatus(str):
    SUCCESS = "SUCCESS"
    ALREADY_INITIALIZED = "ALREADY_INITIALIZED"


@dataclass(frozen=True, slots=True)
class PinnedFabricVersions:
    """Legacy compatibility adapter for callers without an explicit profile."""

    minecraft: str = "1.21.11"
    loader: str = "0.19.3"
    fabric_api: str = "0.141.6+1.21.11"
    yarn: str | None = "1.21.11+build.6"
    java: int = 21
    loom: str = "1.13.3"
    mapping_family: str = "OBFUSCATED_REMAPPED"

    def to_dict(self) -> dict[str, object]:
        return {
            "minecraft": self.minecraft,
            "loader": self.loader,
            "fabric_api": self.fabric_api,
            "yarn": self.yarn,
            "java": self.java,
            "loom": self.loom,
        }


@dataclass(frozen=True, slots=True)
class FabricBootstrapResult:
    status: str
    workspace: Path
    mod_id: str
    package: str
    created_files: tuple[str, ...]
    project_fingerprint: str
    seed_identity: str | None
    manifest_path: Path
    inspection_status: str
    versions: PinnedFabricVersions
    platform_id: str | None = None
    template_id: str | None = None
    template_revision: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "bootstrap_schema_version": 1,
            "status": self.status,
            "workspace": str(self.workspace),
            "mod_id": self.mod_id,
            "package": self.package,
            "created_files": list(self.created_files),
            "project_fingerprint": self.project_fingerprint,
            "seed_identity": self.seed_identity,
            "manifest_path": str(self.manifest_path),
            "inspection_status": self.inspection_status,
            "versions": self.versions.to_dict(),
            "platform_id": self.platform_id,
            "template_id": self.template_id,
            "template_revision": self.template_revision,
        }


_MOD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_JAVA_SEGMENT_RE = re.compile(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$")
_JAVA_KEYWORDS = {
    "class", "enum", "interface", "public", "private", "protected", "static",
    "void", "int", "long", "float", "double", "boolean", "package", "import",
    "new", "return", "this", "null", "true", "false", "var", "record",
}


def _validate_mod_id(value: object) -> str:
    if not isinstance(value, str) or not _MOD_ID_RE.fullmatch(value) or ".." in value:
        raise FabricBootstrapError("invalid mod_id")
    return value


def _validate_package(value: object) -> str:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        raise FabricBootstrapError("invalid package")
    segments = value.split(".")
    if any(not _JAVA_SEGMENT_RE.fullmatch(segment) or segment in _JAVA_KEYWORDS for segment in segments):
        raise FabricBootstrapError("invalid package")
    return value


def _tree_identity(root: Path) -> str:
    try:
        return portable_seed_identity(root)
    except ValueError as exc:
        raise FabricBootstrapError(str(exc)) from exc


def _fingerprint_value(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return "sha256:" + hashlib.sha256(value).hexdigest()
    return value


class FabricBootstrap:
    """Create one deterministic, pinned Fabric project in an empty workspace."""

    def __init__(self, *, versions: PinnedFabricVersions | None = None) -> None:
        self.versions = versions or PinnedFabricVersions()

    def create(
        self,
        workspace: Path,
        *,
        mod_id: str,
        package: str,
        mod_name: str | None = None,
        seed_root: Path | None = None,
        expected_seed_identity: str | None = None,
        wrapper_source_root: Path | None = None,
        reporting: RunStorage | None = None,
        platform_profile: Any | None = None,
        project_template: Any | None = None,
    ) -> FabricBootstrapResult:
        workspace = Path(workspace)
        if workspace.exists():
            if workspace.is_symlink() or not workspace.is_dir():
                raise FabricBootstrapError("workspace must be a directory")
            if any(workspace.iterdir()):
                raise FabricBootstrapError(FabricBootstrapStatus.ALREADY_INITIALIZED)
        mod_id = _validate_mod_id(mod_id)
        package = _validate_package(package)
        if mod_name is not None and (not isinstance(mod_name, str) or not mod_name.strip()):
            raise FabricBootstrapError("invalid mod_name")

        profile = None
        template = None
        effective_versions = self.versions
        if platform_profile is not None or project_template is not None:
            from pd_agent.fabric import FabricPlatformProfile, FabricProjectTemplate

            if not isinstance(platform_profile, FabricPlatformProfile) or not isinstance(project_template, FabricProjectTemplate):
                raise FabricBootstrapError("platform_profile and project_template must be supplied together")
            if platform_profile.platform_id not in project_template.platform_ids:
                raise FabricBootstrapError("template platform mismatch")
            profile = platform_profile
            template = project_template
            effective_versions = PinnedFabricVersions(
                minecraft=profile.minecraft_version,
                loader=profile.loader_version,
                fabric_api=profile.fabric_api_version,
                yarn=profile.mappings_version,
                java=int(profile.java_version),
                loom=profile.loom_version,
                mapping_family=profile.mapping_family.value,
            )
            if template.seed_identity is not None and expected_seed_identity != template.seed_identity:
                raise FabricBootstrapError("template seed identity mismatch")

        seed_identity = None
        if expected_seed_identity is not None and seed_root is None:
            raise FabricBootstrapError("required Gradle seed is missing")
        if seed_root is not None:
            seed_root = Path(seed_root).resolve(strict=True)
            if not seed_root.is_dir():
                raise FabricBootstrapError("Gradle seed root must be a directory")
            seed_identity = _tree_identity(seed_root)
            if expected_seed_identity is not None and seed_identity != expected_seed_identity:
                raise FabricBootstrapError("Gradle seed identity mismatch")

        if not workspace.exists():
            workspace.mkdir(parents=True, exist_ok=False)

        resolver = SecurePathResolver(workspace)
        files: dict[str, str | bytes] = self._project_files(
            mod_id,
            package,
            mod_name or mod_id,
            versions=effective_versions,
        )
        if wrapper_source_root is not None:
            files.update(self._wrapper_files(Path(wrapper_source_root)))
        else:
            files.update(self._default_wrapper_files())

        relative_paths = tuple(sorted(files))
        fingerprint_payload = {
            "mod_id": mod_id,
            "package": package,
            "versions": effective_versions.to_dict(),
            "seed_identity": seed_identity,
            "files": [(path, _fingerprint_value(files[path])) for path in relative_paths],
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        manifest = {
            "bootstrap_schema_version": 1,
            "workspace_identity": fingerprint,
            "mod_id": mod_id,
            "package": package,
            "pinned_versions": effective_versions.to_dict(),
            "created_files": list(relative_paths) + ["bootstrap-manifest.json"],
            "seed_identity": seed_identity,
            "project_fingerprint": fingerprint,
            "timestamp": None,
        }
        if profile is not None and template is not None:
            manifest.update({
                "platform_id": profile.platform_id,
                "platform_identity": profile.identity,
                "template_id": template.template_id,
                "template_revision": template.template_revision,
            })
            manifest["mapping_family"] = profile.mapping_family.value
        files["bootstrap-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        created: list[Path] = []
        try:
            for relative in sorted(files):
                target, parent = resolver.resolve_parent_for_creation(relative)
                if target.exists():
                    raise FabricBootstrapError(f"generated path collision: {relative}")
                parent.mkdir(parents=True, exist_ok=True)
                content = files[relative]
                if isinstance(content, bytes):
                    target.write_bytes(content)
                else:
                    target.write_text(content, encoding="utf-8", newline="\n")
                created.append(target)
            snapshot = ProjectInspector().inspect(workspace)
            if snapshot.status != ProjectInspectionStatus.READY:
                raise FabricBootstrapError(f"generated project is not READY: {snapshot.issues}")
        except Exception:
            for target in reversed(created):
                try:
                    target.unlink()
                except OSError:
                    pass
            for directory in sorted({path.parent for path in created}, key=lambda item: len(item.parts), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise

        result = FabricBootstrapResult(
            status=FabricBootstrapStatus.SUCCESS,
            workspace=workspace.resolve(),
            mod_id=mod_id,
            package=package,
            created_files=tuple(sorted(files)),
            project_fingerprint=fingerprint,
            seed_identity=seed_identity,
            manifest_path=workspace / "bootstrap-manifest.json",
            inspection_status=snapshot.status.value,
            versions=effective_versions,
            platform_id=profile.platform_id if profile is not None else None,
            template_id=template.template_id if template is not None else None,
            template_revision=template.template_revision if template is not None else None,
        )
        if reporting is not None:
            reporting.append_event(
                RunEvent(
                    run_id=f"bootstrap-{fingerprint[:16]}",
                    event_type=RunEventType.BOOTSTRAP_COMPLETED,
                    payload={
                        "workspace_identity": fingerprint,
                        "mod_id": mod_id,
                        "package": package,
                        "pinned_versions": effective_versions.to_dict(),
                        "seed_identity": seed_identity,
                        "manifest_ref": "bootstrap-manifest.json",
                        "inspection_status": snapshot.status.value,
                    },
                )
            )
        return result

    def _project_files(
        self,
        mod_id: str,
        package: str,
        mod_name: str,
        *,
        versions: PinnedFabricVersions | None = None,
    ) -> dict[str, str | bytes]:
        v = versions or self.versions
        package_path = package.replace(".", "/")
        initializer = f"""package {package};

import net.fabricmc.api.ModInitializer;

public final class {self._class_name(mod_id)} implements ModInitializer {{
    public static final String MOD_ID = \"{mod_id}\";

    @Override
    public void onInitialize() {{
    }}
}}
"""
        mappings_dependency = (
            '    mappings("net.fabricmc:yarn:${property("mappings_version")}:v2")\n'
            if v.mapping_family == "OBFUSCATED_REMAPPED" else ""
        )
        mappings_property = "mappings_version=" + str(v.yarn) + "\n" if v.mapping_family == "OBFUSCATED_REMAPPED" else ""
        return {
            "settings.gradle.kts": f'pluginManagement {{ repositories {{ gradlePluginPortal(); maven("https://maven.fabricmc.net/") }} }}\nrootProject.name = "{mod_id}"\n',
            "build.gradle.kts": f'''plugins {{
    id("fabric-loom") version "{v.loom}"
}}

version = "1.0.0"

repositories {{ mavenCentral(); maven("https://maven.fabricmc.net/") }}

dependencies {{
    minecraft("com.mojang:minecraft:${{property("minecraft_version")}}")
{mappings_dependency.rstrip()}
    modImplementation("net.fabricmc:fabric-loader:${{property("loader_version")}}")
    modImplementation("net.fabricmc.fabric-api:fabric-api:${{property("fabric_api_version")}}")
}}

java {{ toolchain {{ languageVersion.set(JavaLanguageVersion.of({v.java})) }} }}
''',
            "gradle.properties": f"minecraft_version={v.minecraft}\n{mappings_property}loader_version={v.loader}\nfabric_api_version={v.fabric_api}\nloom_version={v.loom}\n",
            "src/main/resources/fabric.mod.json": json.dumps({
                "schemaVersion": 1,
                "id": mod_id,
                "version": "${version}",
                "name": mod_name,
                "environment": "*",
                "entrypoints": {"main": [f"{package}.{self._class_name(mod_id)}"]},
                "depends": {"fabricloader": f">={v.loader}", "minecraft": f"~{v.minecraft}", "fabric-api": "*"},
            }, indent=2) + "\n",
            f"src/main/java/{package_path}/{self._class_name(mod_id)}.java": initializer,
            ".gitignore": ".gradle/\nbuild/\nrun/\n",
        }

    def _wrapper_files(self, source: Path) -> dict[str, str | bytes]:
        source = source.resolve(strict=True)
        if not source.is_dir():
            raise FabricBootstrapError("wrapper source must be a directory")
        result: dict[str, str | bytes] = {}
        for relative in ("gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.properties"):
            path = source / relative
            if not path.is_file() or path.is_symlink():
                raise FabricBootstrapError(f"required wrapper file missing: {relative}")
            result[relative] = path.read_text(encoding="utf-8")
        jar = source / "gradle/wrapper/gradle-wrapper.jar"
        if jar.exists():
            if jar.is_symlink() or not jar.is_file():
                raise FabricBootstrapError("invalid Gradle wrapper JAR")
            result["gradle/wrapper/gradle-wrapper.jar"] = jar.read_bytes()
        return result

    def _default_wrapper_files(self) -> dict[str, str]:
        return {
            "gradlew": "#!/bin/sh\nexec gradle \"$@\"\n",
            "gradlew.bat": "@echo off\ngradle %*\n",
            "gradle/wrapper/gradle-wrapper.properties": "distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\n",
        }

    def _class_name(self, mod_id: str) -> str:
        return "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", mod_id) if part) + "Mod"


def bootstrap_fabric_project(workspace: Path, **kwargs: object) -> FabricBootstrapResult:
    """Functional entry point for the pinned Fabric bootstrap."""

    return FabricBootstrap().create(workspace, **kwargs)


@dataclass(frozen=True, slots=True)
class RuntimeBundle:
    """CLI wiring bundle."""

    config: AppConfig
    storage: RunStorage
    controller: RunController
    provider: Any
    economic_session: LunaSharedBudgetSession | None = None


def create_openai_provider(config: AppConfig, *, budget_guard: LunaBudgetGuard | None = None) -> OpenAIProvider:
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
        budget_guard=budget_guard,
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


def create_provider(config: AppConfig, *, budget_guard: LunaBudgetGuard | None = None) -> Any:
    """Create the configured provider adapter."""

    if config.provider == "openai":
        return create_openai_provider(config, budget_guard=budget_guard)
    if budget_guard is not None:
        raise ConfigurationError("economic budget is only supported for openai")
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
    economic_budget_usd: Decimal | str | None = None,
    economic_session: LunaSharedBudgetSession | None = None,
    attempt_ceiling_usd: Decimal | str | None = None,
) -> RuntimeBundle:
    """Compose the runtime graph outside the core runtime."""

    storage = _configure_storage(
        storage,
        config.openai_api_key,
        config.gemini_api_key,
        config.runs_dir,
    )
    if economic_session is not None:
        if economic_budget_usd is not None and economic_session.ceiling_usd != Decimal(str(economic_budget_usd)):
            raise ConfigurationError("shared economic ceiling does not match configured budget")
        if attempt_ceiling_usd is not None:
            try:
                economic_session.configure_attempt_ceiling(attempt_ceiling_usd)
            except ValueError as exc:
                raise ConfigurationError(str(exc)) from exc
        budget_guard = economic_session.guard(
            consumer_id="productive-web-composition",
            experimental=True,
            non_official=True,
        )
    else:
        budget_guard = _build_productive_budget_guard(config, economic_budget_usd, attempt_ceiling_usd)
    if provider_factory is create_provider:
        provider = provider_factory(config, budget_guard=budget_guard)
    else:
        provider = provider_factory(config)
        if budget_guard is not None:
            if not isinstance(provider, OpenAIProvider):
                raise ConfigurationError("explicit economic budget requires an OpenAIProvider")
            provider.budget_guard = budget_guard
    controller = controller_factory(
        provider=provider,
        storage=storage,
        build_runner=build_runner or GradleBuildRunner(reporting=storage),
        artifact_validator=artifact_validator or ArtifactValidator(reporting=storage),
        context_manager=context_manager or ContextManager(),
        limits=config.execution_limits,
        model_config={},
        pre_build_validator=PreBuildWorkspaceValidator(),
    )
    return RuntimeBundle(
        config=config,
        storage=storage,
        controller=controller,
        provider=provider,
        economic_session=economic_session,
    )


def _build_productive_budget_guard(
    config: AppConfig,
    economic_budget_usd: Decimal | str | None,
    attempt_ceiling_usd: Decimal | str | None = None,
) -> LunaBudgetGuard | None:
    """Build the optional productive guard without changing the default runtime."""

    if economic_budget_usd is None:
        return None
    try:
        ceiling = Decimal(str(economic_budget_usd))
    except (InvalidOperation, ValueError) as exc:
        raise ConfigurationError("economic budget must be a positive decimal") from exc
    if not ceiling.is_finite() or ceiling <= 0:
        raise ConfigurationError("economic budget must be a positive decimal")
    if config.provider != "openai" or config.model != "gpt-5.6-luna":
        raise ConfigurationError("economic budget pricing is unavailable for the configured provider/model")
    attempt_ceiling = None
    if attempt_ceiling_usd is not None:
        try:
            attempt_ceiling = Decimal(str(attempt_ceiling_usd))
        except (InvalidOperation, ValueError) as exc:
            raise ConfigurationError("attempt ceiling must be a positive decimal") from exc
        if not attempt_ceiling.is_finite() or attempt_ceiling <= 0:
            raise ConfigurationError("attempt ceiling must be a positive decimal")
        if attempt_ceiling > ceiling:
            raise ConfigurationError("attempt ceiling exceeds global budget")
    # Productive web execution owns its configured global ceiling. Benchmark
    # callers retain the stricter default attempt ceiling in LunaBudgetGuard.
    state = LunaEconomicState(
        execution_id="productive-web",
        global_ceiling_usd=ceiling,
        attempt_ceiling_usd=ceiling if attempt_ceiling is None else attempt_ceiling,
    )
    return LunaBudgetGuard(hard_budget_usd=ceiling, state=state)


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
