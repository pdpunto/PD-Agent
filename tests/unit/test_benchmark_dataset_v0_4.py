from __future__ import annotations

import json
from pathlib import Path

from pd_agent.benchmark import BenchmarkCatalog, BenchmarkDataset, BenchmarkTask
from pd_agent.benchmark.workspace import compute_fixture_identity


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_v0_4_dataset_is_frozen_and_loaded() -> None:
    root = _repo_root() / "benchmarks"
    catalog = BenchmarkCatalog.load(root)

    dataset = catalog.dataset_for("PD_AGENT_BENCHMARK_DATASET_V0.4_1", "0.4.1")
    assert dataset == BenchmarkDataset.from_dict(
        json.loads((root / "datasets" / "PD_AGENT_BENCHMARK_DATASET_V0.4_1.json").read_text(encoding="utf-8"))
    )
    assert tuple(reference.task_id for reference in dataset.tasks) == ("B001", "B002", "B003")

    task_b001 = catalog.task_for("B001", "1")
    task_b002 = catalog.task_for("B002", "1")
    task_b003 = catalog.task_for("B003", "1")

    assert isinstance(task_b001, BenchmarkTask)
    assert isinstance(task_b002, BenchmarkTask)
    assert isinstance(task_b003, BenchmarkTask)

    assert task_b001.validation.minecraft is True
    assert task_b001.acceptance.acceptance_type == "minecraft_harness"
    assert task_b001.acceptance.spec["expected_block_state_id"] == "diamond_block"
    assert task_b001.acceptance.spec["knowledge_needs"][0]["hints"] == [
        "Registries.BLOCK",
        "Identifier.of",
        "minecraft:diamond_block",
    ]

    assert task_b002.validation.minecraft is False
    assert task_b002.acceptance.acceptance_type == "build_artifact"
    assert task_b002.acceptance.spec["version_sensitive"] is True

    assert task_b003.validation.minecraft is True
    assert task_b003.acceptance.acceptance_type == "minecraft_harness"
    assert task_b003.acceptance.spec["multi_symbol"] is True

    expected_hash = compute_fixture_identity(root / "fixtures" / "B001-v1")
    assert catalog.fixture_identities[("B001", "1")] == expected_hash
    assert catalog.fixture_identities[("B002", "1")] == expected_hash
    assert catalog.fixture_identities[("B003", "1")] == expected_hash

    assert catalog.fixture_paths[("B001", "1")] == (root / "fixtures" / "B001-v1").resolve()
    assert catalog.fixture_paths[("B002", "1")] == (root / "fixtures" / "B002-v1").resolve()
    assert catalog.fixture_paths[("B003", "1")] == (root / "fixtures" / "B003-v1").resolve()


def test_v0_4_dataset_docs_capture_antibias_and_source_of_truth() -> None:
    root = _repo_root() / "benchmarks"
    readme = (root / "README.md").read_text(encoding="utf-8")
    dataset_doc = (root / "datasets" / "PD_AGENT_BENCHMARK_DATASET_V0.4_1.md").read_text(encoding="utf-8")

    assert "net.fabricmc:yarn:1.21.11+build.6:v2" in readme
    assert "Anti-bias analysis" in dataset_doc
    assert "| Aspect | B001 | B002 | B003 |" in dataset_doc
    assert "Registry lookup" in dataset_doc
    assert "Version-sensitive API change" in dataset_doc
    assert "Multi-symbol version-sensitive change" in dataset_doc
