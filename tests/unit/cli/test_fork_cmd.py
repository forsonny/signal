"""Tests for signal fork CLI command."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from typer.testing import CliRunner

from signalagent.cli.app import app
from signalagent.worktrees.models import ForkResult


runner = CliRunner()


def _make_result(
    index: int = 0,
    task: str = "test task",
    success: bool = True,
    worktree_id: str | None = "wt_abc12345",
    error: str | None = None,
) -> ForkResult:
    return ForkResult(
        branch_index=index,
        task_description=task,
        response="Done." if success else "",
        worktree_id=worktree_id,
        changed_files=["src/main.py"] if worktree_id else [],
        success=success,
        error=error,
    )


class TestForkCommand:
    @patch("signalagent.core.config.find_instance", return_value=Path("/fake/instance"))
    @patch("signalagent.cli.fork_cmd._async_fork", new_callable=AsyncMock)
    def test_basic_fork(self, mock_fork: AsyncMock, mock_find: MagicMock) -> None:
        mock_fork.return_value = [
            _make_result(index=0, task="approach A", worktree_id="wt_aaa11111"),
            _make_result(index=1, task="approach B", worktree_id="wt_bbb22222"),
        ]
        result = runner.invoke(app, ["fork", "approach A", "approach B"])
        assert result.exit_code == 0
        assert "Fork complete: 2 branches" in result.output
        assert "wt_aaa11111" in result.output
        assert "wt_bbb22222" in result.output
        assert "signal worktree merge" in result.output

    @patch("signalagent.core.config.find_instance", return_value=Path("/fake/instance"))
    @patch("signalagent.cli.fork_cmd._async_fork", new_callable=AsyncMock)
    def test_all_failed_exit_code_1(self, mock_fork: AsyncMock, mock_find: MagicMock) -> None:
        mock_fork.return_value = [
            _make_result(index=0, success=False, error="timeout", worktree_id=None),
            _make_result(index=1, success=False, error="timeout", worktree_id=None),
        ]
        result = runner.invoke(app, ["fork", "task A", "task B"])
        assert result.exit_code == 1

    @patch("signalagent.core.config.find_instance", return_value=Path("/fake/instance"))
    @patch("signalagent.cli.fork_cmd._async_fork", new_callable=AsyncMock)
    def test_partial_success_exit_code_0(self, mock_fork: AsyncMock, mock_find: MagicMock) -> None:
        mock_fork.return_value = [
            _make_result(index=0, success=True),
            _make_result(index=1, success=False, error="timeout", worktree_id=None),
        ]
        result = runner.invoke(app, ["fork", "task A", "task B"])
        assert result.exit_code == 0

    def test_less_than_two_tasks_rejected(self) -> None:
        result = runner.invoke(app, ["fork", "only one task"])
        assert result.exit_code == 1
        assert "at least 2" in result.output.lower() or "At least 2" in result.output

    @patch("signalagent.core.config.find_instance", return_value=Path("/fake/instance"))
    @patch("signalagent.cli.fork_cmd._async_fork", new_callable=AsyncMock)
    def test_no_worktree_branch(self, mock_fork: AsyncMock, mock_find: MagicMock) -> None:
        mock_fork.return_value = [
            _make_result(index=0, worktree_id=None),
            _make_result(index=1, worktree_id="wt_abc12345"),
        ]
        result = runner.invoke(app, ["fork", "analyze", "fix"])
        assert result.exit_code == 0
        assert "wt_abc12345" in result.output
