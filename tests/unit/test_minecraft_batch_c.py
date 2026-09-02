from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

from pd_agent.minecraft import (
    MinecraftObservationType,
    MinecraftTestRunner,
    MinecraftTestSpec,
    MinecraftTestStatus,
    MinecraftTestValidationError,
)
from tests.fixtures.artifact_projects import write_jar, write_manifest_jar


ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = ROOT / "tests" / "fixtures" / "l11_minecraft_harness"


def _make_jar(root: Path, name: str = "target.jar") -> Path:
    return write_manifest_jar(
        root / "build" / "libs" / name,
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "pdagentl11",
                "version": "1.0.0",
                "environment": "*",
                "entrypoints": {
                    "main": ["dev.pdpunto.l11.ExampleMod"],
                },
            }
        ),
    )


def _make_manifest_jar(root: Path, manifest: dict[str, object], name: str = "target.jar") -> Path:
    return write_manifest_jar(
        root / "build" / "libs" / name,
        manifest=json.dumps(manifest),
    )


def _make_runtime_mod_jar(root: Path, rel_path: str, *, mod_id: str) -> Path:
    return write_manifest_jar(
        root / rel_path,
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": mod_id,
                "version": "1.0.0",
                "environment": "*",
            }
        ),
    )


def _runner(root: Path) -> MinecraftTestRunner:
    return MinecraftTestRunner(project_root=root, harness_root=HARNESS_ROOT)


def _env_harness(root: Path, sentinel: Path) -> Path:
    harness = root / "harness"
    harness.mkdir(parents=True, exist_ok=True)
    probe = harness / "gradle_env_probe.py"
    probe.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "def _arg(prefix: str) -> str:",
                "    for value in sys.argv[1:]:",
                "        if value.startswith(prefix):",
                "            return value.split('=', 1)[1]",
                "    raise SystemExit(f'missing {prefix}')",
                "result_path = Path(_arg('-Ppd.agent.resultPath='))",
                "run_dir = Path(_arg('-Ppd.agent.runDir='))",
                "target_path = _arg('-Ppd.agent.targetJar=')",
                "target_sha = _arg('-Ppd.agent.targetSha256=')",
                f"Path(r'{sentinel}').write_text(os.environ.get('GRADLE_USER_HOME', ''), encoding='utf-8')",
                "(run_dir / 'logs').mkdir(parents=True, exist_ok=True)",
                "(run_dir / 'logs' / 'latest.log').write_text('latest log', encoding='utf-8')",
                "result_path.write_text(",
                "    json.dumps({",
                "        'schema_version': 1,",
                "        'target_loaded': True,",
                "        'target_origin_resolved': True,",
                "        'runtime_target_path': target_path,",
                "        'runtime_target_sha256': target_sha,",
                "        'target_sha_match': True,",
                "        'server_started': True,",
                "        'functional_test_result': 'PASS',",
                "        'reason': 'ok',",
                "        'shutdown_requested': True,",
                "    }),",
                "    encoding='utf-8'",
                ")",
                "print('harness ok')",
                "raise SystemExit(0)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (harness / "gradlew.bat").write_text(
        "\n".join(
            [
                "@echo off",
                f"\"{sys.executable}\" \"{probe}\" %*",
                "exit /b %ERRORLEVEL%",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (harness / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    return harness


def _spec() -> dict[str, object]:
    return {
        "target_mod_id": "pdagentl11",
        "minecraft_version": "1.21.11",
        "loader_version": "0.19.3",
        "test_id": "block_state_probe",
        "timeout_seconds": 30,
    }


def _fake_process(
    *,
    root: Path,
    run_id: str,
    payload: dict[str, object] | None,
    exit_code: int = 0,
    timed_out: bool = False,
    stdout: str = "stdout",
    stderr: str = "stderr",
    latest_log: str = "latest log",
) -> dict[str, object]:
    evidence_root = root / "evidence" / "minecraft" / run_id
    runtime_root = evidence_root / "runtime"
    (runtime_root / "logs").mkdir(parents=True, exist_ok=True)
    (runtime_root / "logs" / "latest.log").write_text(latest_log, encoding="utf-8")
    if payload is not None:
        (evidence_root / "harness-result.json").write_text(json.dumps(payload), encoding="utf-8")
    return {
        "command_display": "cmd /c gradlew.bat productionServerRun",
        "cwd": root / "tests" / "fixtures" / "l11_minecraft_harness",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "duration_seconds": 1.0,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
    }


def test_run_pass_records_harness_and_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())
    run_id = "run-pass"
    actual_sha = runner.validate_target(spec, java_version="21").sha256

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload={
                "schema_version": 1,
                "test_id": "block_state_probe",
                "target_mod_id": "pdagentl11",
                "target_loaded": True,
                "target_origin_resolved": True,
                "runtime_target_path": str(tmp_path / "build" / "libs" / "target.jar"),
                "runtime_target_sha256": actual_sha,
                "target_sha_match": True,
                "server_started": True,
                "functional_test_result": "PASS",
                "reason": "target verified",
                "shutdown_requested": True,
            },
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(spec, run_id=run_id, java_version="21")

    assert result.status is MinecraftTestStatus.PASS
    assert result.runtime_evidence is not None
    assert result.runtime_evidence.harness_result_path is not None
    assert result.runtime_evidence.harness_result_path.name == "harness-result.json"
    assert result.launch_plan is not None
    assert dict(result.launch_plan.system_properties)["pd.agent.minecraft.result_path"].endswith(
        "harness-result.json"
    )
    assert result.evidence_paths.result_json.exists()
    assert result.evidence_paths.harness_result_json.exists()
    assert result.metadata["launch_mode"] == "pass"
    assert result.metadata["harness_result_state"] == "PASS"


def test_run_propagates_runtime_mod_jars_to_launch_plan_and_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_jar(tmp_path)
    runtime_mod_a = _make_runtime_mod_jar(tmp_path, "mods/a.jar", mod_id="mod-a")
    runtime_mod_b = _make_runtime_mod_jar(tmp_path, "mods/b.jar", mod_id="mod-b")
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe",
        timeout_seconds=30,
        runtime_mod_jars=(Path("mods/b.jar"), Path("mods/a.jar")),
    )
    run_id = "run-runtime-mods"
    actual_sha = runner.validate_target(spec, java_version="21").sha256
    captured: dict[str, object] = {}

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        captured["command"] = tuple(command)
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload={
                "schema_version": 1,
                "test_id": "block_state_probe",
                "target_mod_id": "pdagentl11",
                "target_loaded": True,
                "target_origin_resolved": True,
                "runtime_target_path": str(tmp_path / "build" / "libs" / "target.jar"),
                "runtime_target_sha256": actual_sha,
                "target_sha_match": True,
                "server_started": True,
                "functional_test_result": "PASS",
                "reason": "target verified",
                "shutdown_requested": True,
            },
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(spec, run_id=run_id, java_version="21", authorized_runtime_roots=(tmp_path,))

    assert result.status is MinecraftTestStatus.PASS
    assert result.launch_plan is not None
    assert dict(result.launch_plan.system_properties)["pd.agent.runtimeModJars"] == os.pathsep.join(
        ["mods/a.jar", "mods/b.jar"]
    )
    assert any(
        str(part).startswith("-Ppd.agent.runtimeModJars=") for part in captured["command"]
    )
    runtime_dependency_records = result.metadata["runtime_mod_dependencies"]
    assert [item["path"] for item in runtime_dependency_records] == [
        runtime_mod_a.resolve().as_posix(),
        runtime_mod_b.resolve().as_posix(),
    ]
    assert all(len(item["sha256"]) == 64 for item in runtime_dependency_records)
    assert all(item["source"] is None for item in runtime_dependency_records)
    assert result.runtime_evidence is not None
    assert result.runtime_evidence.metadata["runtime_mod_dependencies"] == runtime_dependency_records


@pytest.mark.parametrize(
    "runtime_mod_jars, setup, expected_message",
    [
        ((Path("mods/missing.jar"),), None, "missing runtime mod dependency"),
        ((Path("mods/not-a-jar.txt"),), "text", "must be a .jar file"),
        ((Path("mods/corrupt.jar"),), "corrupt", "not a valid jar"),
        ((Path("mods/a.jar"), Path("mods/../mods/a.jar")), "valid", "duplicates are not allowed"),
        ((Path("build/libs/../libs/target.jar"),), "target", "cannot be the target jar"),
        ((Path(r"C:\\outside\\mod.jar"),), "outside", "escapes authorized roots"),
    ],
)
def test_run_rejects_invalid_runtime_mod_dependencies_without_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runtime_mod_jars: tuple[Path, ...],
    setup: str | None,
    expected_message: str,
) -> None:
    _make_jar(tmp_path)
    if setup == "text":
        (tmp_path / "mods").mkdir(parents=True, exist_ok=True)
        (tmp_path / "mods" / "not-a-jar.txt").write_text("not a jar", encoding="utf-8")
    elif setup == "corrupt":
        (tmp_path / "mods").mkdir(parents=True, exist_ok=True)
        (tmp_path / "mods" / "corrupt.jar").write_bytes(b"not-a-jar")
    elif setup == "valid":
        _make_runtime_mod_jar(tmp_path, "mods/a.jar", mod_id="mod-a")
    elif setup == "target":
        pass
    elif setup == "outside":
        outside_root = tmp_path.parent / "outside"
        runtime_mod_jars = (outside_root / "mod.jar",)
        _make_runtime_mod_jar(outside_root, "mod.jar", mod_id="mod-outside")

    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe",
        timeout_seconds=30,
        runtime_mod_jars=runtime_mod_jars,
    )
    run_id = "run-invalid-runtime-mods"
    called = False

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        nonlocal called
        called = True
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload={
                "schema_version": 1,
                "test_id": "block_state_probe",
                "target_mod_id": "pdagentl11",
                "target_loaded": True,
                "target_origin_resolved": True,
                "runtime_target_path": str(tmp_path / "build" / "libs" / "target.jar"),
                "runtime_target_sha256": runner.validate_target(spec, java_version="21").sha256,
                "target_sha_match": True,
                "server_started": True,
                "functional_test_result": "PASS",
                "reason": "should not run",
                "shutdown_requested": True,
            },
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(
        spec,
        run_id=run_id,
        java_version="21",
        authorized_runtime_roots=(tmp_path,),
    )

    assert result.status is MinecraftTestStatus.INFRA_ERROR
    assert expected_message in result.reason
    assert result.metadata["phase"] == "preflight"
    assert not called


def test_run_signal_test_id_pass_records_neighbor_trigger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe_with_signal",
        timeout_seconds=30,
        expect_neighbor_update=True,
    )
    run_id = "run-signal-pass"
    actual_sha = runner.validate_target(spec, java_version="21").sha256

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload={
                "schema_version": 1,
                "test_id": "block_state_probe_with_signal",
                "target_mod_id": "pdagentl11",
                "target_loaded": True,
                "target_origin_resolved": True,
                "runtime_target_path": str(tmp_path / "build" / "libs" / "target.jar"),
                "runtime_target_sha256": actual_sha,
                "target_sha_match": True,
                "server_started": True,
                "functional_test_result": "PASS",
                "neighbor_update_triggered": True,
                "reason": "target verified",
                "shutdown_requested": True,
            },
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(spec, run_id=run_id, java_version="21")

    assert result.status is MinecraftTestStatus.PASS
    assert result.reason == "target verified"
    assert result.runtime_evidence is not None
    assert result.runtime_evidence.harness_result_path is not None
    assert result.runtime_evidence.harness_result_path.exists()


def test_run_signal_test_id_missing_neighbor_records_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe_with_signal",
        timeout_seconds=30,
        expect_neighbor_update=True,
    )
    run_id = "run-signal-fail"
    actual_sha = runner.validate_target(spec, java_version="21").sha256

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload={
                "schema_version": 1,
                "test_id": "block_state_probe_with_signal",
                "target_mod_id": "pdagentl11",
                "target_loaded": True,
                "target_origin_resolved": True,
                "runtime_target_path": str(tmp_path / "build" / "libs" / "target.jar"),
                "runtime_target_sha256": actual_sha,
                "target_sha_match": True,
                "server_started": True,
                "functional_test_result": "FAIL",
                "neighbor_update_triggered": False,
                "reason": "neighbor update was not observed",
                "shutdown_requested": True,
            },
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(spec, run_id=run_id, java_version="21")

    assert result.status is MinecraftTestStatus.FAIL
    assert result.reason == "neighbor update was not observed"
    assert result.runtime_evidence is not None
    assert result.runtime_evidence.harness_result_path is not None
    assert result.runtime_evidence.harness_result_path.exists()


def test_run_functional_fail_classifies_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())
    run_id = "run-fail"
    actual_sha = runner.validate_target(spec, java_version="21").sha256

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload={
                "schema_version": 1,
                "test_id": "block_state_probe",
                "target_mod_id": "pdagentl11",
                "target_loaded": True,
                "target_origin_resolved": True,
                "runtime_target_path": str(tmp_path / "build" / "libs" / "target.jar"),
                "runtime_target_sha256": actual_sha,
                "target_sha_match": True,
                "server_started": True,
                "functional_test_result": "FAIL",
                "reason": "expected block state was not observed",
                "shutdown_requested": True,
            },
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(spec, run_id=run_id, java_version="21", launch_mode="functional_fail")

    assert result.status is MinecraftTestStatus.FAIL
    assert result.reason == "expected block state was not observed"


def test_run_expected_sha_mismatch_is_infra_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())
    run_id = "run-sha"
    actual_sha = runner.validate_target(spec, java_version="21").sha256

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload={
                "schema_version": 1,
                "test_id": "block_state_probe",
                "target_mod_id": "pdagentl11",
                "target_loaded": True,
                "target_origin_resolved": True,
                "runtime_target_path": str(tmp_path / "build" / "libs" / "target.jar"),
                "runtime_target_sha256": actual_sha,
                "target_sha_match": False,
                "server_started": True,
                "functional_test_result": "PASS",
                "reason": "target sha mismatch",
                "shutdown_requested": True,
            },
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(
        spec,
        run_id=run_id,
        java_version="21",
        expected_sha256="b" * 64,
    )

    assert result.status is MinecraftTestStatus.INFRA_ERROR
    assert result.reason == "target sha mismatch"


def test_run_missing_result_timeout_and_crash_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())
    runner.validate_target(spec, java_version="21")

    def fake_missing(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(root=self.project_root, run_id="run-missing", payload=None)

    def fake_timeout(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(root=self.project_root, run_id="run-timeout", payload=None, timed_out=True)

    def fake_crash(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(root=self.project_root, run_id="run-crash", payload=None, exit_code=1)

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_missing)
    missing = runner.run(spec, run_id="run-missing", java_version="21", launch_mode="missing_result")
    assert missing.status is MinecraftTestStatus.INFRA_ERROR

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_timeout)
    timeout = runner.run(spec, run_id="run-timeout", java_version="21", launch_mode="hang")
    assert timeout.status is MinecraftTestStatus.TIMEOUT

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_crash)
    crash = runner.run(spec, run_id="run-crash", java_version="21", launch_mode="crash")
    assert crash.status is MinecraftTestStatus.CRASH


def test_b003_signal_test_id_does_not_override_neighbor_flag(tmp_path: Path) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)

    spec_true = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe_with_signal",
        timeout_seconds=30,
        expect_neighbor_update=True,
    )
    plan_true = runner.build_launch_plan(spec_true, run_id="run-signal-true", java_version="21")

    spec_false = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe_with_signal",
        timeout_seconds=30,
        expect_neighbor_update=False,
    )
    plan_false = runner.build_launch_plan(spec_false, run_id="run-signal-false", java_version="21")

    assert dict(plan_true.system_properties)["pd.agent.minecraft.test_id"] == "block_state_probe_with_signal"
    assert dict(plan_true.system_properties)["pd.agent.targetEntrypointClass"] == "dev.pdpunto.l11.ExampleMod"
    assert dict(plan_true.system_properties)["pd.agent.minecraft.expect_neighbor_update"] == "true"
    assert dict(plan_false.system_properties)["pd.agent.minecraft.test_id"] == "block_state_probe_with_signal"
    assert dict(plan_false.system_properties)["pd.agent.targetEntrypointClass"] == "dev.pdpunto.l11.ExampleMod"
    assert dict(plan_false.system_properties)["pd.agent.minecraft.expect_neighbor_update"] == "false"


def test_runner_preserves_generic_observation_labels_in_launch_plan(tmp_path: Path) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="server_registry_presence",
        observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
        observation_params={"registry_kind": "block", "identifier": "minecraft:diamond_block"},
        timeout_seconds=30,
        expect_neighbor_update=False,
    )

    plan = runner.build_launch_plan(spec, run_id="run-generic-observation", java_version="21")

    assert dict(plan.system_properties)["pd.agent.minecraft.test_id"] == "server_registry_presence"
    assert dict(plan.system_properties)["pd.agent.observationType"] == "REGISTRY_ENTRY_PRESENT"
    assert dict(plan.system_properties)["pd.agent.observationRegistryKind"] == "block"
    assert dict(plan.system_properties)["pd.agent.observationIdentifier"] == "minecraft:diamond_block"
    assert dict(plan.system_properties)["pd.agent.minecraft.expect_neighbor_update"] == "false"


def test_runner_maps_registry_harness_result_to_structured_observation(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    status, reason, metadata = runner._classify_runtime(
        process={"timed_out": False, "exit_code": 0},
        harness_result={
            "test_id": "F6-T3:primary",
            "observation_type": "REGISTRY_ENTRY_PRESENT",
            "registry_kind": "block",
            "observed_identifier": "examplemod:server_core",
            "target_loaded": True,
            "target_origin_resolved": True,
            "target_sha_match": True,
            "server_started": True,
            "functional_test_result": "PASS",
            "shutdown_requested": True,
            "reason": "target verified",
        },
        latest_log="",
        launch_mode="pass",
        target=type("Target", (), {"path": Path("target.jar"), "sha256": "a" * 64, "mod_id": "examplemod"})(),
        timeout_seconds=30,
    )

    assert status is MinecraftTestStatus.PASS
    assert reason == "target verified"
    assert metadata["observation_result"]["observation_id"] == "F6-T3:primary"
    assert metadata["observation_result"]["actual"]["present"] is True


def test_runner_preserves_contract_observation_id_over_harness_test_id(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    status, _reason, metadata = runner._classify_runtime(
        process={"timed_out": False, "exit_code": 0},
        harness_result={
            "test_id": "harness-technical-id",
            "observation_type": "REGISTRY_ENTRY_PRESENT",
            "registry_kind": "block",
            "observed_identifier": "examplemod:server_core",
            "target_loaded": True,
            "target_origin_resolved": True,
            "target_sha_match": True,
            "server_started": True,
            "functional_test_result": "PASS",
            "shutdown_requested": True,
        },
        latest_log="",
        launch_mode="pass",
        target=type("Target", (), {"path": Path("target.jar"), "sha256": "a" * 64, "mod_id": "examplemod"})(),
        timeout_seconds=30,
        observation_id="server-core-registry",
    )

    assert status is MinecraftTestStatus.PASS
    assert metadata["observation_result"]["observation_id"] == "server-core-registry"
    assert metadata["harness_test_id"] == "harness-technical-id"


def test_runner_rejects_missing_or_ambiguous_main_entrypoint(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    _make_manifest_jar(
        tmp_path,
        {
            "schemaVersion": 1,
            "id": "pdagentl11",
            "version": "1.0.0",
            "environment": "*",
            "entrypoints": {},
        },
        name="missing-main.jar",
    )
    _make_manifest_jar(
        tmp_path,
        {
            "schemaVersion": 1,
            "id": "pdagentl11",
            "version": "1.0.0",
            "environment": "*",
            "entrypoints": {
                "main": ["dev.pdpunto.l11.ExampleMod", "dev.pdpunto.l11.OtherMod"],
            },
        },
        name="ambiguous-main.jar",
    )
    missing_manifest = write_jar(
        tmp_path / "build" / "libs" / "missing-manifest.jar",
        files={"README.txt": "no manifest here"},
    )
    malformed_manifest = write_jar(
        tmp_path / "build" / "libs" / "malformed-manifest.jar",
        files={
            "fabric.mod.json": "{not-json",
        },
    )

    missing_spec = MinecraftTestSpec(
        target_jar=Path("build/libs/missing-main.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe",
        timeout_seconds=30,
    )
    missing_manifest_spec = MinecraftTestSpec(
        target_jar=Path("build/libs/missing-manifest.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe",
        timeout_seconds=30,
    )
    malformed_manifest_spec = MinecraftTestSpec(
        target_jar=Path("build/libs/malformed-manifest.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe",
        timeout_seconds=30,
    )
    ambiguous_spec = MinecraftTestSpec(
        target_jar=Path("build/libs/ambiguous-main.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="block_state_probe",
        timeout_seconds=30,
    )

    with pytest.raises(MinecraftTestValidationError, match="missing fabric.mod.json"):
        runner.build_launch_plan(missing_manifest_spec, run_id="missing-manifest", java_version="21")
    with pytest.raises(MinecraftTestValidationError, match="fabric.mod.json is not valid JSON"):
        runner.build_launch_plan(malformed_manifest_spec, run_id="malformed-manifest", java_version="21")
    with pytest.raises(MinecraftTestValidationError, match="main entrypoint"):
        runner.build_launch_plan(missing_spec, run_id="missing-main", java_version="21")
    with pytest.raises(MinecraftTestValidationError, match="main entrypoint"):
        runner.build_launch_plan(ambiguous_spec, run_id="ambiguous-main", java_version="21")


def test_run_propagates_gradle_user_home_to_harness_wrapper(tmp_path: Path) -> None:
    _make_jar(tmp_path)
    sentinel = tmp_path / "gradle-user-home.txt"
    harness_root = _env_harness(tmp_path, sentinel)
    runner = MinecraftTestRunner(
        project_root=tmp_path,
        harness_root=harness_root,
        environment_overrides={"GRADLE_USER_HOME": str(tmp_path / "isolated-gradle-home")},
    )
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())

    result = runner.run(spec, run_id="run-env", java_version="21")

    assert result.status is MinecraftTestStatus.PASS
    assert sentinel.read_text(encoding="utf-8") == str(tmp_path / "isolated-gradle-home")
    assert result.process_evidence is not None
    assert result.process_evidence.metadata["environment_overrides"]["GRADLE_USER_HOME"] == str(tmp_path / "isolated-gradle-home")


def test_run_missing_harness_result_with_target_entrypoint_failure_is_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())
    run_id = "run-target-startup-crash"

    latest_log = """
[main/ERROR]: Failed to start the minecraft server
java.lang.RuntimeException: Could not execute entrypoint stage 'main' due to errors, provided by 'pdagentl11' at 'dev.pdpunto.l11.ExampleMod'!
Caused by: java.lang.ExceptionInInitializerError
Caused by: java.lang.NullPointerException: Item id not set
    at dev.pdpunto.l11.ExampleMod.<clinit>(ExampleMod.java:17)
""".strip()

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload=None,
            exit_code=0,
            latest_log=latest_log,
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(spec, run_id=run_id, java_version="21")

    assert result.status is MinecraftTestStatus.CRASH
    assert result.reason == "target mod failed during Minecraft startup"
    assert result.runtime_evidence is not None
    runtime_metadata = result.runtime_evidence.metadata
    assert runtime_metadata["classification"] == "CRASH"
    assert runtime_metadata["target_startup_failure"] is True
    assert "provided by 'pdagentl11'" in runtime_metadata["target_startup_failure_evidence"]
    assert result.target_failure_reason == "Item id not set"
    assert runtime_metadata["target_failure_reason"] == "Item id not set"


@pytest.mark.parametrize("cause", ["Item id not set", "Block id not set"])
def test_target_startup_failure_preserves_compact_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cause: str,
) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())
    run_id = f"run-target-startup-{cause.split()[0].casefold()}"
    latest_log = f"""
[main/ERROR]: Failed to start the minecraft server
java.lang.RuntimeException: Could not execute entrypoint stage 'main' due to errors, provided by 'pdagentl11' at 'dev.pdpunto.l11.ExampleMod'!
Caused by: java.lang.ExceptionInInitializerError
Caused by: java.lang.NullPointerException: {cause}
""".strip()

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(root=self.project_root, run_id=run_id, payload=None, exit_code=1, latest_log=latest_log)

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)
    result = runner.run(spec, run_id=run_id, java_version="21")

    assert result.status is MinecraftTestStatus.CRASH
    assert result.reason == "target mod failed during Minecraft startup"
    assert result.target_failure_reason == cause
    assert result.runtime_evidence is not None
    assert result.runtime_evidence.metadata["target_failure_reason"] == cause


def test_run_missing_harness_result_without_target_failure_remains_infra_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())
    run_id = "run-genuine-missing-result"

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload=None,
            exit_code=0,
            latest_log="Minecraft started but no harness result was written.",
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(
        spec,
        run_id=run_id,
        java_version="21",
        launch_mode="missing_result",
    )

    assert result.status is MinecraftTestStatus.INFRA_ERROR
    assert result.reason == "missing harness result"
    assert result.runtime_evidence is not None
    assert result.runtime_evidence.metadata["classification"] == "INFRA_ERROR"


def test_run_nonzero_exit_with_target_entrypoint_failure_marks_target_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(target_jar=Path("build/libs/target.jar"), **_spec())
    run_id = "run-target-startup-crash-nonzero"

    latest_log = """
[main/ERROR]: Failed to start the minecraft server
java.lang.RuntimeException: Could not execute entrypoint stage 'main' due to errors, provided by 'pdagentl11' at 'dev.pdpunto.l11.ExampleMod'!
Caused by: java.lang.NullPointerException: Item id not set
""".strip()

    def fake_run_command(self, command, *, cwd, timeout_seconds):  # noqa: ANN001
        return _fake_process(
            root=self.project_root,
            run_id=run_id,
            payload=None,
            exit_code=1,
            latest_log=latest_log,
        )

    monkeypatch.setattr(MinecraftTestRunner, "_run_command", fake_run_command)

    result = runner.run(spec, run_id=run_id, java_version="21")

    assert result.status is MinecraftTestStatus.CRASH
    assert result.reason == "target mod failed during Minecraft startup"
    assert result.runtime_evidence is not None
    assert result.runtime_evidence.metadata["target_startup_failure"] is True
