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
