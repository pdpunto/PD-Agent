from __future__ import annotations

import json
from textwrap import dedent
from pathlib import Path

from pd_agent.benchmark import BenchmarkCatalog, BenchmarkDataset, BenchmarkTask
from pd_agent.benchmark.workspace import compute_fixture_identity


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _b002_accepts(source: str) -> bool:
    required = (
        "Identifier.ofVanilla(\"diamond_block\")",
        "probeIdentifier()",
    )
    forbidden = (
        "Identifier.of(\"minecraft\", \"diamond_block\")",
    )
    return all(item in source for item in required) and not any(item in source for item in forbidden)


def _b003_accepts(target_source: str, harness_source: str) -> bool:
    target_required = (
        "Registries.BLOCK.get(",
        "Identifier.of(\"minecraft\", \"diamond_block\")",
        "Block.NOTIFY_ALL",
    )
    harness_required = (
        "neighbor_update_triggered",
        "HarnessSignals",
        "NeighborUpdateProbeBlock",
        "neighborUpdate(",
        "HarnessSignals.markNeighborUpdateTriggered()",
    )
    return all(item in target_source for item in target_required) and all(item in harness_source for item in harness_required)


def test_v0_4_hardened_dataset_is_frozen_and_loaded() -> None:
    root = _repo_root() / "benchmarks"
    catalog = BenchmarkCatalog.load(root)

    dataset = catalog.dataset_for("PD_AGENT_BENCHMARK_DATASET_V0.4_2", "0.4.2")
    assert dataset == BenchmarkDataset.from_dict(
        json.loads((root / "datasets" / "PD_AGENT_BENCHMARK_DATASET_V0.4_2.json").read_text(encoding="utf-8"))
    )
    assert tuple(reference.task_id for reference in dataset.tasks) == ("B001", "B002", "B003")

    task_b001 = catalog.task_for("B001", "1")
    task_b002 = catalog.task_for("B002", "2")
    task_b003 = catalog.task_for("B003", "2")

    assert isinstance(task_b001, BenchmarkTask)
    assert isinstance(task_b002, BenchmarkTask)
    assert isinstance(task_b003, BenchmarkTask)

    assert task_b001.validation.minecraft is True
    assert task_b001.acceptance.acceptance_type == "minecraft_harness"
    assert task_b001.acceptance.spec["expected_block_state_id"] == "diamond_block"
    assert task_b001.acceptance.spec.get("expected_neighbor_update", False) is False
    assert task_b001.acceptance.spec["knowledge_needs"][0]["hints"] == [
        "Registries.BLOCK",
        "Identifier.of",
        "minecraft:diamond_block",
    ]

    assert task_b002.validation.minecraft is False
    assert task_b002.acceptance.acceptance_type == "source_structure"
    assert task_b002.acceptance.spec["file"] == "src/main/java/dev/pdpunto/l11/ExampleMod.java"
    assert tuple(task_b002.acceptance.spec["required_symbols"]) == (
        "Identifier.ofVanilla(\"diamond_block\")",
        "probeIdentifier()",
    )
    assert task_b002.acceptance.spec["build_required"] is True
    assert task_b002.acceptance.spec["artifact_required"] is True

    assert task_b003.validation.minecraft is True
    assert task_b003.acceptance.acceptance_type == "minecraft_harness"
    assert task_b003.acceptance.spec["expected_neighbor_update"] is True
    assert task_b003.acceptance.spec["neighbor_probe_block"] == "neighbor_update_probe"

    expected_hash = compute_fixture_identity(root / "fixtures" / "B001-v1")
    assert catalog.fixture_identities[("B001", "1")] == expected_hash
    assert catalog.fixture_identities[("B002", "2")] == expected_hash
    assert catalog.fixture_identities[("B003", "2")] == expected_hash

    assert catalog.fixture_paths[("B001", "1")] == (root / "fixtures" / "B001-v1").resolve()
    assert catalog.fixture_paths[("B002", "2")] == (root / "fixtures" / "B002-v2").resolve()
    assert catalog.fixture_paths[("B003", "2")] == (root / "fixtures" / "B003-v2").resolve()


def test_v0_4_dataset_docs_capture_antibias_and_source_of_truth() -> None:
    root = _repo_root() / "benchmarks"
    readme = (root / "README.md").read_text(encoding="utf-8")
    dataset_doc = (root / "datasets" / "PD_AGENT_BENCHMARK_DATASET_V0.4_2.md").read_text(encoding="utf-8")
    candidate_doc = (root / "datasets" / "PD_AGENT_BENCHMARK_DATASET_V0.4_1.md").read_text(encoding="utf-8")

    assert "net.fabricmc:yarn:1.21.11+build.6:v2" in readme
    assert "Anti-bias analysis" in dataset_doc
    assert "| Aspect | B001 | B002 | B003 |" in dataset_doc
    assert "Version-sensitive API helper" in dataset_doc
    assert "Multi-symbol runtime check" in dataset_doc
    assert "candidate freeze" in candidate_doc.casefold()


def test_v0_4_b002_controls_and_acceptance_predicate() -> None:
    root = _repo_root() / "benchmarks" / "fixtures" / "B002-v2"
    source_path = root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"
    baseline = source_path.read_text(encoding="utf-8")

    irrelevant = baseline.replace("Intentionally empty.", "Still empty.")
    correct = dedent(
        """
        package dev.pdpunto.l11;

        import net.fabricmc.api.ModInitializer;
        import net.minecraft.block.Block;
        import net.minecraft.block.BlockState;
        import net.minecraft.block.Blocks;
        import net.minecraft.server.world.ServerWorld;
        import net.minecraft.util.Identifier;
        import net.minecraft.registry.Registries;
        import net.minecraft.util.math.BlockPos;

        public final class ExampleMod implements ModInitializer {
            public static final String MOD_ID = "pdagentl11";
            private static final Identifier PROBE_ID = Identifier.ofVanilla("diamond_block");
            private static final BlockState PROBE_STATE = Registries.BLOCK.get(PROBE_ID).getDefaultState();

            @Override
            public void onInitialize() {
                // Intentionally empty. The batch-B acceptance uses the public server-side helper below.
            }

            public static boolean applyProbeState(ServerWorld world, BlockPos pos) {
                return world.setBlockState(pos, PROBE_STATE, Block.NOTIFY_ALL);
            }

            public static Identifier probeIdentifier() {
                return PROBE_ID;
            }

            public static BlockState expectedProbeState() {
                return PROBE_STATE;
            }
        }
        """
    ).strip()

    assert _b002_accepts(baseline) is False
    assert _b002_accepts(irrelevant) is False
    assert _b002_accepts(correct) is True


def test_v0_4_b003_controls_and_harness_signal() -> None:
    root = _repo_root() / "benchmarks" / "fixtures" / "B003-v2"
    target_source = (root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java").read_text(encoding="utf-8")
    harness_root = _repo_root() / "tests" / "fixtures" / "l11_minecraft_harness"
    harness_source = (harness_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRunner.java").read_text(encoding="utf-8")
    harness_mod = (harness_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "L11HarnessMod.java").read_text(encoding="utf-8")
    harness_result = (harness_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessResult.java").read_text(encoding="utf-8")
    signals_source = (harness_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessSignals.java").read_text(encoding="utf-8")
    probe_source = (harness_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "NeighborUpdateProbeBlock.java").read_text(encoding="utf-8")
    blocks_source = (harness_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessBlocks.java").read_text(encoding="utf-8")
    runner_source = (harness_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRunner.java").read_text(encoding="utf-8")

    baseline = target_source
    partial_registry = target_source.replace(
        "private static final BlockState PROBE_STATE = Blocks.DIAMOND_BLOCK.getDefaultState();",
        "private static final BlockState PROBE_STATE = Registries.BLOCK.get(Identifier.of(\"minecraft\", \"diamond_block\")).getDefaultState();",
    )
    partial_flag = baseline
    correct = partial_registry

    assert _b003_accepts(baseline, harness_source) is False
    assert _b003_accepts(partial_registry.replace("Block.NOTIFY_ALL", "Block.NOTIFY_NEIGHBORS"), harness_source) is False
    assert _b003_accepts(partial_flag, harness_source) is False
    harness_bundle = harness_source + harness_mod + harness_result + signals_source + probe_source + blocks_source + runner_source
    assert _b003_accepts(correct, harness_bundle) is True
