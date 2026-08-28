"""Portable identity for materialized Gradle seed contents."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


NONPORTABLE_SEED_FILE_NAMES = frozenset({"file-access.bin", "file-access.properties"})


def is_nonportable_seed_entry(relative_path: str, *, current_path: Path | None = None) -> bool:
    normalized = str(relative_path).replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1].casefold()
    if filename == "gc.properties" or filename.endswith((".lock", ".lck")):
        return True
    if normalized.startswith("caches/journal-1/") and filename in NONPORTABLE_SEED_FILE_NAMES:
        return True
    return current_path is not None and current_path.name.casefold() == "journal-1" and filename in NONPORTABLE_SEED_FILE_NAMES


def iter_portable_seed_files(root: Path) -> tuple[tuple[str, Path], ...]:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Gradle seed root must be an existing directory")
    items: list[tuple[str, Path]] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(dirnames, key=str.casefold)
        for dirname in dirnames:
            candidate = current_path / dirname
            if candidate.is_symlink():
                raise ValueError(f"symlink not allowed in Gradle seed: {candidate}")
        for filename in sorted(filenames, key=str.casefold):
            candidate = current_path / filename
            if candidate.is_symlink():
                raise ValueError(f"symlink not allowed in Gradle seed: {candidate}")
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root).as_posix()
            if not is_nonportable_seed_entry(relative, current_path=current_path):
                items.append((relative, candidate))
    return tuple(items)


def portable_seed_identity(root: Path, *, seed_id: str = "gradle-wrapper-caches", seed_version: str = "1") -> str:
    components = []
    total_size = 0
    for relative, path in iter_portable_seed_files(root):
        data_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        size = path.stat().st_size
        total_size += size
        components.append({"path": relative, "size_bytes": size, "sha256": data_hash})
    components.sort(key=lambda item: item["path"].casefold())
    payload = {
        "schema_version": 1,
        "seed_id": str(seed_id),
        "seed_version": str(seed_version),
        "components": components,
        "total_size_bytes": total_size,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
