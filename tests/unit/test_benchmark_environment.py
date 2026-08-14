from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_agent.benchmark import BenchmarkGradleEnvironment, BenchmarkGradleEnvironmentError, BenchmarkGradleSeedManifest


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
