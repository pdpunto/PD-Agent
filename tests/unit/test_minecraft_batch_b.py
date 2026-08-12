from __future__ import annotations

import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_FIXTURE = ROOT / "tests" / "fixtures" / "l11_fabric_fixture"
HARNESS_FIXTURE = ROOT / "tests" / "fixtures" / "l11_minecraft_harness"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _jar_entries(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as jar:
        return set(jar.namelist())


def test_batch_b_target_fixture_uses_server_side_block_probe() -> None:
    build_file = _read(TARGET_FIXTURE / "build.gradle.kts")
    manifest = json.loads(_read(TARGET_FIXTURE / "src" / "main" / "resources" / "fabric.mod.json"))
    source = _read(TARGET_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java")

    assert 'archiveBaseName.set("pd-agent-l11-fixture")' in build_file
    assert 'archiveVersion.set("")' in build_file
    assert manifest["id"] == "pdagentl11"
    assert manifest["entrypoints"]["main"] == ["dev.pdpunto.l11.ExampleMod"]
    assert manifest["depends"]["fabricloader"] == ">=0.19.3"
    assert manifest["depends"]["minecraft"] == "~1.21.11"
    assert "implements ModInitializer" in source
    assert "ServerWorld" in source
    assert "BlockPos" in source
    assert "Blocks.DIAMOND_BLOCK" in source
    assert "Registries.BLOCK" not in source
    assert "Identifier.of(\"minecraft\", \"diamond_block\")" not in source
    assert "setBlockState" in source
    assert "expectedProbeState" in source


def test_batch_b_harness_fixture_is_separate_and_protocol_driven() -> None:
    build_file = _read(HARNESS_FIXTURE / "build.gradle.kts")
    manifest = json.loads(_read(HARNESS_FIXTURE / "src" / "main" / "resources" / "fabric.mod.json"))
    config_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessConfig.java")
    runner_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRunner.java")
    identity_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "TargetIdentityProbe.java")
    result_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessResult.java")
    mod_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "L11HarnessMod.java")
    signals_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessSignals.java")
    mixin_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "mixin" / "BlockNeighborUpdateMixin.java")
    mixin_json = _read(HARNESS_FIXTURE / "src" / "main" / "resources" / "pdagentl11_harness.mixins.json")

    assert 'archiveBaseName.set("pd-agent-l11-harness")' in build_file
    assert 'compileOnly(files("../l11_fabric_fixture/build/classes/java/main"))' in build_file
    assert "fabric_api_version" not in build_file
    assert "fabric-api" not in build_file
    assert 'id("fabric-loom") version "1.13.3"' in build_file
    assert manifest["id"] == "pdagentl11_harness"
    assert manifest["environment"] == "server"
    assert manifest["entrypoints"]["server"] == ["dev.pdpunto.l11harness.L11HarnessMod"]
    assert manifest["mixins"] == ["pdagentl11_harness.mixins.json"]
    assert 'minecraft("com.mojang:minecraft:${property("minecraft_version")}")' in build_file
    assert 'modImplementation("net.fabricmc:fabric-loader:${property("loader_version")}")' in build_file
    assert 'pd.agent.expectNeighborUpdate' in build_file
    assert "DedicatedServerModInitializer" in mod_source
    assert "Thread.ofPlatform().daemon().name(\"pd-agent-l11-harness\")" in mod_source
    assert "waitForServerStart" in mod_source
    assert "ServerLifecycleEvents.SERVER_STARTED" not in mod_source
    assert "server.stop(false)" in mod_source
    assert "HarnessSignals.reset()" in mod_source
    assert "HarnessBlocks" not in mod_source
    assert "Blocks.DIAMOND_BLOCK.getDefaultState()" in runner_source
    assert "HarnessSignals.armNeighborUpdateProbe(SIGNAL_POS)" in runner_source
    assert "HarnessSignals.disarmNeighborUpdateProbe()" in runner_source
    assert "Blocks.OBSERVER" not in runner_source
    assert "ObserverBlock.POWERED" not in runner_source
    assert "FacingBlock.FACING" not in runner_source
    assert "expectNeighborUpdate" in config_source
    assert "neighborPass = !config.expectNeighborUpdate() || neighborTriggered" in runner_source
    assert "HarnessResult.pass(config, identity, neighborTriggered)" in runner_source
    assert "HarnessResult.fail(config, identity, reason, neighborTriggered)" in runner_source
    assert "FabricLoader.getInstance()" in identity_source
    assert "getModContainer" in identity_source
    assert "getOrigin" in identity_source
    assert "ModOrigin.Kind.PATH" in identity_source
    assert "getPaths" in identity_source
    assert "MinecraftServer" in runner_source
    assert "ServerWorld" in runner_source
    assert "BlockPos" in runner_source
    assert "BlockState" in runner_source
    assert "neighbor_update_triggered" in result_source
    assert "HarnessSignals" in signals_source
    assert "schema_version" in result_source
    assert "target_origin_resolved" in result_source
    assert "runtime_target_sha256" in result_source
    assert "target_sha_match" in result_source
    assert "functional_test_result" in result_source
    assert "shutdown_requested" in result_source
    assert "BlockNeighborUpdateMixin" in mixin_source
    assert "HarnessSignals.markNeighborUpdateTriggered(pos)" in mixin_source
    assert "world.isClient()" in mixin_source
    assert "AbstractBlock.class" in mixin_source
    assert "BlockNeighborUpdateMixin" in mixin_json
    assert "AtomicBoolean" in signals_source
    assert "AtomicReference" in signals_source
    assert "reset()" in signals_source
    assert "armNeighborUpdateProbe" in signals_source
    assert "disarmNeighborUpdateProbe" in signals_source
    assert "markNeighborUpdateTriggered(" in signals_source
    assert "neighborUpdateTriggered()" in signals_source
    assert "Files.move" in _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessResultWriter.java")
    assert "ATOMIC_MOVE" in _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessResultWriter.java")
    assert "pd.agent.targetModId" in config_source
    assert "pd.agent.targetSha256" in config_source
    assert "pd.agent.testId" in config_source
    assert "pd.agent.resultPath" in config_source
    assert "block_state_probe_with_signal" in config_source
    assert "SUPPORTED_TEST_IDS" in config_source
    assert "unsupported test id" in config_source
    assert "result path must be absolute" in config_source
    assert "HarnessSignals.armNeighborUpdateProbe(SIGNAL_POS)" in runner_source
    assert "HarnessSignals.disarmNeighborUpdateProbe()" in runner_source
    assert "waitForObserverPowered" not in runner_source
    assert "boundedNeighborWaitMillis" not in runner_source


def test_batch_b_harness_supports_signal_test_id_without_relaxing_validation() -> None:
    config_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessConfig.java")

    assert "block_state_probe" in config_source
    assert "block_state_probe_with_signal" in config_source
    assert "SUPPORTED_TEST_IDS = Set.of(" in config_source
    assert "unsupported test id" in config_source


def test_batch_b_built_jars_stay_separate() -> None:
    target_jar = TARGET_FIXTURE / "build" / "libs" / "pd-agent-l11-fixture.jar"
    harness_jar = HARNESS_FIXTURE / "build" / "libs" / "pd-agent-l11-harness.jar"

    assert target_jar.exists(), f"missing target jar: {target_jar}"
    assert harness_jar.exists(), f"missing harness jar: {harness_jar}"

    target_entries = _jar_entries(target_jar)
    harness_entries = _jar_entries(harness_jar)

    assert "dev/pdpunto/l11/ExampleMod.class" in target_entries
    assert "dev/pdpunto/l11harness/L11HarnessMod.class" not in target_entries
    assert "dev/pdpunto/l11harness/L11HarnessMod.class" in harness_entries
    assert "dev/pdpunto/l11/ExampleMod.class" not in harness_entries


def test_batch_b_target_and_harness_sources_encode_functional_state_probe() -> None:
    target_source = _read(TARGET_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java")
    harness_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRunner.java")
    runtime_options_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRuntimeOptions.java")
    mixin_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "mixin" / "BlockNeighborUpdateMixin.java")

    assert "Blocks.AIR.getDefaultState()" in harness_source
    assert "Blocks.DIAMOND_BLOCK.getDefaultState()" in harness_source
    assert "HarnessSignals.armNeighborUpdateProbe(SIGNAL_POS)" in harness_source
    assert "HarnessSignals.neighborUpdateTriggered()" in harness_source
    assert "ExampleMod.applyProbeState" in harness_source
    assert "expectedBlockState()" in runtime_options_source
    assert "FUNCTIONAL_FAIL" in runtime_options_source
    assert "world.getBlockState" in harness_source
    assert "ServerWorld" in target_source
    assert "applyProbeState" in target_source
    assert "expectedProbeState" in target_source
    assert "neighborUpdate(" in mixin_source
    assert "HarnessSignals.markNeighborUpdateTriggered(pos)" in mixin_source
