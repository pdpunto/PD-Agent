from __future__ import annotations

from pathlib import Path

from pd_agent.core import ExecutionLimits, ToolCall, ToolResultStatus
from pd_agent.tools import ToolExecutionContext, ToolExecutor, create_filesystem_tools


def test_list_directory_missing_path_is_observation_not_terminal_rejection(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    executor = ToolExecutor(tools=create_filesystem_tools())
    context = ToolExecutionContext(
        project_root=root,
        limits=ExecutionLimits(),
        run_id="f9-missing-directory",
    )

    result = executor.execute(
        ToolCall(
            call_id="1",
            tool_name="list_directory",
            arguments={"path": "src/main/resources/assets"},
        ),
        context,
    )

    assert result.status == ToolResultStatus.SUCCESS
    assert result.output["exists"] is False
    assert result.output["entries"] == []
    assert result.output["entry_count"] == 0
    assert result.metadata["exists"] is False
    assert not (root / "src/main/resources/assets").exists()
