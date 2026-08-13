from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from pd_agent.core import ExecutionLimits, ToolCall, ToolResultStatus
from pd_agent.reporting import RunStorage
from pd_agent.tools import (
    ToolExecutionContext,
    ToolExecutor,
    create_filesystem_tools,
)


def _make_executor(root: Path, *, limits: ExecutionLimits | None = None):
    storage = RunStorage(root / "runs")
    run_id = "run-l3"
    executor = ToolExecutor(
        event_sink=storage.event_writer(run_id),
        tools=create_filesystem_tools(),
    )
    context = ToolExecutionContext(
        project_root=root,
        limits=limits or ExecutionLimits(),
        run_id=run_id,
    )
    return executor, context, storage, run_id


def _prepare_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "src").mkdir()
    (root / "src" / "alpha.txt").write_text("alpha line\nneedle here\n", encoding="utf-8")
    (root / "docs" / "readme.md").write_text("docs text\n", encoding="utf-8")
    (root / "existing.txt").write_text("old content", encoding="utf-8")
    (root / "empty.txt").write_text("", encoding="utf-8")
    (root / ".git").mkdir()
    (root / "gradlew").write_text("wrapper", encoding="utf-8")
    return root


def test_valid_read_write_create_search_delete_and_events(tmp_path: Path) -> None:
    root = _prepare_project(tmp_path)
    executor, context, storage, run_id = _make_executor(root)

    read_result = executor.execute(
        ToolCall(call_id="1", tool_name="read_file", arguments={"path": "existing.txt"}),
        context,
    )
    write_result = executor.execute(
        ToolCall(
            call_id="2",
            tool_name="write_file",
            arguments={"path": "existing.txt", "content": "new content"},
        ),
        context,
    )
    create_result = executor.execute(
        ToolCall(
            call_id="3",
            tool_name="create_file",
            arguments={"path": "created.txt", "content": "hello"},
        ),
        context,
    )
    search_result = executor.execute(
        ToolCall(
            call_id="4",
            tool_name="search_text",
            arguments={"query": "needle", "paths": ["src"]},
        ),
        context,
    )
    delete_result = executor.execute(
        ToolCall(call_id="5", tool_name="delete_file", arguments={"path": "empty.txt"}),
        context,
    )

    assert read_result.status == ToolResultStatus.SUCCESS
    assert read_result.output["content"] == "old content"
    assert write_result.status == ToolResultStatus.SUCCESS
    assert write_result.output["changed"] is True
    assert create_result.status == ToolResultStatus.SUCCESS
    assert (root / "created.txt").read_text(encoding="utf-8") == "hello"
    assert search_result.status == ToolResultStatus.SUCCESS
    assert search_result.output["matches"]
    assert delete_result.status == ToolResultStatus.SUCCESS
    assert not (root / "empty.txt").exists()
    tools = {tool.name: tool for tool in create_filesystem_tools()}
    assert "existing" in tools["write_file"].description.lower()
    assert "does not already exist" in tools["create_file"].description.lower()

    events = [
        json.loads(line)
        for line in storage.paths_for(run_id).events_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event_type"] for event in events].count("TOOL_REQUESTED") >= 5
    assert "TOOL_EXECUTED" in [event["event_type"] for event in events]
    assert "FILE_CHANGED" in [event["event_type"] for event in events]


def test_relative_escape_absolute_escape_and_git_protection(tmp_path: Path) -> None:
    root = _prepare_project(tmp_path)
    executor, context, storage, run_id = _make_executor(root)

    parent_escape = executor.execute(
        ToolCall(call_id="6", tool_name="read_file", arguments={"path": "../outside.txt"}),
        context,
    )
    absolute_escape = executor.execute(
        ToolCall(
            call_id="7",
            tool_name="read_file",
            arguments={"path": str(tmp_path / "outside.txt")},
        ),
        context,
    )
    git_protected = executor.execute(
        ToolCall(call_id="8", tool_name="delete_file", arguments={"path": ".git/config"}),
        context,
    )
    root_delete = executor.execute(
        ToolCall(call_id="9", tool_name="delete_file", arguments={"path": "."}),
        context,
    )

    assert parent_escape.status == ToolResultStatus.REJECTED
    assert absolute_escape.status == ToolResultStatus.REJECTED
    assert git_protected.status == ToolResultStatus.REJECTED
    assert root_delete.status == ToolResultStatus.REJECTED

    events = [
        json.loads(line)
        for line in storage.paths_for(run_id).events_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    event_types = [event["event_type"] for event in events]
    assert event_types.count("TOOL_REJECTED") >= 4
    assert "FILE_CHANGED" not in event_types[-2:]


def test_invalid_input_unknown_tool_and_noop_write_rejections(tmp_path: Path) -> None:
    root = _prepare_project(tmp_path)
    executor, context, storage, run_id = _make_executor(root)

    invalid_input = executor.execute(
        ToolCall(call_id="10", tool_name="read_file", arguments={"path": 123}),
        context,
    )
    unknown_tool = executor.execute(
        ToolCall(call_id="11", tool_name="no_such_tool", arguments={}),
        context,
    )
    create_exists = executor.execute(
        ToolCall(
            call_id="12",
            tool_name="create_file",
            arguments={"path": "existing.txt", "content": "x"},
        ),
        context,
    )
    write_missing = executor.execute(
        ToolCall(
            call_id="13",
            tool_name="write_file",
            arguments={"path": "missing.txt", "content": "x"},
        ),
        context,
    )

    assert invalid_input.status == ToolResultStatus.REJECTED
    assert unknown_tool.status == ToolResultStatus.REJECTED
    assert create_exists.status == ToolResultStatus.REJECTED
    assert write_missing.status == ToolResultStatus.REJECTED
    assert create_exists.metadata["recoverable"] is True
    assert create_exists.metadata["rejection_code"] == "file_exists"
    assert write_missing.metadata["recoverable"] is False
    assert "rejection_code" not in write_missing.metadata

    event_types = [
        json.loads(line)["event_type"]
        for line in storage.paths_for(run_id).events_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert "TOOL_REJECTED" in event_types


def test_file_exists_rejection_is_structured_and_emits_metadata(tmp_path: Path) -> None:
    root = _prepare_project(tmp_path)
    executor, context, storage, run_id = _make_executor(root)

    result = executor.execute(
        ToolCall(
            call_id="20",
            tool_name="create_file",
            arguments={"path": "existing.txt", "content": "replacement"},
        ),
        context,
    )

    assert result.status == ToolResultStatus.REJECTED
    assert result.metadata["recoverable"] is True
    assert result.metadata["rejection_code"] == "file_exists"
    assert "write_file" in (result.error or "")
    assert (root / "existing.txt").read_text(encoding="utf-8") == "old content"

    event = json.loads(
        storage.paths_for(run_id).events_jsonl.read_text(encoding="utf-8").splitlines()[-1]
    )
    assert event["event_type"] == "TOOL_REJECTED"
    assert event["payload"]["rejection_code"] == "file_exists"
    assert event["payload"]["recoverable"] is True


def test_internal_exception_becomes_error(tmp_path: Path) -> None:
    root = _prepare_project(tmp_path)
    executor, context, _storage, _run_id = _make_executor(root)
    tool = executor.get_tool("read_file")

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    tool.execute = boom  # type: ignore[assignment]

    result = executor.execute(
        ToolCall(call_id="14", tool_name="read_file", arguments={"path": "existing.txt"}),
        context,
    )

    assert result.status == ToolResultStatus.ERROR
    assert "boom" in (result.error or "")


def test_file_changed_only_on_real_change_and_unicode_paths(tmp_path: Path) -> None:
    root = _prepare_project(tmp_path)
    executor, context, storage, run_id = _make_executor(root)

    same = executor.execute(
        ToolCall(
            call_id="15",
            tool_name="write_file",
            arguments={"path": "existing.txt", "content": "old content"},
        ),
        context,
    )
    changed = executor.execute(
        ToolCall(
            call_id="16",
            tool_name="write_file",
            arguments={"path": "existing.txt", "content": "updated"},
        ),
        context,
    )
    unicode_dir = root / "unicodé"
    unicode_dir.mkdir()
    (unicode_dir / "archivo.txt").write_text("hola mundo", encoding="utf-8")
    unicode_create = executor.execute(
        ToolCall(
            call_id="17",
            tool_name="create_file",
            arguments={"path": "unicodé/nuevo.txt", "content": "sí"},
        ),
        context,
    )

    assert same.status == ToolResultStatus.SUCCESS
    assert same.output["changed"] is False
    assert changed.status == ToolResultStatus.SUCCESS
    assert changed.output["changed"] is True
    assert unicode_create.status == ToolResultStatus.SUCCESS
    assert (unicode_dir / "nuevo.txt").read_text(encoding="utf-8") == "sí"

    event_types = [
        json.loads(line)["event_type"]
        for line in storage.paths_for(run_id).events_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert event_types.count("FILE_CHANGED") >= 2


def test_output_truncation_is_explicit(tmp_path: Path) -> None:
    root = _prepare_project(tmp_path)
    big_text = "x" * 10_000
    (root / "big.txt").write_text(big_text, encoding="utf-8")
    executor, context, _storage, _run_id = _make_executor(
        root, limits=ExecutionLimits(max_tool_output_bytes=64)
    )

    result = executor.execute(
        ToolCall(call_id="18", tool_name="read_file", arguments={"path": "big.txt"}),
        context,
    )

    assert result.status == ToolResultStatus.SUCCESS
    assert result.output["truncated"] is True
    assert result.metadata["truncated"] is True
    assert len(result.output["content"].encode("utf-8")) <= 64


def test_symlink_escape_rejected_when_supported(tmp_path: Path) -> None:
    root = _prepare_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    link = root / "linked-secret.txt"

    if not hasattr(os, "symlink"):
        pytest.skip("symlinks not supported")
    try:
        link.symlink_to(outside_file)
    except (OSError, NotImplementedError, AttributeError):
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            pytest.skip("symlink or junction creation unavailable in this environment")

    executor, context, _storage, _run_id = _make_executor(root)
    result = executor.execute(
        ToolCall(call_id="19", tool_name="read_file", arguments={"path": "linked-secret.txt"}),
        context,
    )

    assert result.status == ToolResultStatus.REJECTED
