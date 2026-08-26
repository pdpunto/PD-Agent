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
    assert 'compileOnly(files("../l11_fabric_fixture/build/classes/java/main"))' not in build_file
    assert "fabric_api_version" not in build_file
    assert 'modImplementation("net.fabricmc.fabric-api:fabric-api:0.141.6+1.21.11")' in build_file
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
    assert "HarnessResult.passLegacy(config, identity, neighborTriggered)" in runner_source
    assert "HarnessResult.failLegacy(config, identity, reason, neighborTriggered)" in runner_source
    assert "HarnessResult.passRegistry(" in runner_source
    assert "HarnessResult.failRegistry(" in runner_source
    assert "TargetBridge.applyProbeState" in runner_source
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
    target_bridge_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "TargetBridge.java")
    assert "Class.forName" in target_bridge_source
    assert "getDeclaredMethod" in target_bridge_source
    assert "Modifier.isStatic" in target_bridge_source
    assert "target entrypoint class not found" in target_bridge_source
    assert "target bridge method missing" in target_bridge_source
    assert "target bridge method signature mismatch" in target_bridge_source
    assert "Files.move" in _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessResultWriter.java")
    assert "ATOMIC_MOVE" in _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessResultWriter.java")
    assert "pd.agent.targetModId" in config_source
    assert "pd.agent.targetSha256" in config_source
    assert "pd.agent.targetEntrypointClass" in config_source
    assert "pd.agent.testId" in config_source
    assert "pd.agent.observationType" in config_source
    assert "pd.agent.observationRegistryKind" in config_source
    assert "pd.agent.observationIdentifier" in config_source
    assert "pd.agent.resultPath" in config_source
    assert "normalizeTestId(String value)" in config_source
    assert "test id cannot be empty" in config_source
    assert "SUPPORTED_TEST_IDS" not in config_source
    assert "unsupported test id" not in config_source
    assert "result path must be absolute" in config_source
    assert "HarnessConfig.OBSERVATION_REGISTRY_ENTRY_PRESENT" in runner_source
    assert "Registries.BLOCK.containsId(identifier)" in runner_source
    assert "Registries.ITEM.containsId(identifier)" in runner_source
    assert "getOrEmpty(identifier).isPresent()" not in runner_source
    assert "HarnessSignals.armNeighborUpdateProbe(SIGNAL_POS)" in runner_source
    assert "HarnessSignals.disarmNeighborUpdateProbe()" in runner_source
    assert "waitForObserverPowered" not in runner_source
    assert "boundedNeighborWaitMillis" not in runner_source


def test_batch_b_registry_presence_lookup_is_semantically_key_based() -> None:
    runner_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRunner.java")

    assert "Registries.BLOCK.containsId(identifier)" in runner_source
    assert "Registries.ITEM.containsId(identifier)" in runner_source
    assert "Registry" in runner_source


def test_batch_b_harness_supports_generic_test_id_labels_without_task_whitelist() -> None:
    config_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessConfig.java")

    assert "pd.agent.testId" in config_source
    assert "test id cannot be empty" in config_source
    assert "SUPPORTED_TEST_IDS" not in config_source
    assert "unsupported test id" not in config_source


def test_batch_b_built_jars_stay_separate() -> None:
    target_source = _read(TARGET_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java")
    harness_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "L11HarnessMod.java")
    target_manifest = json.loads(_read(TARGET_FIXTURE / "src" / "main" / "resources" / "fabric.mod.json"))
    harness_manifest = json.loads(_read(HARNESS_FIXTURE / "src" / "main" / "resources" / "fabric.mod.json"))
    build_file = _read(HARNESS_FIXTURE / "build.gradle.kts")

    assert target_manifest["entrypoints"]["main"] == ["dev.pdpunto.l11.ExampleMod"]
    assert harness_manifest["entrypoints"]["server"] == ["dev.pdpunto.l11harness.L11HarnessMod"]
    assert "ExampleMod" in target_source
    assert "L11HarnessMod" in harness_source
    assert 'compileOnly(files("../l11_fabric_fixture/build/classes/java/main"))' not in build_file
    assert "pd.agent.targetEntrypointClass" in build_file


def test_batch_b_target_and_harness_sources_encode_functional_state_probe() -> None:
    target_source = _read(TARGET_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java")
    harness_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRunner.java")
    runtime_options_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRuntimeOptions.java")
    mixin_source = _read(HARNESS_FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "mixin" / "BlockNeighborUpdateMixin.java")
    build_file = _read(HARNESS_FIXTURE / "build.gradle.kts")

    assert "Blocks.AIR.getDefaultState()" in harness_source
    assert "Blocks.DIAMOND_BLOCK.getDefaultState()" in harness_source
    assert "HarnessSignals.armNeighborUpdateProbe(SIGNAL_POS)" in harness_source
    assert "HarnessSignals.neighborUpdateTriggered()" in harness_source
    assert "TargetBridge.applyProbeState" in harness_source
    assert "expectedBlockState()" in runtime_options_source
    assert "FUNCTIONAL_FAIL" in runtime_options_source
    assert "world.getBlockState" in harness_source
    assert "ServerWorld" in target_source
    assert "applyProbeState" in target_source
    assert "expectedProbeState" in target_source
    assert "neighborUpdate(" in mixin_source
    assert "HarnessSignals.markNeighborUpdateTriggered(pos)" in mixin_source
    assert "pd.agent.targetEntrypointClass" in build_file
