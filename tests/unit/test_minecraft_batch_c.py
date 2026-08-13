from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

from pd_agent.minecraft import MinecraftTestRunner, MinecraftTestSpec, MinecraftTestStatus, MinecraftTestValidationError
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
) -> dict[str, object]:
    evidence_root = root / "evidence" / "minecraft" / run_id
    runtime_root = evidence_root / "runtime"
    (runtime_root / "logs").mkdir(parents=True, exist_ok=True)
    (runtime_root / "logs" / "latest.log").write_text("latest log", encoding="utf-8")
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
