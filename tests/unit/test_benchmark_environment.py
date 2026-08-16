from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_agent.benchmark import (
    BenchmarkGradleEnvironment,
    BenchmarkGradleEnvironmentError,
    BenchmarkGradleSeedComponent,
    BenchmarkGradleSeedManifest,
)


def _seed(root: Path) -> Path:
    (root / "wrapper").mkdir(parents=True, exist_ok=True)
    (root / "caches").mkdir(parents=True, exist_ok=True)
    (root / "wrapper" / "seed.txt").write_text("wrapper", encoding="utf-8")
    (root / "caches" / "marker.txt").write_text("cache", encoding="utf-8")
    return root


def _manifest(seed_root: Path, *, bom: bool = False) -> Path:
    built = BenchmarkGradleSeedManifest.build(seed_root)
    manifest = {
        "schema_version": built.schema_version,
        "created_at": built.created_at.isoformat(),
        "source": "host-gradle-bootstrap",
        "bootstrap_network_used": False,
        "gradle": "8.14.3",
        "java_major": 21,
        "minecraft": "1.21.11",
        "loom": "1.13.3",
        "loader": "0.19.3",
        "yarn": "1.21.11+build.6",
        "file_count": built.component_count,
        "total_bytes": built.total_size_bytes,
        "entries": [
            {
                "path": component.path,
                "size": component.size_bytes,
                "sha256": component.sha256,
            }
            for component in built.components
        ],
    }
    path = seed_root.parent / "seed-manifest.json"
    raw = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
    if bom:
        path.write_bytes(b"\xef\xbb\xbf" + raw.encode("utf-8"))
    else:
        path.write_text(raw, encoding="utf-8")
    return path


def _contaminated_manifest(seed_root: Path) -> tuple[Path, tuple[BenchmarkGradleSeedComponent, ...]]:
    portable = BenchmarkGradleSeedManifest.build(seed_root)
    volatile_files = (
        seed_root / "caches" / "fabric-loom" / ".4cdb1c74ed94ba0ff74ab4ebba36e04d05e3ffe8.lock",
        seed_root / "caches" / "modules-2" / "sample.lock",
        seed_root / "caches" / "8.14.3" / "gc.properties",
        seed_root / "caches" / "modules-2" / "gc.properties",
        seed_root / "caches" / "journal-1" / "file-access.bin",
        seed_root / "caches" / "journal-1" / "file-access.properties",
    )
    for file_path in volatile_files:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f"volatile:{file_path.name}", encoding="utf-8")
    volatile_components = tuple(
        BenchmarkGradleSeedComponent(path=file_path.relative_to(seed_root).as_posix(), size_bytes=file_path.stat().st_size, sha256="0" * 64)
        for file_path in volatile_files
    )
    contaminated_components = tuple(sorted((*portable.components, *volatile_components), key=lambda component: component.path.casefold()))
    contaminated_manifest = BenchmarkGradleSeedManifest(
        schema_version=portable.schema_version,
        seed_id=portable.seed_id,
        seed_version=portable.seed_version,
        source_root=portable.source_root,
        components=contaminated_components,
        total_size_bytes=sum(component.size_bytes for component in contaminated_components),
        created_at=portable.created_at,
    )
    path = seed_root.parent / "contaminated-seed-manifest.json"
    path.write_text(
        json.dumps(contaminated_manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path, volatile_components


def test_prepare_accepts_utf8_seed_manifest_without_bom(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    execution_root = tmp_path / "exec"
    execution_root.mkdir()
    manifest_path = _manifest(seed_root, bom=False)

    env = BenchmarkGradleEnvironment.prepare(
        seed_root=seed_root,
        execution_root=execution_root,
        seed_manifest_path=manifest_path,
    )

    assert env.bootstrap_status == "READY"
    assert env.offline is True
    assert env.gradle_user_home.exists()


def test_prepare_accepts_utf8_seed_manifest_with_bom(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    execution_root = tmp_path / "exec"
    execution_root.mkdir()
    manifest_path = _manifest(seed_root, bom=True)

    env = BenchmarkGradleEnvironment.prepare(
        seed_root=seed_root,
        execution_root=execution_root,
        seed_manifest_path=manifest_path,
    )

    assert env.seed_manifest.identity_hash is not None
    assert env.seed_manifest_path is not None
    assert env.seed_manifest_path.exists()


def test_prepare_rejects_invalid_seed_manifest_json(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    execution_root = tmp_path / "exec"
    execution_root.mkdir()
    manifest_path = tmp_path / "seed-manifest.json"
    manifest_path.write_bytes(b"\xef\xbb\xbf{ not json }")

    with pytest.raises(json.JSONDecodeError):
        BenchmarkGradleEnvironment.prepare(
            seed_root=seed_root,
            execution_root=execution_root,
            seed_manifest_path=manifest_path,
        )


def test_prepare_rejects_seed_manifest_mismatch(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    execution_root = tmp_path / "exec"
    execution_root.mkdir()
    manifest_path = _manifest(seed_root, bom=True)
    (seed_root / "wrapper" / "seed.txt").write_text("changed", encoding="utf-8")

    with pytest.raises(BenchmarkGradleEnvironmentError, match="manifest mismatch"):
        BenchmarkGradleEnvironment.prepare(
            seed_root=seed_root,
            execution_root=execution_root,
            seed_manifest_path=manifest_path,
        )


def test_prepare_sanitizes_nonportable_seed_state(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    execution_root = tmp_path / "exec"
    execution_root.mkdir()
    manifest_path, volatile_components = _contaminated_manifest(seed_root)

    env = BenchmarkGradleEnvironment.prepare(
        seed_root=seed_root,
        execution_root=execution_root,
        seed_manifest_path=manifest_path,
    )

    assert env.seed_manifest.identity_hash is not None
    assert env.seed_manifest.component_count == len(BenchmarkGradleSeedManifest.build(seed_root).components)
    assert env.seed_manifest.component_count < BenchmarkGradleSeedManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8"))).component_count
    for component in volatile_components:
        assert not (env.gradle_user_home / component.path).exists()
    assert (env.gradle_user_home / "wrapper" / "seed.txt").exists()


def test_restore_sanitizes_nonportable_seed_state(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    execution_root = tmp_path / "exec"
    execution_root.mkdir()
    manifest_path, volatile_components = _contaminated_manifest(seed_root)

    prepared = BenchmarkGradleEnvironment.prepare(
        seed_root=seed_root,
        execution_root=execution_root,
        seed_manifest_path=manifest_path,
    )
    restored = BenchmarkGradleEnvironment.restore(execution_root=execution_root)

    assert restored.seed_manifest.identity_hash == prepared.seed_manifest.identity_hash
    for component in volatile_components:
        assert not (restored.gradle_user_home / component.path).exists()
    assert (restored.gradle_user_home / "wrapper" / "seed.txt").exists()


def test_build_keeps_modules_metadata_and_excludes_nonportable_cache_state(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    metadata_root = seed_root / "caches" / "modules-2" / "metadata-2.107"
    descriptor_root = metadata_root / "descriptors" / "net.fabricmc.fabric-api" / "fabric-api" / "0.141.6+1.21.11" / "abcdef1234567890"
    files_root = seed_root / "caches" / "modules-2" / "files-2.1" / "net.fabricmc.fabric-api" / "fabric-api" / "0.141.6+1.21.11" / "abcdef1234567890"
    descriptor_root.mkdir(parents=True, exist_ok=True)
    files_root.mkdir(parents=True, exist_ok=True)
    (metadata_root / "module-metadata.bin").write_bytes(b"module-metadata-a")
    (metadata_root / "module-artifact.bin").write_bytes(b"module-artifact-a")
    (metadata_root / "module-artifacts.bin").write_bytes(b"module-artifacts-a")
    (metadata_root / "resource-at-url.bin").write_bytes(b"resource-at-url-a")
    (descriptor_root / "descriptor.bin").write_bytes(b"descriptor-a")
    (files_root / "fabric-api-0.141.6+1.21.11.jar").write_bytes(b"fabric-api-jar-a")
    (files_root / "fabric-api-0.141.6+1.21.11.pom").write_text("<project/>", encoding="utf-8")
    (seed_root / "caches" / "modules-2" / "gc.properties").write_text("gc", encoding="utf-8")
    (seed_root / "caches" / "modules-2" / "sample.lock").write_text("lock", encoding="utf-8")
    (seed_root / "caches" / "8.14.3").mkdir(parents=True, exist_ok=True)
    (seed_root / "caches" / "8.14.3" / "gc.properties").write_text("gc", encoding="utf-8")
    (seed_root / "caches" / "journal-1").mkdir(parents=True, exist_ok=True)
    (seed_root / "caches" / "journal-1" / "file-access.bin").write_bytes(b"journal-bin")
    (seed_root / "caches" / "journal-1" / "file-access.properties").write_text("journal-props", encoding="utf-8")

    manifest = BenchmarkGradleSeedManifest.build(seed_root)
    paths = {component.path for component in manifest.components}

    assert "caches/modules-2/metadata-2.107/module-metadata.bin" in paths
    assert "caches/modules-2/metadata-2.107/module-artifact.bin" in paths
    assert "caches/modules-2/metadata-2.107/module-artifacts.bin" in paths
    assert "caches/modules-2/metadata-2.107/resource-at-url.bin" in paths
    assert "caches/modules-2/metadata-2.107/descriptors/net.fabricmc.fabric-api/fabric-api/0.141.6+1.21.11/abcdef1234567890/descriptor.bin" in paths
    assert "caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/0.141.6+1.21.11/abcdef1234567890/fabric-api-0.141.6+1.21.11.jar" in paths
    assert "caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/0.141.6+1.21.11/abcdef1234567890/fabric-api-0.141.6+1.21.11.pom" in paths
    assert not any(path.endswith("gc.properties") for path in paths)
    assert not any(path.endswith(".lock") or path.endswith(".lck") for path in paths)
    assert not any(path.endswith("file-access.bin") or path.endswith("file-access.properties") for path in paths)


def test_build_identity_changes_when_portable_modules_metadata_changes(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    metadata_root = seed_root / "caches" / "modules-2" / "metadata-2.107"
    metadata_root.mkdir(parents=True, exist_ok=True)
    (metadata_root / "module-metadata.bin").write_bytes(b"module-metadata-a")
    manifest_a = BenchmarkGradleSeedManifest.build(seed_root)

    (metadata_root / "module-metadata.bin").write_bytes(b"module-metadata-b")
    manifest_b = BenchmarkGradleSeedManifest.build(seed_root)

    assert manifest_a.identity_hash != manifest_b.identity_hash
    assert manifest_a.diff(manifest_b) == ("mismatch:caches/modules-2/metadata-2.107/module-metadata.bin",)


def test_restore_reuses_existing_materialization(tmp_path: Path) -> None:
    seed_root = _seed(tmp_path / "seed")
    execution_root = tmp_path / "exec"
    execution_root.mkdir()
    manifest_path = _manifest(seed_root, bom=False)

    prepared = BenchmarkGradleEnvironment.prepare(
        seed_root=seed_root,
        execution_root=execution_root,
        seed_manifest_path=manifest_path,
    )
    restored = BenchmarkGradleEnvironment.restore(execution_root=execution_root)

    assert restored.bootstrap_status == "READY"
    assert restored.offline is True
    assert restored.gradle_user_home == prepared.gradle_user_home
    assert restored.environment_overrides == prepared.environment_overrides
    assert restored.seed_manifest.identity_hash == prepared.seed_manifest.identity_hash
    assert restored.seed_manifest_path == prepared.seed_manifest_path
