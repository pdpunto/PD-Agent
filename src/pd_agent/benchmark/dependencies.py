"""Runtime mod dependency resolution for benchmark/project builds."""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from pd_agent.project import ProjectInspector, ProjectSnapshot


_PLACEHOLDER_PATTERN = re.compile(r"\$\{\s*(?:property\([\"']([^\"']+)[\"']\)|([^}]+))\s*\}")
_EXCLUDED_CORE_COORDINATES = {
    ("com.mojang", "minecraft"),
    ("net.fabricmc", "fabric-loader"),
}


class RuntimeModDependencyResolutionError(ValueError):
    """Raised when runtime mod dependencies cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeModDependency:
    """Resolved runtime mod JAR with provenance."""

    coordinate: str
    path: Path
    sha256: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {
            "coordinate": self.coordinate,
            "path": self.path.as_posix(),
            "sha256": self.sha256,
            "source": self.source,
        }


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_properties(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    properties: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        properties[key.strip()] = value.strip()
    return properties


def _version_symbols(snapshot: ProjectSnapshot) -> dict[str, str]:
    symbols: dict[str, str] = {}
    properties = _load_properties(snapshot.gradle_properties)
    symbols.update(properties)
    symbols.update(
        {
            f"{key}_version": detected.value
            for key, detected in snapshot.detected_versions.items()
            if detected.value
        }
    )
    if "loader" in snapshot.detected_versions:
        symbols.setdefault("fabric_loader_version", snapshot.detected_versions["loader"].value)
        symbols.setdefault("fabricLoaderVersion", snapshot.detected_versions["loader"].value)
    if "fabric_api" in snapshot.detected_versions:
        symbols.setdefault("fabric_api_version", snapshot.detected_versions["fabric_api"].value)
        symbols.setdefault("fabricApiVersion", snapshot.detected_versions["fabric_api"].value)
    if "minecraft" in snapshot.detected_versions:
        symbols.setdefault("minecraft_version", snapshot.detected_versions["minecraft"].value)
        symbols.setdefault("minecraftVersion", snapshot.detected_versions["minecraft"].value)
    if "loom" in snapshot.detected_versions:
        symbols.setdefault("loom_version", snapshot.detected_versions["loom"].value)
        symbols.setdefault("loomVersion", snapshot.detected_versions["loom"].value)
    if "mappings" in snapshot.detected_versions:
        symbols.setdefault("mappings_version", snapshot.detected_versions["mappings"].value)
        symbols.setdefault("yarn_mappings", snapshot.detected_versions["mappings"].value)
    return symbols


def _resolve_placeholders(raw: str, symbols: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1) or match.group(2) or ""
        key = key.strip()
        if key not in symbols:
            raise RuntimeModDependencyResolutionError(f"unknown version symbol: {key}")
        return symbols[key]

    resolved = _PLACEHOLDER_PATTERN.sub(replace, raw)
    if "${" in resolved:
        raise RuntimeModDependencyResolutionError(f"unresolved version placeholder: {raw}")
    return resolved


def _extract_kotlin_string_argument(line: str, call_name: str) -> str | None:
    marker = f"{call_name}("
    start = line.find(marker)
    if start < 0:
        return None
    cursor = line.find('"', start + len(marker))
    if cursor < 0:
        return None
    cursor += 1
    depth = 0
    escaped = False
    characters: list[str] = []
    while cursor < len(line):
        char = line[cursor]
        if escaped:
            characters.append(char)
            escaped = False
            cursor += 1
            continue
        if char == "\\":
            characters.append(char)
            escaped = True
            cursor += 1
            continue
        if depth == 0 and char == '"':
            return "".join(characters)
        if char == "$" and cursor + 1 < len(line) and line[cursor + 1] == "{":
            characters.append(char)
            characters.append("{")
            depth += 1
            cursor += 2
            continue
        if depth > 0:
            characters.append(char)
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            cursor += 1
            continue
        characters.append(char)
        cursor += 1
    return None


def _iter_declared_runtime_mod_coordinates(
    build_files: Sequence[Path],
    *,
    symbols: Mapping[str, str],
) -> tuple[tuple[str, str, str, str], ...]:
    declarations: list[tuple[str, str, str, str]] = []
    for build_file in build_files:
        text = build_file.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for kind in ("modImplementation", "modRuntimeOnly", "modApi"):
                literal = _extract_kotlin_string_argument(line, kind)
                if literal is None:
                    continue
                parts = literal.split(":")
                if len(parts) != 3:
                    continue
                group, artifact, raw_version = parts
                coordinate = f"{group}:{artifact}:{_resolve_placeholders(raw_version, symbols)}"
                declarations.append((kind, coordinate, str(build_file), str(line_number)))
    return tuple(declarations)


def _locate_runtime_mod_jar(
    gradle_user_home: Path,
    *,
    group: str,
    artifact: str,
    version: str,
) -> Path | None:
    group_root = Path(*group.split("."))
    files_root = (
        gradle_user_home
        / "caches"
        / "modules-2"
        / "files-2.1"
        / group_root
        / artifact
        / version
    )
    if not files_root.exists():
        return None
    candidates = sorted(
        (
            candidate
            for candidate in files_root.rglob(f"{artifact}-{version}.jar")
            if candidate.is_file()
        ),
        key=lambda path: path.as_posix().casefold(),
    )
    return candidates[0] if candidates else None


def _contains_fabric_mod_json(path: Path) -> bool:
    with zipfile.ZipFile(path) as jar:
        return "fabric.mod.json" in jar.namelist()


def resolve_runtime_mod_dependencies(
    project_root: Path,
    *,
    gradle_user_home: Path,
    project_snapshot: ProjectSnapshot | None = None,
) -> tuple[ResolvedRuntimeModDependency, ...]:
    root = Path(project_root).resolve(strict=True)
    gradle_home = Path(gradle_user_home).expanduser().resolve(strict=False)
    snapshot = project_snapshot or ProjectInspector().inspect(root)
    build_files = snapshot.build_files or tuple(
        sorted(
            p
            for p in root.rglob("build.gradle*")
            if p.is_file()
        )
    )
    if not build_files:
        raise RuntimeModDependencyResolutionError("no build files found for runtime mod dependency resolution")

    symbols = _version_symbols(snapshot)
    declared = _iter_declared_runtime_mod_coordinates(build_files, symbols=symbols)
    resolved: list[ResolvedRuntimeModDependency] = []
    seen_paths: set[str] = set()
    seen_coordinates: set[str] = set()

    for kind, coordinate, source_file, line_number in declared:
        group, artifact, version = coordinate.split(":", 2)
        if (group, artifact) in _EXCLUDED_CORE_COORDINATES:
            continue
        jar_path = _locate_runtime_mod_jar(gradle_home, group=group, artifact=artifact, version=version)
        if jar_path is None:
            raise RuntimeModDependencyResolutionError(
                f"missing runtime mod dependency: {coordinate} ({source_file}:{line_number})"
            )
        resolved_jar = jar_path.resolve(strict=True)
        try:
            resolved_jar.relative_to(gradle_home)
        except ValueError as exc:  # pragma: no cover - defensive
            raise RuntimeModDependencyResolutionError(
                f"runtime mod dependency escapes gradle_user_home: {resolved_jar}"
            ) from exc
        if not _contains_fabric_mod_json(resolved_jar):
            continue
        path_key = resolved_jar.as_posix().casefold()
        coordinate_key = coordinate.casefold()
        if path_key in seen_paths or coordinate_key in seen_coordinates:
            continue
        seen_paths.add(path_key)
        seen_coordinates.add(coordinate_key)
        resolved.append(
            ResolvedRuntimeModDependency(
                coordinate=coordinate,
                path=resolved_jar,
                sha256=_sha256_file(resolved_jar),
                source=f"{source_file}:{line_number}:{kind}",
            )
        )

    resolved.sort(key=lambda item: (item.coordinate.casefold(), item.path.as_posix().casefold()))
    return tuple(resolved)


__all__ = [
    "ResolvedRuntimeModDependency",
    "RuntimeModDependencyResolutionError",
    "resolve_runtime_mod_dependencies",
]
