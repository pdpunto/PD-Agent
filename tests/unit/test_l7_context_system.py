from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pd_agent import ContextBundle, ContextItem, ContextManager, ContextRequest, ExternalContextSource, ProjectContextSource, RunContextSource
from pd_agent.core import ArtifactResult, BuildResult, ExecutionLimits, RunState, RunStatus
from pd_agent.reporting import Redactor
from tests.fixtures.fabric_projects import make_dirty_git_project


def _build_result(started_at: datetime, *, stdout: str = "", stderr: str = "", exit_code: int = 0) -> BuildResult:
    return BuildResult(
        attempt=1,
        command_display="gradlew build",
        cwd=Path("C:/dev/project"),
        started_at=started_at,
        duration_seconds=2.5,
        exit_code=exit_code,
        stdout_log=stdout,
        stderr_log=stderr,
    )


def _context_manager(*, redactor: Redactor | None = None, max_context_bytes: int = 4096) -> ContextManager:
    return ContextManager(redactor=redactor, max_context_bytes=max_context_bytes)


def test_combination_order_is_stable(tmp_path: Path) -> None:
    root = make_dirty_git_project(tmp_path / "proj")
    snapshot = __import__("pd_agent.project", fromlist=["ProjectInspector"]).ProjectInspector().inspect(root)
    started_at = datetime.now(timezone.utc)
    run_state = RunState(
        project_root=root,
        task="task",
        state=RunStatus.BUILDING,
        current_plan="plan",
        build_attempt_count=1,
        build_results=(
            _build_result(started_at, stdout="hello", stderr="warn"),
        ),
    )

    manager = _context_manager(max_context_bytes=16_384)
    bundle_a = manager.build_context(project_snapshot=snapshot, run_state=run_state, external_context=("extra",))
    bundle_b = manager.build_context(project_snapshot=snapshot, run_state=run_state, external_context=("extra",))

    assert bundle_a.to_dict() == bundle_b.to_dict()
    assert [item.priority for item in bundle_a.items] == sorted(item.priority for item in bundle_a.items)
    assert bundle_a.to_messages()[0].role == "system"
    assert bundle_a.to_messages()[0].metadata["context_truncated"] is False


def test_empty_context_is_valid() -> None:
    bundle = _context_manager().build_context()

    assert bundle.items == ()
    assert bundle.to_messages() == ()
    assert bundle.truncated is False
    assert bundle.omitted_count == 0


def test_external_context_is_included_explicitly() -> None:
    manager = _context_manager()
    bundle = manager.build_context(
        external_context=(
            "doc fragment",
            ContextItem.from_text(source="external", priority=90, label="manual", content="notes"),
        )
    )

    assert any(item.label == "manual" for item in bundle.items)
    assert any(item.source == "external" for item in bundle.items)
    assert "doc fragment" in bundle.to_text()


def test_priority_retains_critical_items_before_huge_external(tmp_path: Path) -> None:
    root = make_dirty_git_project(tmp_path / "priority")
    snapshot = __import__("pd_agent.project", fromlist=["ProjectInspector"]).ProjectInspector().inspect(root)
    run_state = RunState(
        project_root=root,
        task="t",
        state=RunStatus.EDITING,
        build_attempt_count=1,
        build_results=(
            _build_result(
                datetime.now(timezone.utc),
                stdout="line-" * 500,
                stderr="boom" * 500,
            ),
        ),
    )
    huge_external = "EXTERNAL-" + ("z" * 20000)

    bundle = _context_manager(max_context_bytes=8000).build_context(
        project_snapshot=snapshot,
        run_state=run_state,
        external_context=(huge_external,),
    )

    labels = [item.label for item in bundle.items]
    assert "project-overview" in labels
    assert "run-state" in labels
    assert "build-results" in labels
    assert "external-1" not in labels
    assert bundle.truncated is True
    assert bundle.omitted_count >= 1
    assert len(bundle.to_text().encode("utf-8")) <= 8000


def test_build_logs_are_bounded_and_recent(tmp_path: Path) -> None:
    root = make_dirty_git_project(tmp_path / "logs")
    snapshot = __import__("pd_agent.project", fromlist=["ProjectInspector"]).ProjectInspector().inspect(root)
    started_at = datetime.now(timezone.utc)
    stdout = "\n".join(f"stdout-{index}" for index in range(200))
    stderr = "\n".join(f"stderr-{index}" for index in range(200))
    run_state = RunState(
        project_root=root,
        task="build",
        state=RunStatus.BUILDING,
        build_results=(
            _build_result(started_at, stdout=stdout, stderr=stderr),
        ),
    )

    manager = ContextManager(
        sources=(
            ("project", ProjectContextSource()),
            ("run", RunContextSource(log_tail_bytes=120)),
            ("external", ExternalContextSource()),
        ),
        max_context_bytes=12_000,
    )
    bundle = manager.build_context(
        project_snapshot=snapshot,
        run_state=run_state,
    )

    text = bundle.to_text()
    assert "latest-build-log" in text
    assert "stdout-199" in text
    assert "stderr-199" in text
    assert "stdout-0" not in text
    assert "stderr-0" not in text


def test_secret_is_redacted_from_output(tmp_path: Path) -> None:
    secret = "super-secret-token"
    root = make_dirty_git_project(tmp_path / "secret")
    snapshot = __import__("pd_agent.project", fromlist=["ProjectInspector"]).ProjectInspector().inspect(root)
    run_state = RunState(
        project_root=root,
        task=f"task uses {secret}",
        current_plan=f"plan {secret}",
        build_results=(
            _build_result(datetime.now(timezone.utc), stdout=f"stdout {secret}", stderr=f"stderr {secret}"),
        ),
        artifact_result=ArtifactResult(
            path=root / "build" / "libs" / "example.jar",
            size=123,
            timestamp=datetime.now(timezone.utc),
            classification="VALID",
            metadata={"note": secret},
        ),
    )

    bundle = _context_manager(redactor=Redactor((secret,)), max_context_bytes=16_384).build_context(
        project_snapshot=snapshot,
        run_state=run_state,
        external_context=(f"external {secret}",),
    )

    text = bundle.to_text()
    assert secret not in text
    assert "[REDACTED]" in text


def test_project_and_run_summaries_present(tmp_path: Path) -> None:
    root = make_dirty_git_project(tmp_path / "summary")
    snapshot = __import__("pd_agent.project", fromlist=["ProjectInspector"]).ProjectInspector().inspect(root)
    run_state = RunState(
        project_root=root,
        task="build",
        current_plan="inspect, build",
        changed_files=("README.md",),
        build_results=(
            _build_result(datetime.now(timezone.utc), stdout="ok", stderr=""),
        ),
        artifact_result=ArtifactResult(
            path=root / "build" / "libs" / "mod.jar",
            size=10,
            timestamp=datetime.now(timezone.utc),
            classification="VALID",
            metadata={"mod_id": "example"},
        ),
    )

    bundle = _context_manager(max_context_bytes=16_384).build_context(
        project_snapshot=snapshot,
        run_state=run_state,
    )

    labels = [item.label for item in bundle.items]
    assert "project-overview" in labels
    assert "project-structure" in labels
    assert "run-state" in labels
    assert "build-results" in labels
    assert "latest-build-log" in labels
    assert "artifact-result" in labels


def test_run_summary_exposes_budget_and_phase(tmp_path: Path) -> None:
    root = make_dirty_git_project(tmp_path / "budget")
    snapshot = __import__("pd_agent.project", fromlist=["ProjectInspector"]).ProjectInspector().inspect(root)
    run_state = RunState(
        project_root=root,
        task="build",
        state=RunStatus.PLANNING,
        current_plan="inspect, act",
        changed_files=("src/Main.java",),
        tool_call_count=2,
        agent_step_count=3,
        build_attempt_count=1,
        last_error="none",
    )
    limits = ExecutionLimits(max_agent_steps=5, max_tool_calls=7, max_build_attempts=4)

    bundle = _context_manager(max_context_bytes=16_384).build_context(
        project_snapshot=snapshot,
        run_state=run_state,
        limits=limits,
    )

    text = bundle.to_text()
    assert "phase: PLANNING" in text
    assert "agent_steps_remaining: 2" in text
    assert "tool_calls_remaining: 5" in text
    assert "build_attempts_remaining: 3" in text
    assert "logical_provider_request_count" in text
    assert "consecutive_recoverable_rejections" in text


def test_utf8_truncation_is_explicit_and_valid(tmp_path: Path) -> None:
    root = make_dirty_git_project(tmp_path / "unicode")
    snapshot = __import__("pd_agent.project", fromlist=["ProjectInspector"]).ProjectInspector().inspect(root)
    run_state = RunState(
        project_root=root,
        task="task",
        build_results=(
            _build_result(
                datetime.now(timezone.utc),
                stdout="漢字" * 1000,
                stderr="éxito" * 1000,
            ),
        ),
    )

    bundle = _context_manager(max_context_bytes=2048).build_context(
        project_snapshot=snapshot,
        run_state=run_state,
        external_context=("日本語" * 2000,),
    )

    text = bundle.to_text()
    encoded = text.encode("utf-8")
    assert len(encoded) <= 2048
    assert "..." in text or bundle.truncated is True
    assert "\ufffd" not in text


def test_same_input_same_result(tmp_path: Path) -> None:
    root = make_dirty_git_project(tmp_path / "same")
    snapshot = __import__("pd_agent.project", fromlist=["ProjectInspector"]).ProjectInspector().inspect(root)
    run_state = RunState(
        project_root=root,
        task="task",
        build_results=(
            _build_result(datetime.now(timezone.utc), stdout="1", stderr="2"),
        ),
    )
    manager = _context_manager(max_context_bytes=4096)

    first = manager.build_context(project_snapshot=snapshot, run_state=run_state, external_context=("x",))
    second = manager.build_context(project_snapshot=snapshot, run_state=run_state, external_context=("x",))

    assert first.to_dict() == second.to_dict()


def test_no_openai_or_process_dependencies_in_context_package() -> None:
    import pd_agent.context as context_package

    source = inspect.getsource(context_package)
    lower = source.lower()

    assert "openai" not in lower
    assert "subprocess" not in lower
    assert "requests" not in lower
    assert "http" not in lower
    assert "vector" not in lower
    assert "embedding" not in lower
