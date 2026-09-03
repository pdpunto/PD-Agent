"""Static Fabric metadata inspection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .models import (
    DetectedValue,
    FabricDependencyMap,
    FabricManifest,
    MixinConfig,
)


NOISY_DIRS = {
    ".git",
    ".gradle",
    "__pycache__",
    "bin",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "build",
    "dist",
    "runs",
    "evidence",
}


@dataclass(frozen=True, slots=True)
class FabricInspectionResult:
    """Static Fabric inspection result."""

    manifests: tuple[FabricManifest, ...]
    mixins: tuple[MixinConfig, ...]
    source_roots: tuple[Path, ...]
    resource_roots: tuple[Path, ...]
    build_files: tuple[Path, ...]
    settings_files: tuple[Path, ...]
    gradle_properties: Path | None
    version_catalogs: tuple[Path, ...]
    wrapper_present: bool
    wrapper_scripts: tuple[Path, ...]
    detected_versions: Mapping[str, DetectedValue]
    module_roots: tuple[Path, ...]
    target_subproject: Path | None
    issues: tuple[str, ...]


class FabricInspector:
    """Static Fabric project inspector."""

    def inspect(self, project_root: Path) -> FabricInspectionResult:
        root = project_root.resolve(strict=True)
        settings_files = tuple(
            sorted(
                p
                for p in root.rglob("settings.gradle*")
                if p.is_file() and not self._is_noisy(p)
            )
        )
        build_files = tuple(
            sorted(
                p
                for p in root.rglob("build.gradle*")
                if p.is_file() and not self._is_noisy(p)
            )
        )
        wrapper_scripts = tuple(
            sorted(
                p
                for p in [root / "gradlew", root / "gradlew.bat"]
                if p.exists()
            )
        )
        wrapper_present = bool(wrapper_scripts)
        gradle_properties = root / "gradle.properties" if (root / "gradle.properties").exists() else None
        version_catalogs = tuple(
            sorted(
                p
                for p in root.rglob("libs.versions.toml")
                if p.is_file() and not self._is_noisy(p)
            )
        )

        manifest_paths = tuple(
            sorted(
                p
                for p in root.rglob("fabric.mod.json")
                if p.is_file() and not self._is_noisy(p)
            )
        )

        manifests: list[FabricManifest] = []
        mixin_paths: list[Path] = []
        module_roots: set[Path] = set()
        for path in manifest_paths:
            manifest, manifest_mixins, module_root = self._read_manifest(path)
            manifests.append(manifest)
            mixin_paths.extend(manifest_mixins)
            module_roots.add(module_root)

        explicit_source_roots, explicit_resource_roots = self._discover_explicit_roots(build_files)
        for module_root in self._discover_module_roots(root, settings_files, build_files, manifests):
            module_roots.add(module_root)
            source_candidate = module_root / "src" / "main" / "java"
            kotlin_candidate = module_root / "src" / "main" / "kotlin"
            resource_candidate = module_root / "src" / "main" / "resources"
            if source_candidate.exists():
                explicit_source_roots.add(source_candidate.resolve(strict=False))
            if kotlin_candidate.exists():
                explicit_source_roots.add(kotlin_candidate.resolve(strict=False))
            if resource_candidate.exists():
                explicit_resource_roots.add(resource_candidate.resolve(strict=False))

        mixins = tuple(
            sorted(
                (self._read_mixin_config(path) for path in self._unique_paths(mixin_paths)),
                key=lambda item: str(item.path).casefold(),
            )
        )
        detected_versions = self._detect_versions(gradle_properties, version_catalogs, build_files)
        target_subproject, issues = self._resolve_target_subproject(
            tuple(sorted(module_roots, key=lambda path: str(path).casefold())),
            manifests,
            wrapper_present,
        )
        source_roots = tuple(
            sorted(explicit_source_roots, key=lambda path: str(path).casefold())
        )
        resource_roots = tuple(
            sorted(explicit_resource_roots, key=lambda path: str(path).casefold())
        )

        return FabricInspectionResult(
            manifests=tuple(manifests),
            mixins=mixins,
            source_roots=source_roots,
            resource_roots=resource_roots,
            build_files=build_files,
            settings_files=settings_files,
            gradle_properties=gradle_properties,
            version_catalogs=version_catalogs,
            wrapper_present=wrapper_present,
            wrapper_scripts=wrapper_scripts,
            detected_versions=detected_versions,
            module_roots=tuple(sorted(module_roots, key=lambda path: str(path).casefold())),
            target_subproject=target_subproject,
            issues=issues,
        )

    def _read_manifest(self, path: Path) -> tuple[FabricManifest, tuple[Path, ...], Path]:
        errors: list[str] = []
        mixin_paths: list[Path] = []
        module_root = self._module_root_for_manifest(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return (
                FabricManifest(
                    path=path,
                    mod_id=None,
                    version=None,
                    environment=None,
                    errors=(f"invalid JSON: {exc.msg}",),
                    source_root=module_root / "src" / "main" / "java",
                    resource_root=module_root / "src" / "main" / "resources",
                ),
                (),
                module_root,
            )

        if not isinstance(data, Mapping):
            return (
                FabricManifest(
                    path=path,
                    mod_id=None,
                    version=None,
                    environment=None,
                    errors=("manifest is not an object",),
                    source_root=module_root / "src" / "main" / "java",
                    resource_root=module_root / "src" / "main" / "resources",
                ),
                (),
                module_root,
            )

        mod_id = self._coerce_str(data.get("id"))
        version = self._coerce_str(data.get("version"))
        environment = self._coerce_str(data.get("environment"))
        entrypoints = self._parse_entrypoints(data.get("entrypoints"), errors)
        dependencies = FabricDependencyMap(
            depends=self._coerce_mapping(data.get("depends"), errors),
            recommends=self._coerce_mapping(data.get("recommends"), errors),
            suggests=self._coerce_mapping(data.get("suggests"), errors),
            conflicts=self._coerce_mapping(data.get("conflicts"), errors),
            breaks=self._coerce_mapping(data.get("breaks"), errors),
        )
        mixins = self._parse_mixins_field(data.get("mixins"), path, mixin_paths, errors)

        if mod_id is None:
            errors.append("missing id")
        if version is None:
            errors.append("missing version")
        if environment is None:
            errors.append("missing environment")

        manifest = FabricManifest(
            path=path,
            mod_id=mod_id,
            version=version,
            environment=environment,
            entrypoints=entrypoints,
            dependencies=dependencies,
            mixins=mixins,
            source_root=module_root / "src" / "main" / "java",
            resource_root=module_root / "src" / "main" / "resources",
            errors=tuple(errors),
        )
        return manifest, tuple(mixin_paths), module_root

    def _parse_entrypoints(self, value: object, errors: list[str]) -> dict[str, tuple[str, ...]]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            errors.append("entrypoints must be an object")
            return {}
        parsed: dict[str, tuple[str, ...]] = {}
        for key, raw in value.items():
            if isinstance(raw, str):
                parsed[str(key)] = (raw,)
            elif isinstance(raw, list) and all(isinstance(item, str) for item in raw):
                parsed[str(key)] = tuple(raw)
            else:
                errors.append(f"entrypoint {key!r} has unsupported shape")
        return parsed

    def _coerce_mapping(self, value: object, errors: list[str]) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            errors.append("dependency section must be an object")
            return {}
        return dict(value)

    def _coerce_str(self, value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    def _parse_mixins_field(
        self,
        value: object,
        manifest_path: Path,
        mixin_paths: list[Path],
        errors: list[str],
    ) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            entries = [value]
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            entries = list(value)
        else:
            errors.append("mixins must be string or array of strings")
            return ()
        for item in entries:
            mixin_paths.append((manifest_path.parent / item).resolve(strict=False))
        return tuple(entries)

    def _read_mixin_config(self, path: Path) -> MixinConfig:
        errors: list[str] = []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return MixinConfig(
                path=path,
                package=None,
                required=None,
                compatibility_level=None,
                errors=(f"invalid JSON: {exc.msg}",),
            )
        if not isinstance(data, Mapping):
            return MixinConfig(
                path=path,
                package=None,
                required=None,
                compatibility_level=None,
                errors=("mixin config is not an object",),
            )

        mixins = self._tuple_of_strings(data.get("mixins"), errors, "mixins")
        client = self._tuple_of_strings(data.get("client"), errors, "client")
        server = self._tuple_of_strings(data.get("server"), errors, "server")
        injectors = data.get("injectors")
        default_require = None
        if isinstance(injectors, Mapping) and isinstance(injectors.get("defaultRequire"), int):
            default_require = int(injectors["defaultRequire"])
        package = self._coerce_str(data.get("package"))
        required = data.get("required") if isinstance(data.get("required"), bool) else None
        compatibility_level = self._coerce_str(data.get("compatibilityLevel"))
        return MixinConfig(
            path=path,
            package=package,
            required=required,
            compatibility_level=compatibility_level,
            mixins=mixins,
            client=client,
            server=server,
            default_require=default_require,
            errors=tuple(errors),
        )

    def _tuple_of_strings(self, value: object, errors: list[str], field_name: str) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return tuple(value)
        errors.append(f"{field_name} must be string or array of strings")
        return ()

    def _module_root_for_manifest(self, manifest_path: Path) -> Path:
        posix = manifest_path.as_posix()
        if posix.endswith("/src/main/resources/fabric.mod.json") and len(manifest_path.parents) > 3:
            return manifest_path.parents[3]
        return manifest_path.parent

    def _discover_explicit_roots(self, build_files: tuple[Path, ...]) -> tuple[set[Path], set[Path]]:
        source_roots: set[Path] = set()
        resource_roots: set[Path] = set()
        for build_file in build_files:
            text = build_file.read_text(encoding="utf-8")
            for match in re.finditer(r'(?:java|kotlin)\.srcDir\(\s*["\']([^"\']+)["\']\s*\)', text):
                source_roots.add((build_file.parent / match.group(1)).resolve(strict=False))
            for match in re.finditer(r'resources\.srcDir\(\s*["\']([^"\']+)["\']\s*\)', text):
                resource_roots.add((build_file.parent / match.group(1)).resolve(strict=False))
            for match in re.finditer(r'srcDir\(\s*["\']([^"\']+)["\']\s*\)', text):
                relative = match.group(1)
                if "resources" in match.group(0):
                    resource_roots.add((build_file.parent / relative).resolve(strict=False))
                else:
                    source_roots.add((build_file.parent / relative).resolve(strict=False))
        return source_roots, resource_roots

    def _discover_module_roots(
        self,
        root: Path,
        settings_files: tuple[Path, ...],
        build_files: tuple[Path, ...],
        manifests: tuple[FabricManifest, ...],
    ) -> tuple[Path, ...]:
        roots: set[Path] = {root}
        for settings_file in settings_files:
            for included in self._parse_includes(settings_file):
                candidate = (settings_file.parent / included.lstrip(":").replace(":", "/")).resolve(strict=False)
                if candidate.exists():
                    roots.add(candidate)
        for build_file in build_files:
            roots.add(build_file.parent)
        for manifest in manifests:
            roots.add(self._module_root_for_manifest(manifest.path))
        return tuple(sorted(roots, key=lambda path: str(path).casefold()))

    def _parse_includes(self, settings_file: Path) -> tuple[str, ...]:
        text = settings_file.read_text(encoding="utf-8")
        matches: list[str] = []
        if settings_file.suffix == ".kts":
            for match in re.finditer(r"include\(([^)]*)\)", text):
                matches.extend(re.findall(r'["\']([^"\']+)["\']', match.group(1)))
        else:
            for match in re.finditer(r"include\s+([^\n]+)", text):
                matches.extend(re.findall(r'["\']([^"\']+)["\']', match.group(1)))
        return tuple(matches)

    def _resolve_target_subproject(
        self,
        module_roots: tuple[Path, ...],
        manifests: tuple[FabricManifest, ...],
        wrapper_present: bool,
    ) -> tuple[Path | None, tuple[str, ...]]:
        if not wrapper_present:
            return None, ("Gradle Wrapper absent",)
        fabric_candidates = tuple(
            sorted(
                {self._module_root_for_manifest(manifest.path) for manifest in manifests},
                key=lambda path: str(path).casefold(),
            )
        )
        if len(fabric_candidates) == 1:
            return fabric_candidates[0], ()
        if len(fabric_candidates) == 0:
            return (module_roots[0], ()) if len(module_roots) == 1 else (None, ("no Fabric module detected",))
        return None, ("ambiguous Fabric subproject selection",)

    def _detect_versions(
        self,
        gradle_properties: Path | None,
        version_catalogs: tuple[Path, ...],
        build_files: tuple[Path, ...],
    ) -> dict[str, DetectedValue]:
        values: dict[str, DetectedValue] = {}
        properties = self._load_properties(gradle_properties) if gradle_properties else {}

        for logical, keys in {
            "minecraft": ("minecraft_version", "minecraftVersion"),
            "loader": ("loader_version", "fabric_loader_version", "fabricLoaderVersion"),
            "fabric_api": ("fabric_version", "fabric_api_version", "fabricApiVersion"),
            "loom": ("loom_version", "loomVersion"),
            "mappings": ("mappings", "yarn_mappings", "mappings_version"),
        }.items():
            for key in keys:
                if key in properties and logical not in values:
                    values[logical] = DetectedValue(properties[key], f"{gradle_properties}:{key}")

        try:
            import tomllib
        except Exception:  # pragma: no cover
            tomllib = None

        if tomllib is not None:
            for catalog in version_catalogs:
                data = tomllib.loads(catalog.read_text(encoding="utf-8"))
                versions = data.get("versions", {})
                if isinstance(versions, Mapping):
                    for logical, aliases in {
                        "minecraft": ("minecraft", "minecraft_version"),
                        "loader": ("loader", "fabric_loader"),
                        "fabric_api": ("fabric_api", "fabric-api"),
                        "loom": ("loom",),
                        "mappings": ("mappings", "yarn"),
                    }.items():
                        for alias in aliases:
                            if alias in versions and logical not in values:
                                values[logical] = DetectedValue(
                                    str(versions[alias]), f"{catalog}:versions.{alias}"
                                )

        for build_file in build_files:
            text = build_file.read_text(encoding="utf-8")
            for logical, pattern in {
                "minecraft": r'minecraft_version\s*[=:]\s*["\']?([0-9A-Za-z_.+-]+)',
                "loader": r'fabric_loader_version\s*[=:]\s*["\']?([0-9A-Za-z_.+-]+)',
                "fabric_api": r'fabric_version\s*[=:]\s*["\']?([0-9A-Za-z_.+-]+)',
                "loom": r'loom_version\s*[=:]\s*["\']?([0-9A-Za-z_.+-]+)',
                "mappings": r'mappings\s+["\']([^"\']+)["\']',
            }.items():
                if logical not in values:
                    match = re.search(pattern, text)
                    if match:
                        values[logical] = DetectedValue(match.group(1), f"{build_file}:{logical}")
        return values

    def _load_properties(self, path: Path) -> dict[str, str]:
        properties: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            properties[key.strip()] = value.strip()
        return properties

    def _is_noisy(self, path: Path) -> bool:
        return any(part in NOISY_DIRS for part in path.parts)

    def _unique_paths(self, paths: list[Path]) -> tuple[Path, ...]:
        return tuple(sorted({path.resolve(strict=False) for path in paths}, key=lambda path: str(path).casefold()))
