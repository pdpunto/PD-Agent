from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import zipfile

from pd_agent.minecraft import (
    MinecraftObservationType,
    MinecraftTestRunner,
    MinecraftTestSpec,
    MinecraftTestStatus,
    PersistencePhase,
    PersistenceScenario,
)


SHA = "a" * 64


def _scenario() -> PersistenceScenario:
    return PersistenceScenario(
        scenario_id="persistence-001",
        world_id="world-001",
        world_root="world",
        target_artifact_sha256=SHA,
        test_id="persistence-b",
        phase=PersistencePhase.PHASE_1,
        expected_observation_id="inventory-before-save",
        process_id="phase-1-process",
    )


def _spec(tmp_path: Path) -> MinecraftTestSpec:
    target = tmp_path / "target.jar"
    with zipfile.ZipFile(target, "w") as jar:
        jar.writestr(
            "fabric.mod.json",
            '{"schemaVersion":1,"id":"pdagentl11","version":"1.0.0","entrypoints":{"main":["dev.pdpunto.l11.ExampleMod"]}}',
        )
    return MinecraftTestSpec(
        target_jar=Path("target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="persistence-b",
        timeout_seconds=30,
        observation_type=MinecraftObservationType.INVENTORY_STATE,
        observation_params={"slot": 0, "item_id": "minecraft:diamond", "count": 5},
    )


def test_persistence_launch_plan_is_owned_and_phase_scoped(tmp_path: Path) -> None:
    runner = MinecraftTestRunner(project_root=tmp_path)
    spec = _spec(tmp_path)
    scenario = _scenario()

    plan = runner.build_launch_plan(
        spec,
        run_id="phase-1",
        runtime_run_dir=tmp_path / "owned-execution",
        persistence_phase=PersistencePhase.PHASE_1,
        persistence_scenario=scenario,
        persistence_evidence_path=tmp_path / "lifecycle.json",
    )

    props = dict(plan.system_properties)
    assert plan.run_dir == (tmp_path / "owned-execution").resolve()
    assert props["pd.agent.persistencePhase"] == "PHASE_1"
    assert props["pd.agent.persistenceScenarioId"] == scenario.scenario_id
    assert props["pd.agent.persistenceWorldId"] == scenario.world_id


def test_persistence_rejects_non_reopenable_world_before_phase_two(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = MinecraftTestRunner(project_root=tmp_path)
    spec = _spec(tmp_path)
    calls: list[str] = []
    (tmp_path / "execution").mkdir()

    def fake_run(*args, run_id: str, **kwargs):
        calls.append(run_id)
        (tmp_path / "execution" / "world").mkdir(parents=True)
        evidence_path = kwargs["persistence_evidence_path"]
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            '{"before_save":"t","after_save":"t","save_completed":"t","world_unload":"t","shutdown_initiated":"t"}',
            encoding="utf-8",
        )
        return SimpleNamespace(
            status=MinecraftTestStatus.PASS,
            process_evidence=None,
        )

    monkeypatch.setattr(MinecraftTestRunner, "run", fake_run)
    result = runner.run_persistence(spec, _scenario(), authorized_root=tmp_path / "execution")

    assert result.status == "INVALID"
    assert result.reason == "owned world root is not reopenable"
    assert calls == ["persistence-001-phase-1"]


def test_inventory_runtime_uses_persisted_mismatch_error_code(tmp_path: Path) -> None:
    runner = MinecraftTestRunner(project_root=tmp_path)
    spec = _spec(tmp_path)
    target = runner.validate_target(spec, java_version="21")
    status, _, metadata = runner._classify_runtime(
        process={"timed_out": False, "exit_code": 0},
        harness_result={
            "target_loaded": True,
            "target_origin_resolved": True,
            "target_sha_match": True,
            "server_started": True,
            "functional_test_result": "FAIL",
            "shutdown_requested": True,
            "reason": "persisted inventory mismatch",
            "observation_type": "INVENTORY_STATE",
            "test_id": "persistence-b",
            "observation_expected": {"count": 5},
            "observation_actual": {"count": 0},
            "error_code": "PERSISTED_STATE_MISMATCH",
        },
        latest_log=None,
        launch_mode="pass",
        target=target,
        timeout_seconds=30,
        persistence_phase=PersistencePhase.PHASE_2.value,
    )

    assert status is MinecraftTestStatus.FAIL
    assert metadata["persistence_phase"] == "PHASE_2"
    assert metadata["observation_result"]["error"]["code"] == "PERSISTED_STATE_MISMATCH"


def test_persistence_profile_does_not_enable_i8_load_callback() -> None:
    source = Path("tests/fixtures/l11_minecraft_harness/src/main/java/dev/pdpunto/l11harness/L11HarnessMod.java").read_text(encoding="utf-8")
    assert '"i8_world_load_effect".equals(System.getProperty("pd.agent.eventProfile"))' in source
    assert "isPersistence()" in source
