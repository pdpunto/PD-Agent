from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from pd_agent.minecraft import MinecraftObservationType, MinecraftTestRunner, MinecraftTestSpec
from pd_agent.minecraft.errors import UnsupportedMinecraftEnvironmentError


FIXTURE = Path("tests/fixtures/fabric_26_2_minecraft_harness")


def _spec(tmp_path: Path, *, version: str, platform_id: str | None = None) -> MinecraftTestSpec:
    target = tmp_path / "target.jar"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps({"id": "modernfixture", "entrypoints": {"main": ["Main"]}}))
    return MinecraftTestSpec(
        target_jar=Path("target.jar"),
        target_mod_id="modernfixture",
        minecraft_version=version,
        loader_version="0.19.3",
        test_id="lot6",
        timeout_seconds=30,
        platform_id=platform_id,
        observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        observation_params={"registry_kind": "block", "identifier": "modernfixture:server_core"},
    )


def test_legacy_spec_keeps_existing_inferred_profile(tmp_path: Path) -> None:
    spec = _spec(tmp_path, version="1.21.11")
    MinecraftTestRunner(project_root=tmp_path).validate_spec(spec, java_version="21")


def test_26_2_selects_bounded_profile_and_rejects_java21(tmp_path: Path) -> None:
    spec = _spec(tmp_path, version="26.2", platform_id="fabric-minecraft-26.2")
    runner = MinecraftTestRunner(project_root=tmp_path, harness_root=FIXTURE)
    runner.validate_spec(spec, java_version="25")
    with pytest.raises(UnsupportedMinecraftEnvironmentError, match="java_version: 25"):
        runner.validate_spec(spec, java_version="21")


@pytest.mark.parametrize(
    ("version", "platform_id"),
    [("26.1.2", "fabric-minecraft-26.1.2"), ("26.2", "fabric-unknown")],
)
def test_unknown_and_26_1_2_platforms_fail_closed(tmp_path: Path, version: str, platform_id: str) -> None:
    with pytest.raises(UnsupportedMinecraftEnvironmentError):
        MinecraftTestRunner(project_root=tmp_path).validate_spec(
            _spec(tmp_path, version=version, platform_id=platform_id), java_version="25"
        )


def test_26_2_spec_round_trip_and_launch_profile_are_yarn_free(tmp_path: Path) -> None:
    spec = _spec(tmp_path, version="26.2", platform_id="fabric-minecraft-26.2")
    restored = MinecraftTestSpec.from_dict(spec.to_dict())
    assert restored.platform_id == "fabric-minecraft-26.2"
    assert "yarn" not in (FIXTURE / "build.gradle.kts").read_text(encoding="utf-8").casefold()
    assert "JavaLanguageVersion.of(25)" in (FIXTURE / "build.gradle.kts").read_text(encoding="utf-8")

    plan = MinecraftTestRunner(project_root=tmp_path, harness_root=FIXTURE).build_launch_plan(
        restored,
        run_id="lot6-26-2",
        java_version="25",
    )
    properties = dict(plan.system_properties)
    assert properties["pd.agent.minecraft.run_id"] == "lot6-26-2"
    assert properties["pd.agent.observationIdentifier"] == "modernfixture:server_core"


def test_26_2_owns_gradle9_wrapper_and_preserves_arguments() -> None:
    wrapper = (FIXTURE / "gradlew.bat").read_text(encoding="utf-8")
    properties = (FIXTURE / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(encoding="utf-8")
    build = (FIXTURE / "build.gradle.kts").read_text(encoding="utf-8")

    assert "gradle-wrapper.jar" in wrapper
    assert "%*" in wrapper
    assert "l11_minecraft_harness" not in wrapper
    assert "gradle-9.5.1-bin.zip" in properties
    assert 'id("net.fabricmc.fabric-loom") version "1.17-SNAPSHOT"' in build
    assert 'implementation("net.fabricmc:fabric-loader:' in build
    assert 'implementation("net.fabricmc.fabric-api:fabric-api:' in build
    assert "modImplementation" not in build
    assert "modRuntimeOnly" not in build
    assert "C:\\dev\\" not in wrapper
    assert "C:\\Users\\" not in wrapper
    assert (FIXTURE / "gradle" / "wrapper" / "gradle-wrapper.jar").is_file()


def test_26_2_wrapper_is_not_the_1_21_11_wrapper() -> None:
    bounded_properties = (FIXTURE / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(encoding="utf-8")
    legacy_properties = (FIXTURE.parent / "l11_minecraft_harness" / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(
        encoding="utf-8"
    )

    assert "gradle-9.5.1-bin.zip" in bounded_properties
    assert "gradle-8.14.3-bin.zip" in legacy_properties


def test_26_2_harness_is_bounded_to_vertical_a_observations() -> None:
    build = (FIXTURE / "build.gradle.kts").read_text(encoding="utf-8")
    java_sources = "\n".join(path.read_text(encoding="utf-8") for path in (FIXTURE / "src" / "main" / "java").rglob("*.java"))
    manifest = json.loads((FIXTURE / "src" / "main" / "resources" / "fabric.mod.json").read_text(encoding="utf-8"))

    assert 'java.srcDir("src/main/java")' in build
    assert "../l11_minecraft_harness/src/main/java" not in build
    assert 'tasks.register<ServerProductionRunTask>("productionServerRun")' in build
    assert manifest["entrypoints"]["server"] == ["dev.pdpunto.l11harness.L262HarnessMod"]
    assert "L11HarnessMod" not in manifest["entrypoints"]["server"]
    assert "net.minecraft.resources.Identifier" in java_sources
    assert "net.minecraft.core.registries.BuiltInRegistries" in java_sources
    assert "net.minecraft.world.item.BlockItem" in java_sources
    assert "ServerLifecycleEvents.SERVER_STARTED" in java_sources
    assert "server.halt(false)" in java_sources
    assert "BuiltInRegistries.BLOCK.getOptional" in java_sources
    assert "BuiltInRegistries.ITEM.getOptional" in java_sources
    assert "instanceof BlockItem" in java_sources
    assert "getBlock()" in java_sources
    assert "blockId.toString().equals(actualId)" in java_sources
    assert "BLOCK_ITEM_ASSOCIATION_MISMATCH" in java_sources


@pytest.mark.parametrize("observation", ["REGISTRY_ENTRY_PRESENT", "BLOCK_ITEM_ASSOCIATION"])
def test_26_2_harness_declares_vertical_a_observation_allowlist(observation: str) -> None:
    source = (FIXTURE / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessConfig26_2.java").read_text(
        encoding="utf-8"
    )

    assert observation in source
    for unsupported in ("ITEM_COMPONENT_STATE", "BLOCK_ENTITY_STATE", "INVENTORY_STATE", "TAG_MEMBERSHIP", "RECIPE_MATCH", "LOOT_RESULT"):
        assert unsupported not in source
