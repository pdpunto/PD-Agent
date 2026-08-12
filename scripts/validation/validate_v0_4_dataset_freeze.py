"""PD Agent v0.4 dataset freeze validator.

Mantainable, reproducible validator for the 11 v0.4 freeze controls.
No fixture canonical tree is modified; all work happens on temp copies.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
REPO_ROOT = SCRIPT_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import validate_v0_1 as base
from pd_agent.benchmark.workspace import compute_fixture_identity
from pd_agent.minecraft import MinecraftTestRunner, MinecraftTestSpec


BENCHMARK_ROOT = REPO_ROOT / "benchmarks"
CANONICAL_TARGET_NAME = "l11_fabric_fixture"
CANONICAL_HARNESS_NAME = "l11_minecraft_harness"
DEFAULT_VALIDATION_ROOT = Path(tempfile.gettempdir()) / "pd-agent-v0.4-dataset-freeze"
DEFAULT_GRADLE_HOME = Path.home() / ".gradle"
DEFAULT_GRADLE_EXE = Path(r"C:\Users\Usuario\.gradle\wrapper\dists\gradle-8.14.3-bin\cv11ve7ro1n3o1j4so8xd9n66\gradle-8.14.3\bin\gradle.bat")
DEFAULT_PYTHON_EXE = Path(r"C:\dev\proyectos\PD-Agent\.venv-l0fix\Scripts\python.exe")
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_JAVA_VERSION = "21"
DEFAULT_MINECRAFT_VERSION = "1.21.11"
DEFAULT_LOADER_VERSION = "0.19.3"
DEFAULT_TARGET_MOD_ID = "pdagentl11"
DEFAULT_TEST_ID_B001_B002 = "block_state_probe"
DEFAULT_TEST_ID_B003 = "block_state_probe_with_signal"
EXPECTED_FIXTURE_HASH = "c2648999209fa4d92f901b0c54517595da6152a14f6e9bc8c0dc27ecc0707e4f"
IGNORED_COPY_DIRS = tuple(sorted(name for name in base.IGNORED_COPY_DIRS if name != ".gradle"))


def _b001_b003_positive_source(*, vanilla_identifier: bool) -> str:
    identifier_line = (
        '    private static final Identifier PROBE_ID = Identifier.ofVanilla("diamond_block");'
        if vanilla_identifier
        else '    private static final Identifier PROBE_ID = Identifier.of("minecraft", "diamond_block");'
    )
    return (
        "package dev.pdpunto.l11;\n\n"
        "import net.fabricmc.api.ModInitializer;\n"
        "import net.minecraft.block.Block;\n"
        "import net.minecraft.block.BlockState;\n"
        "import net.minecraft.registry.Registries;\n"
        "import net.minecraft.server.world.ServerWorld;\n"
        "import net.minecraft.util.Identifier;\n"
        "import net.minecraft.util.math.BlockPos;\n\n"
        "public final class ExampleMod implements ModInitializer {\n"
        '    public static final String MOD_ID = "pdagentl11";\n'
        f"{identifier_line}\n"
        "    private static final BlockState PROBE_STATE = Registries.BLOCK.get(PROBE_ID).getDefaultState();\n\n"
        "    @Override\n"
        "    public void onInitialize() {\n"
        "        // Intentionally empty. The batch-B acceptance uses the public server-side helper below.\n"
        "    }\n\n"
        "    public static boolean applyProbeState(ServerWorld world, BlockPos pos) {\n"
        "        return world.setBlockState(pos, PROBE_STATE, Block.NOTIFY_ALL);\n"
        "    }\n\n"
        "    public static Identifier probeIdentifier() {\n"
        "        return PROBE_ID;\n"
        "    }\n\n"
        "    public static BlockState expectedProbeState() {\n"
        "        return PROBE_STATE;\n"
        "    }\n"
        "}\n"
    )


def _b002_positive_source() -> str:
    return (
        "package dev.pdpunto.l11;\n\n"
        "import net.fabricmc.api.ModInitializer;\n"
        "import net.minecraft.block.Block;\n"
        "import net.minecraft.block.BlockState;\n"
        "import net.minecraft.block.Blocks;\n"
        "import net.minecraft.server.world.ServerWorld;\n"
        "import net.minecraft.util.Identifier;\n"
        "import net.minecraft.registry.Registries;\n"
        "import net.minecraft.util.math.BlockPos;\n\n"
        "public final class ExampleMod implements ModInitializer {\n"
        '    public static final String MOD_ID = "pdagentl11";\n'
        '    private static final Identifier PROBE_ID = Identifier.ofVanilla("diamond_block");\n'
        "    private static final BlockState PROBE_STATE = Registries.BLOCK.get(PROBE_ID).getDefaultState();\n\n"
        "    @Override\n"
        "    public void onInitialize() {\n"
        "        // Intentionally empty. The batch-B acceptance uses the public server-side helper below.\n"
        "    }\n\n"
        "    public static boolean applyProbeState(ServerWorld world, BlockPos pos) {\n"
        "        return world.setBlockState(pos, PROBE_STATE, Block.NOTIFY_ALL);\n"
        "    }\n\n"
        "    public static Identifier probeIdentifier() {\n"
        "        return PROBE_ID;\n"
        "    }\n\n"
        "    public static BlockState expectedProbeState() {\n"
        "        return PROBE_STATE;\n"
        "    }\n"
        "}\n"
    )


def _b003_flag_only_source() -> str:
    return (
        "package dev.pdpunto.l11;\n\n"
        "import net.fabricmc.api.ModInitializer;\n"
        "import net.minecraft.block.Block;\n"
        "import net.minecraft.block.BlockState;\n"
        "import net.minecraft.block.Blocks;\n"
        "import net.minecraft.server.world.ServerWorld;\n"
        "import net.minecraft.util.math.BlockPos;\n\n"
        "public final class ExampleMod implements ModInitializer {\n"
        '    public static final String MOD_ID = "pdagentl11";\n'
        "    private static final BlockState PROBE_STATE = Blocks.DIAMOND_BLOCK.getDefaultState();\n\n"
        "    @Override\n"
        "    public void onInitialize() {\n"
        "        // Flag-only control: compile-safe noise, no registry lookup.\n"
        "    }\n\n"
        "    public static boolean applyProbeState(ServerWorld world, BlockPos pos) {\n"
        "        return world.setBlockState(pos, PROBE_STATE, Block.NOTIFY_ALL);\n"
        "    }\n\n"
        "    public static BlockState expectedProbeState() {\n"
        "        return PROBE_STATE;\n"
        "    }\n"
        "}\n"
    )


def _b003_registry_only_source() -> str:
    return _b001_b003_positive_source(vanilla_identifier=False).replace("Block.NOTIFY_ALL", "Block.NOTIFY_NEIGHBORS")


def _b003_missing_neighbor_harness_source(original: str) -> str:
    old = "        boolean neighborTriggered = config.expectNeighborUpdate() && waitForObserverPowered(world, true, neighborWaitMillis);"
    new = "        boolean neighborTriggered = false; // validation-only negative control"
    if old not in original:
        raise RuntimeError("neighbor trigger line not found")
    return original.replace(old, new, 1)


def _dedent_multiline(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256_text(text: str) -> str:
    return base._sha256_text(text)


def _json_write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _git_status_dirty(stdout: str) -> bool:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return any(not line.startswith("##") for line in lines)


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    extra_env: Mapping[str, str] | None = None,
) -> base.CommandResult:
    return base._run_command(command, cwd=cwd, timeout_seconds=timeout_seconds, extra_env=extra_env)


def _gradle_command(gradle_exe: Path, project_root: Path, args: Sequence[str]) -> list[str]:
    return ["cmd", "/c", str(gradle_exe), "-p", str(project_root), *args]


def _repo_git(*args: str, timeout_seconds: int = 30) -> base.CommandResult:
    return _run_command(["git", *args], cwd=REPO_ROOT, timeout_seconds=timeout_seconds)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_task_manifest(task_id: str, version: str) -> dict[str, Any]:
    path = BENCHMARK_ROOT / "tasks" / f"{task_id}-v{version}.json"
    return dict(_load_json(path))


def _fixture_source(task_id: str, version: str) -> Path:
    return BENCHMARK_ROOT / "fixtures" / f"{task_id}-v{version}"


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*IGNORED_COPY_DIRS))


def _target_source_path(target_root: Path) -> Path:
    return target_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11" / "ExampleMod.java"


def _harness_source_path(harness_root: Path) -> Path:
    return harness_root / "src" / "main" / "java" / "dev" / "pdpunto" / "l11harness" / "HarnessRunner.java"


def _case_fixture_identity(task_id: str, version: str) -> str:
    return compute_fixture_identity(_fixture_source(task_id, version))


def _assert_fixture_identity_matches_manifest(task_id: str, version: str) -> None:
    manifest = _load_task_manifest(task_id, version)
    computed = _case_fixture_identity(task_id, version)
    expected = str(manifest["fixture"]["fixture_identity"])
    if computed != expected:
        raise RuntimeError(
            f"fixture identity mismatch for {task_id}-v{version}: computed={computed} expected={expected}"
        )


def _prepare_case_workspace(root: Path, task_id: str, version: str) -> tuple[Path, Path, Path]:
    case_root = root / "cases" / f"{task_id}-v{version}"
    target_root = case_root / "workspace" / "tests" / "fixtures" / CANONICAL_TARGET_NAME
    harness_root = case_root / "workspace" / "tests" / "fixtures" / CANONICAL_HARNESS_NAME
    evidence_root = root / "evidence" / f"{task_id}-v{version}"
    _copy_tree(_fixture_source(task_id, version), target_root)
    _copy_tree(REPO_ROOT / "tests" / "fixtures" / CANONICAL_HARNESS_NAME, harness_root)
    evidence_root.mkdir(parents=True, exist_ok=True)
    return target_root, harness_root, evidence_root


def _edit_source(path: Path, text: str) -> None:
    _write_text(path, text)


def _edit_harness_for_missing_neighbor(path: Path) -> None:
    original = _read_text(path)
    updated = _b003_missing_neighbor_harness_source(original)
    _write_text(path, updated)


def _parse_harness_result(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return dict(_load_json(path))


def _read_tail(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return base._tail(_read_text(path))


def _jar_sha256(path: Path) -> str:
    import hashlib

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _run_gradle_build(
    *,
    gradle_exe: Path,
    project_root: Path,
    gradle_user_home: Path,
    timeout_seconds: int,
    label: str,
) -> base.CommandResult:
    command = _gradle_command(gradle_exe, project_root, ["build", "--offline", "--no-daemon", "--stacktrace", "--console=plain"])
    result = _run_command(command, cwd=project_root, timeout_seconds=timeout_seconds, extra_env={"GRADLE_USER_HOME": str(gradle_user_home)})
    return result


def _build_target_jar(project_root: Path) -> Path:
    jar = project_root / "build" / "libs" / "pd-agent-l11-fixture.jar"
    if not jar.exists():
        jars = sorted((project_root / "build" / "libs").glob("*.jar"))
        if not jars:
            raise FileNotFoundError(f"target jar not found in {project_root / 'build' / 'libs'}")
        return jars[0]
    return jar


def _build_harness_jar(project_root: Path) -> Path:
    jar = project_root / "build" / "libs" / "pd-agent-l11-harness.jar"
    if not jar.exists():
        jars = sorted((project_root / "build" / "libs").glob("*.jar"))
        if not jars:
            raise FileNotFoundError(f"harness jar not found in {project_root / 'build' / 'libs'}")
        return jars[0]
    return jar


@dataclass(slots=True)
class CaseResult:
    task: str
    control: str
    expected: str
    actual_acceptance: str
    control_result: str
    build: str
    artifact: str
    minecraft: str
    neighbor: str
    task_version: str
    fixture_path: str
    fixture_identity_before: str | None = None
    fixture_identity_after: str | None = None
    source_before_hash: str | None = None
    source_after_hash: str | None = None
    source_diff: str | None = None
    target_jar: str | None = None
    target_jar_sha256: str | None = None
    harness_result: dict[str, Any] | None = None
    build_stdout_tail: str | None = None
    build_stderr_tail: str | None = None
    harness_build_stdout_tail: str | None = None
    harness_build_stderr_tail: str | None = None
    harness_run_stdout_tail: str | None = None
    harness_run_stderr_tail: str | None = None
    evidence_root: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "task_version": self.task_version,
            "control": self.control,
            "expected": self.expected,
            "actual_acceptance": self.actual_acceptance,
            "control_result": self.control_result,
            "build": self.build,
            "artifact": self.artifact,
            "minecraft": self.minecraft,
            "neighbor": self.neighbor,
            "fixture_path": self.fixture_path,
            "fixture_identity_before": self.fixture_identity_before,
            "fixture_identity_after": self.fixture_identity_after,
            "source_before_hash": self.source_before_hash,
            "source_after_hash": self.source_after_hash,
            "source_diff": self.source_diff,
            "target_jar": self.target_jar,
            "target_jar_sha256": self.target_jar_sha256,
            "harness_result": self.harness_result,
            "build_stdout_tail": self.build_stdout_tail,
            "build_stderr_tail": self.build_stderr_tail,
            "harness_build_stdout_tail": self.harness_build_stdout_tail,
            "harness_build_stderr_tail": self.harness_build_stderr_tail,
            "harness_run_stdout_tail": self.harness_run_stdout_tail,
            "harness_run_stderr_tail": self.harness_run_stderr_tail,
            "evidence_root": self.evidence_root,
            "error": self.error,
        }


@dataclass(slots=True)
class ValidationSummary:
    started_at: datetime
    repo_root: Path
    validation_root: Path
    branch: str | None = None
    head: str | None = None
    origin_main: str | None = None
    git_status_before: str | None = None
    git_status_after: str | None = None
    cases: list[CaseResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    finished_at: datetime | None = None

    @property
    def ready(self) -> bool:
        return len(self.cases) == 11 and all(case.control_result == "PASS" for case in self.cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "repo_root": str(self.repo_root),
            "validation_root": str(self.validation_root),
            "branch": self.branch,
            "head": self.head,
            "origin_main": self.origin_main,
            "git_status_before": self.git_status_before,
            "git_status_after": self.git_status_after,
            "ready": self.ready,
            "error": self.error,
            "notes": list(self.notes),
            "cases": [case.to_dict() for case in self.cases],
            "table": self.table(),
        }

    def table(self) -> str:
        lines = ["Task | Control | Build | Artifact | Minecraft | Neighbor | Acceptance | Expected | Control result"]
        lines.append("--- | --- | --- | --- | --- | --- | --- | --- | ---")
        for case in self.cases:
            lines.append(
                f"{case.task} | {case.control} | {case.build} | {case.artifact} | {case.minecraft} | {case.neighbor} | {case.actual_acceptance} | {case.expected} | {case.control_result}"
            )
        return "\n".join(lines)


@dataclass(slots=True)
class ControlSpec:
    task: str
    task_version: str
    control: str
    expected: str
    fixture_version: str
    source_edit: Callable[[Path], None] | None = None
    harness_edit: Callable[[Path], None] | None = None
    run_minecraft: bool = False
    expect_neighbor_update: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PD Agent v0.4 dataset freeze validator")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--validation-root", type=Path, default=DEFAULT_VALIDATION_ROOT)
    parser.add_argument("--gradle-exe", type=Path, default=DEFAULT_GRADLE_EXE)
    parser.add_argument("--gradle-user-home", type=Path, default=DEFAULT_GRADLE_HOME)
    parser.add_argument("--python-exe", type=Path, default=DEFAULT_PYTHON_EXE)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--keep-working-copy", action="store_true")
    return parser


def _control_specs() -> tuple[ControlSpec, ...]:
    return (
        ControlSpec("B001", "1", "baseline", "FAIL", "1", run_minecraft=True, expect_neighbor_update=False),
        ControlSpec(
            "B001",
            "1",
            "positive",
            "PASS",
            "1",
            source_edit=lambda root: _edit_source(_target_source_path(root), _b001_b003_positive_source(vanilla_identifier=False)),
            run_minecraft=True,
            expect_neighbor_update=False,
        ),
        ControlSpec("B002", "2", "baseline", "FAIL", "2", run_minecraft=False),
        ControlSpec(
            "B002",
            "2",
            "irrelevant",
            "FAIL",
            "2",
            source_edit=lambda root: _edit_source(
                _target_source_path(root),
                _read_text(_target_source_path(root)).replace(
                    "// Intentionally empty. The batch-B acceptance uses the public server-side helper below.",
                    "// Still empty.",
                ),
            ),
            run_minecraft=False,
        ),
        ControlSpec(
            "B002",
            "2",
            "forbidden",
            "FAIL",
            "2",
            source_edit=lambda root: _edit_source(
                _target_source_path(root),
                (
                    "package dev.pdpunto.l11;\n\n"
                    "import net.fabricmc.api.ModInitializer;\n"
                    "import net.minecraft.block.Block;\n"
                    "import net.minecraft.block.BlockState;\n"
                    "import net.minecraft.block.Blocks;\n"
                    "import net.minecraft.server.world.ServerWorld;\n"
                    "import net.minecraft.util.Identifier;\n"
                    "import net.minecraft.registry.Registries;\n"
                    "import net.minecraft.util.math.BlockPos;\n\n"
                    "public final class ExampleMod implements ModInitializer {\n"
                    '    public static final String MOD_ID = "pdagentl11";\n'
                    '    private static final Identifier PROBE_ID = Identifier.of("minecraft", "diamond_block");\n'
                    "    private static final BlockState PROBE_STATE = Registries.BLOCK.get(PROBE_ID).getDefaultState();\n\n"
                    "    @Override\n"
                    "    public void onInitialize() {\n"
                    "        // Intentionally empty. The batch-B acceptance uses the public server-side helper below.\n"
                    "    }\n\n"
                    "    public static boolean applyProbeState(ServerWorld world, BlockPos pos) {\n"
                    "        return world.setBlockState(pos, PROBE_STATE, Block.NOTIFY_ALL);\n"
                    "    }\n\n"
                    "    public static Identifier probeIdentifier() {\n"
                    "        return PROBE_ID;\n"
                    "    }\n\n"
                    "    public static BlockState expectedProbeState() {\n"
                    "        return PROBE_STATE;\n"
                    "    }\n"
                    "}\n"
                ),
            ),
            run_minecraft=False,
        ),
        ControlSpec(
            "B002",
            "2",
            "positive",
            "PASS",
            "2",
            source_edit=lambda root: _edit_source(_target_source_path(root), _b002_positive_source()),
            run_minecraft=False,
        ),
        ControlSpec("B003", "2", "baseline", "FAIL", "2", run_minecraft=True, expect_neighbor_update=True),
        ControlSpec(
            "B003",
            "2",
            "registry-only",
            "FAIL",
            "2",
            source_edit=lambda root: _edit_source(_target_source_path(root), _b003_registry_only_source()),
            run_minecraft=True,
            expect_neighbor_update=True,
        ),
        ControlSpec(
            "B003",
            "2",
            "flag-only",
            "FAIL",
            "2",
            source_edit=lambda root: _edit_source(_target_source_path(root), _b003_flag_only_source()),
            run_minecraft=True,
            expect_neighbor_update=True,
        ),
        ControlSpec(
            "B003",
            "2",
            "missing-neighbor",
            "FAIL",
            "2",
            source_edit=lambda root: _edit_source(_target_source_path(root), _b001_b003_positive_source(vanilla_identifier=False)),
            harness_edit=lambda root: _edit_source(
                _harness_source_path(root),
                _b003_missing_neighbor_harness_source(_read_text(_harness_source_path(root))),
            ),
            run_minecraft=True,
            expect_neighbor_update=True,
        ),
        ControlSpec(
            "B003",
            "2",
            "complete",
            "PASS",
            "2",
            source_edit=lambda root: _edit_source(_target_source_path(root), _b001_b003_positive_source(vanilla_identifier=False)),
            run_minecraft=True,
            expect_neighbor_update=True,
        ),
    )


def _validate_control(
    *,
    spec: ControlSpec,
    target_root: Path,
    harness_root: Path,
    evidence_root: Path,
    gradle_exe: Path,
    gradle_user_home: Path,
    timeout_seconds: int,
    repo_root: Path,
) -> CaseResult:
    source_path = _target_source_path(target_root)
    before_text = _read_text(source_path)
    before_hash = _sha256_text(before_text)
    before_identity = compute_fixture_identity(target_root)

    if spec.source_edit is not None:
        spec.source_edit(target_root)
    if spec.harness_edit is not None:
        spec.harness_edit(harness_root)

    after_text = _read_text(source_path)
    after_hash = _sha256_text(after_text)
    after_identity = compute_fixture_identity(target_root)
    source_diff = "\n".join(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile=f"before/{spec.task}-{spec.control}/ExampleMod.java",
            tofile=f"after/{spec.task}-{spec.control}/ExampleMod.java",
            lineterm="",
        )
    )
    source_changed = before_hash != after_hash

    build_result = _run_gradle_build(
        gradle_exe=gradle_exe,
        project_root=target_root,
        gradle_user_home=gradle_user_home,
        timeout_seconds=timeout_seconds,
        label=f"{spec.task}-{spec.control}-target",
    )
    build_status = "BLOCKED" if build_result.timed_out else ("PASS" if build_result.exit_code == 0 else "FAIL")
    target_jar = None
    target_jar_sha256 = None
    artifact_status = "BLOCKED"
    if build_status == "PASS":
        try:
            target_jar = _build_target_jar(target_root)
            runner = MinecraftTestRunner(project_root=target_root)
            spec_for_validation = MinecraftTestSpec(
                target_jar=Path("build/libs/pd-agent-l11-fixture.jar"),
                target_mod_id=DEFAULT_TARGET_MOD_ID,
                minecraft_version=DEFAULT_MINECRAFT_VERSION,
                loader_version=DEFAULT_LOADER_VERSION,
                test_id=DEFAULT_TEST_ID_B001_B002 if spec.task in {"B001", "B002"} else DEFAULT_TEST_ID_B003,
                timeout_seconds=30,
                expect_neighbor_update=spec.expect_neighbor_update,
            )
            target_metadata = runner.validate_target(spec_for_validation, java_version=DEFAULT_JAVA_VERSION)
            artifact_status = "PASS"
            target_jar_sha256 = target_metadata.sha256
        except Exception:
            artifact_status = "FAIL"
    else:
        artifact_status = "BLOCKED" if build_status == "BLOCKED" else "FAIL"

    minecraft_status = "N/A"
    neighbor_status = "N/A"
    harness_result: dict[str, Any] | None = None
    harness_build_stdout_tail = None
    harness_build_stderr_tail = None
    harness_run_stdout_tail = None
    harness_run_stderr_tail = None
    if spec.run_minecraft and build_status == "PASS" and artifact_status == "PASS":
        harness_build = _run_gradle_build(
            gradle_exe=gradle_exe,
            project_root=harness_root,
            gradle_user_home=gradle_user_home,
            timeout_seconds=timeout_seconds,
            label=f"{spec.task}-{spec.control}-harness",
        )
        harness_build_status = "BLOCKED" if harness_build.timed_out else ("PASS" if harness_build.exit_code == 0 else "FAIL")
        harness_build_stdout_tail = base._tail(harness_build.stdout)
        harness_build_stderr_tail = base._tail(harness_build.stderr)
        if harness_build_status == "PASS":
            runner = MinecraftTestRunner(
                project_root=target_root,
                harness_root=harness_root,
                evidence_root=evidence_root / "minecraft",
            )
            target_jar_path = _build_target_jar(target_root)
            spec_for_run = MinecraftTestSpec(
                target_jar=Path("build/libs/pd-agent-l11-fixture.jar"),
                target_mod_id=DEFAULT_TARGET_MOD_ID,
                minecraft_version=DEFAULT_MINECRAFT_VERSION,
                loader_version=DEFAULT_LOADER_VERSION,
                test_id=DEFAULT_TEST_ID_B001_B002 if spec.task in {"B001", "B002"} else DEFAULT_TEST_ID_B003,
                timeout_seconds=120,
                expect_neighbor_update=spec.expect_neighbor_update,
            )
            runtime_result = runner.run(
                spec_for_run,
                run_id=f"{spec.task}-{spec.control}",
                java_version=DEFAULT_JAVA_VERSION,
                expected_sha256=_jar_sha256(target_jar_path),
            )
            minecraft_status = runtime_result.status.value
            harness_run_stdout_tail = _read_tail(
                runtime_result.process_evidence.stdout_log if runtime_result.process_evidence else None
            )
            harness_run_stderr_tail = _read_tail(
                runtime_result.process_evidence.stderr_log if runtime_result.process_evidence else None
            )
            harness_result = _parse_harness_result(runtime_result.evidence_paths.harness_result_json)
            neighbor_value = None if harness_result is None else harness_result.get("neighbor_update_triggered")
            if neighbor_value is True:
                neighbor_status = "true"
            elif neighbor_value is False:
                neighbor_status = "false"
            else:
                neighbor_status = "N/A"
        else:
            minecraft_status = harness_build_status
            neighbor_status = "N/A"

    actual_acceptance = _evaluate_acceptance(
        spec=spec,
        build_status=build_status,
        artifact_status=artifact_status,
        minecraft_status=minecraft_status,
        neighbor_status=neighbor_status,
        source_text=after_text,
        source_changed=source_changed,
        harness_result=harness_result,
    )

    control_result = _control_result(spec.expected, actual_acceptance)
    if build_status == "BLOCKED" or artifact_status == "BLOCKED" or minecraft_status == "BLOCKED":
        control_result = "BLOCKED"
    if build_status == "FAIL" and control_result == "PASS":
        control_result = "BLOCKED"

    case_dir = evidence_root
    case_dir.mkdir(parents=True, exist_ok=True)
    _write_text(case_dir / "source-before.txt", before_text)
    _write_text(case_dir / "source-after.txt", after_text)
    _write_text(case_dir / "source-diff.txt", source_diff)
    _write_text(case_dir / "fixture-identity-before.txt", before_identity)
    _write_text(case_dir / "fixture-identity-after.txt", after_identity)
    _json_write(
        case_dir / "case-summary.json",
        {
            "task": spec.task,
            "task_version": spec.task_version,
            "control": spec.control,
            "expected": spec.expected,
            "actual_acceptance": actual_acceptance,
            "control_result": control_result,
            "build": build_status,
            "artifact": artifact_status,
            "minecraft": minecraft_status,
            "neighbor": neighbor_status,
            "fixture_path": str(_fixture_source(spec.task, spec.fixture_version)),
            "fixture_identity_before": before_identity,
            "fixture_identity_after": after_identity,
            "source_before_hash": before_hash,
            "source_after_hash": after_hash,
            "source_changed": source_changed,
            "target_jar": str(target_jar) if target_jar else None,
            "target_jar_sha256": target_jar_sha256,
            "harness_result": harness_result,
            "build_stdout_tail": base._tail(build_result.stdout),
            "build_stderr_tail": base._tail(build_result.stderr),
            "harness_build_stdout_tail": harness_build_stdout_tail,
            "harness_build_stderr_tail": harness_build_stderr_tail,
            "harness_run_stdout_tail": harness_run_stdout_tail,
            "harness_run_stderr_tail": harness_run_stderr_tail,
        },
    )

    return CaseResult(
        task=spec.task,
        task_version=spec.task_version,
        control=spec.control,
        expected=spec.expected,
        actual_acceptance=actual_acceptance,
        control_result=control_result,
        build=build_status,
        artifact=artifact_status,
        minecraft=minecraft_status,
        neighbor=neighbor_status,
        fixture_path=str(_fixture_source(spec.task, spec.fixture_version)),
        fixture_identity_before=before_identity,
        fixture_identity_after=after_identity,
        source_before_hash=before_hash,
        source_after_hash=after_hash,
        source_diff=source_diff,
        target_jar=str(target_jar) if target_jar else None,
        target_jar_sha256=target_jar_sha256,
        harness_result=harness_result,
        build_stdout_tail=base._tail(build_result.stdout),
        build_stderr_tail=base._tail(build_result.stderr),
        harness_build_stdout_tail=harness_build_stdout_tail,
        harness_build_stderr_tail=harness_build_stderr_tail,
        harness_run_stdout_tail=harness_run_stdout_tail,
        harness_run_stderr_tail=harness_run_stderr_tail,
        evidence_root=str(case_dir),
    )


def _evaluate_acceptance(
    *,
    spec: ControlSpec,
    build_status: str,
    artifact_status: str,
    minecraft_status: str,
    neighbor_status: str,
    source_text: str,
    source_changed: bool,
    harness_result: dict[str, Any] | None,
) -> str:
    if build_status != "PASS" or artifact_status != "PASS":
        return "BLOCKED" if "BLOCKED" in {build_status, artifact_status} else "FAIL"

    if spec.task == "B002":
        required = (
            "Identifier.ofVanilla(\"diamond_block\")",
            "probeIdentifier()",
        )
        forbidden = ("Identifier.of(\"minecraft\", \"diamond_block\")",)
        if source_changed and all(item in source_text for item in required) and not any(item in source_text for item in forbidden):
            return "PASS"
        return "FAIL"

    if minecraft_status not in {"PASS", "FAIL"}:
        return "BLOCKED"

    if harness_result is None:
        return "BLOCKED"

    if spec.task == "B001":
        required = (
            "Registries.BLOCK.get(",
            "Identifier.of(\"minecraft\", \"diamond_block\")",
            "Block.NOTIFY_ALL",
        )
        if source_changed and all(item in source_text for item in required) and harness_result.get("functional_test_result") == "PASS":
            return "PASS"
        return "FAIL"

    if spec.task == "B003":
        required = (
            "Registries.BLOCK.get(",
            "Identifier.of(\"minecraft\", \"diamond_block\")",
            "Block.NOTIFY_ALL",
        )
        if (
            source_changed
            and all(item in source_text for item in required)
            and harness_result.get("functional_test_result") == "PASS"
            and harness_result.get("target_loaded") is True
            and harness_result.get("target_origin_resolved") is True
            and harness_result.get("target_sha_match") is True
            and harness_result.get("server_started") is True
            and harness_result.get("shutdown_requested") is True
            and harness_result.get("neighbor_update_triggered") is True
        ):
            return "PASS"
        return "FAIL"

    return "FAIL"


def _control_result(expected: str, actual: str) -> str:
    if actual == "BLOCKED":
        return "BLOCKED"
    if actual == expected:
        return "PASS"
    return "FAIL"


def _build_summary(repo_root: Path, validation_root: Path) -> ValidationSummary:
    return ValidationSummary(
        started_at=datetime.now(timezone.utc),
        repo_root=repo_root,
        validation_root=validation_root,
    )


def _write_summary(summary: ValidationSummary) -> None:
    summary.finished_at = datetime.now(timezone.utc)
    _json_write(summary.validation_root / "final-summary.json", summary.to_dict())
    _write_text(summary.validation_root / "final-summary.md", summary.table() + "\n")


def _precheck(summary: ValidationSummary, *, repo_root: Path) -> None:
    branch = _repo_git("branch", "--show-current")
    status = _repo_git("status", "--short", "--branch")
    head = _repo_git("rev-parse", "HEAD")
    origin = _repo_git("rev-parse", "origin/main")
    if branch.exit_code != 0 or head.exit_code != 0 or origin.exit_code != 0 or status.exit_code != 0:
        raise RuntimeError("git precheck failed")
    if branch.stdout.strip() != "main":
        raise RuntimeError(f"branch no es main: {branch.stdout.strip()}")
    if head.stdout.strip() != origin.stdout.strip():
        raise RuntimeError("HEAD != origin/main")
    if _git_status_dirty(status.stdout):
        raise RuntimeError(f"working tree dirty: {status.stdout.strip()}")
    summary.branch = branch.stdout.strip()
    summary.head = head.stdout.strip()
    summary.origin_main = origin.stdout.strip()
    summary.git_status_before = status.stdout.strip()


def _postcheck(summary: ValidationSummary) -> None:
    status = _repo_git("status", "--short", "--branch")
    if status.exit_code != 0:
        raise RuntimeError("git status final failed")
    if _git_status_dirty(status.stdout):
        raise RuntimeError(f"working tree dirty after validator: {status.stdout.strip()}")
    summary.git_status_after = status.stdout.strip()


def _cleanup_case_root(case_root: Path) -> None:
    if case_root.exists():
        shutil.rmtree(case_root, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    repo_root = args.repo_root.resolve()
    validation_root = args.validation_root.resolve()
    validation_root.mkdir(parents=True, exist_ok=True)
    (validation_root / "evidence").mkdir(parents=True, exist_ok=True)
    (validation_root / "cases").mkdir(parents=True, exist_ok=True)

    summary = _build_summary(repo_root, validation_root)
    summary.notes.append(f"python_exe: {args.python_exe}")
    summary.notes.append(f"gradle_exe: {args.gradle_exe}")
    summary.notes.append("run_v0_4.py = NOT_READY")

    try:
        _precheck(summary, repo_root=repo_root)
        if not args.python_exe.exists():
            raise RuntimeError(f"python exe no existe: {args.python_exe}")
        if not args.gradle_exe.exists():
            raise RuntimeError(f"gradle exe no existe: {args.gradle_exe}")

        _assert_fixture_identity_matches_manifest("B001", "1")
        _assert_fixture_identity_matches_manifest("B002", "2")
        _assert_fixture_identity_matches_manifest("B003", "2")

        controls = _control_specs()
        for spec in controls:
            target_root, harness_root, evidence_root = _prepare_case_workspace(validation_root, spec.task, spec.fixture_version)
            try:
                case = _validate_control(
                    spec=spec,
                    target_root=target_root,
                    harness_root=harness_root,
                    evidence_root=evidence_root,
                    gradle_exe=args.gradle_exe,
                    gradle_user_home=args.gradle_user_home,
                    timeout_seconds=args.timeout_seconds,
                    repo_root=repo_root,
                )
            except Exception as exc:
                case = CaseResult(
                    task=spec.task,
                    task_version=spec.task_version,
                    control=spec.control,
                    expected=spec.expected,
                    actual_acceptance="BLOCKED",
                    control_result="BLOCKED",
                    build="BLOCKED",
                    artifact="BLOCKED",
                    minecraft="BLOCKED" if spec.run_minecraft else "N/A",
                    neighbor="N/A",
                    fixture_path=str(_fixture_source(spec.task, spec.fixture_version)),
                    evidence_root=str(evidence_root),
                    error=f"{type(exc).__name__}: {exc}",
                )
                _json_write(evidence_root / "case-error.json", {"error": case.error, "task": spec.task, "control": spec.control})
                summary.cases.append(case)
                summary.error = case.error
                break

            summary.cases.append(case)
            if case.control_result == "BLOCKED":
                summary.error = case.error or "blocked"
                break

        _postcheck(summary)
        _write_summary(summary)
    except Exception as exc:
        summary.error = f"{type(exc).__name__}: {exc}"
        summary.notes.append(summary.error)
        _write_summary(summary)
        print("DATASET_FREEZE_BLOCKED")
        print(f"CASE=internal-error")
        print(f"TYPE=ERROR")
        print("EXPECTED=READY")
        print("ACTUAL=BLOCKED")
        print(f"EVIDENCE={validation_root}")
        return 1
    finally:
        if not args.keep_working_copy:
            for spec in _control_specs():
                _cleanup_case_root(validation_root / "cases" / f"{spec.task}-v{spec.fixture_version}")

    print(summary.table())
    print()
    if summary.ready:
        print("DATASET_FREEZE_READY")
        return 0

    blocked_case = next((case for case in summary.cases if case.control_result != "PASS"), None)
    print("DATASET_FREEZE_BLOCKED")
    if blocked_case is not None:
        print(f"CASE={blocked_case.task}-v{blocked_case.task_version}-{blocked_case.control}")
        print(f"TYPE={blocked_case.control}")
        print(f"EXPECTED={blocked_case.expected}")
        print(f"ACTUAL={blocked_case.actual_acceptance}")
        print(f"EVIDENCE={blocked_case.evidence_root}")
    else:
        print("CASE=unknown")
        print("TYPE=unknown")
        print("EXPECTED=unknown")
        print("ACTUAL=unknown")
        print(f"EVIDENCE={validation_root}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
