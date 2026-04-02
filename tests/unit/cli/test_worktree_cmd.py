"""Tests for signal worktree CLI commands."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from signalagent.cli.app import app
from signalagent.worktrees.models import WorktreeRecord


runner = CliRunner()


def _make_record(
    id: str = "wt_abc12345",
    status: str = "pending",
    agent_name: str = "coder",
    worktree_path: Path = Path("/tmp/wt"),
) -> WorktreeRecord:
    return WorktreeRecord(
        id=id,
        worktree_path=worktree_path,
        workspace_root=Path("/project"),
        agent_name=agent_name,
        created=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
        status=status,
        is_git=True,
        branch_name=f"signal/worktree/{agent_name}_{id}",
    )


class TestWorktreeList:
    @patch("signalagent.cli.worktree_cmd._get_instance_dir")
    @patch("signalagent.worktrees.manifest.WorktreeManifest")
    @patch("signalagent.worktrees.manager.WorktreeManager")
    def test_shows_pending_worktrees(
        self, MockManager: MagicMock, MockManifest: MagicMock, mock_find: MagicMock, tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        manifest = MagicMock()
        manifest.list_pending.return_value = [
            _make_record(id="wt_001", agent_name="coder"),
            _make_record(id="wt_002", agent_name="reviewer"),
        ]
        MockManifest.return_value = manifest
        manager = MagicMock()
        manager.changed_files.return_value = ["file.py"]
        MockManager.return_value = manager

        result = runner.invoke(app, ["worktree", "list"])
        assert result.exit_code == 0
        assert "wt_001" in result.output
        assert "wt_002" in result.output
        assert "coder" in result.output

    @patch("signalagent.cli.worktree_cmd._get_instance_dir")
    @patch("signalagent.worktrees.manifest.WorktreeManifest")
    def test_shows_empty_message(
        self, MockManifest: MagicMock, mock_find: MagicMock, tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        manifest = MagicMock()
        manifest.list_pending.return_value = []
        MockManifest.return_value = manifest

        result = runner.invoke(app, ["worktree", "list"])
        assert result.exit_code == 0
        assert "no pending" in result.output.lower() or "No pending" in result.output


class TestWorktreeMerge:
    @patch("signalagent.cli.worktree_cmd._get_instance_dir")
    @patch("signalagent.worktrees.manifest.WorktreeManifest")
    @patch("signalagent.worktrees.manager.WorktreeManager")
    def test_merges_and_cleans(
        self,
        MockManager: MagicMock,
        MockManifest: MagicMock,
        mock_find: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        record = _make_record(worktree_path=tmp_path / "wt")
        manifest = MagicMock()
        manifest.get.return_value = record
        MockManifest.return_value = manifest
        manager = MagicMock()
        MockManager.return_value = manager

        result = runner.invoke(app, ["worktree", "merge", "wt_abc12345"])
        assert result.exit_code == 0
        manager.merge.assert_called_once()
        manager.cleanup.assert_called_once()
        manifest.append.assert_called_once()
        updated = manifest.append.call_args[0][0]
        assert updated.status == "merged"

    @patch("signalagent.cli.worktree_cmd._get_instance_dir")
    @patch("signalagent.worktrees.manifest.WorktreeManifest")
    def test_merge_unknown_id(
        self, MockManifest: MagicMock, mock_find: MagicMock, tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        manifest = MagicMock()
        manifest.get.return_value = None
        MockManifest.return_value = manifest

        result = runner.invoke(app, ["worktree", "merge", "wt_nonexistent"])
        assert result.exit_code == 1


class TestWorktreeDiscard:
    @patch("signalagent.cli.worktree_cmd._get_instance_dir")
    @patch("signalagent.worktrees.manifest.WorktreeManifest")
    @patch("signalagent.worktrees.manager.WorktreeManager")
    def test_discards_and_cleans(
        self,
        MockManager: MagicMock,
        MockManifest: MagicMock,
        mock_find: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_find.return_value = tmp_path
        record = _make_record(worktree_path=tmp_path / "wt")
        manifest = MagicMock()
        manifest.get.return_value = record
        MockManifest.return_value = manifest
        manager = MagicMock()
        MockManager.return_value = manager

        result = runner.invoke(app, ["worktree", "discard", "wt_abc12345"])
        assert result.exit_code == 0
        manager.merge.assert_not_called()
        manager.cleanup.assert_called_once()
        updated = manifest.append.call_args[0][0]
        assert updated.status == "discarded"
