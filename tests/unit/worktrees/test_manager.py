"""Tests for WorktreeManager."""
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch, MagicMock

import pytest

from signalagent.worktrees.manager import WorktreeManager


class TestGitDetection:
    def test_detects_git_repo(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        assert mgr.is_git is True

    def test_detects_non_git(self, tmp_path: Path) -> None:
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        assert mgr.is_git is False


class TestGitCreate:
    @patch("signalagent.worktrees.manager.subprocess")
    def test_creates_git_worktree(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_sub.run.return_value = CompletedProcess(args=[], returncode=0)
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        result = mgr.create("coder_wt_abc123")
        expected_target = tmp_path / "data" / "worktrees" / "coder_wt_abc123"
        assert result == expected_target
        mock_sub.run.assert_called_once()
        args = mock_sub.run.call_args
        assert "worktree" in args[0][0]
        assert "-b" in args[0][0]
        assert "signal/worktree/coder_wt_abc123" in args[0][0]


class TestGitDiff:
    @patch("signalagent.worktrees.manager.subprocess")
    def test_returns_diff_output(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_sub.run.return_value = CompletedProcess(
            args=[], returncode=0,
            stdout="--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n",
        )
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        diff = mgr.diff(tmp_path / "data" / "worktrees" / "wt1")
        assert "--- a/file.py" in diff
        assert "+new" in diff


class TestGitChangedFiles:
    @patch("signalagent.worktrees.manager.subprocess")
    def test_returns_sorted_files(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_sub.run.return_value = CompletedProcess(
            args=[], returncode=0,
            stdout="src/utils.py\nsrc/main.py\n",
        )
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        files = mgr.changed_files(tmp_path / "wt")
        assert files == ["src/main.py", "src/utils.py"]

    @patch("signalagent.worktrees.manager.subprocess")
    def test_empty_when_no_changes(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_sub.run.return_value = CompletedProcess(
            args=[], returncode=0, stdout="",
        )
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        assert mgr.changed_files(tmp_path / "wt") == []


class TestMerge:
    def test_copies_changed_files(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "existing.py").write_text("old content")

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / "existing.py").write_text("new content")
        (worktree / "new_file.py").write_text("brand new")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        # Use non-git mode for merge test (merge is file-copy regardless)
        mgr._is_git = False
        mgr.merge(worktree)
        assert (workspace / "existing.py").read_text() == "new content"
        assert (workspace / "new_file.py").read_text() == "brand new"

    def test_deletes_removed_files(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "to_delete.py").write_text("will be removed")

        # Use create() so the worktree starts as a proper copy of workspace
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("del_test")
        # Agent deletes the file in the worktree
        (target / "to_delete.py").unlink()

        mgr.merge(target)
        assert not (workspace / "to_delete.py").exists()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / "deep" / "nested").mkdir(parents=True)
        (worktree / "deep" / "nested" / "file.py").write_text("content")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        mgr._is_git = False
        mgr.merge(worktree)
        assert (workspace / "deep" / "nested" / "file.py").read_text() == "content"


class TestCleanup:
    def test_removes_directory(self, tmp_path: Path) -> None:
        wt_dir = tmp_path / "worktree"
        wt_dir.mkdir()
        (wt_dir / "file.py").write_text("content")
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        mgr.cleanup(wt_dir)
        assert not wt_dir.exists()

    @patch("signalagent.worktrees.manager.subprocess")
    def test_prunes_git_worktree(self, mock_sub: MagicMock, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        wt_dir = tmp_path / "worktree"
        wt_dir.mkdir()
        mock_sub.run.return_value = CompletedProcess(args=[], returncode=0)
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        mgr.cleanup(wt_dir, branch_name="signal/worktree/test")
        calls = mock_sub.run.call_args_list
        assert len(calls) == 2
        assert "prune" in calls[0][0][0]
        assert "-D" in calls[1][0][0]
        assert "signal/worktree/test" in calls[1][0][0]

    def test_noop_if_dir_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=tmp_path)
        mgr.cleanup(missing)  # should not raise


class TestNonGitCreate:
    def test_copies_workspace(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "src").mkdir()
        (workspace / "src" / "main.py").write_text("hello")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        assert mgr.is_git is False
        target = mgr.create("test_wt")
        assert target.exists()
        assert (target / "src" / "main.py").read_text() == "hello"

    def test_ignores_dirs(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "__pycache__").mkdir()
        (workspace / "__pycache__" / "cache.pyc").write_bytes(b"bytes")
        (workspace / "src").mkdir()
        (workspace / "src" / "main.py").write_text("code")
        (workspace / "node_modules").mkdir()
        (workspace / "node_modules" / "big.js").write_text("js")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        assert (target / "src" / "main.py").exists()
        assert not (target / "__pycache__").exists()
        assert not (target / "node_modules").exists()


class TestNonGitChangedFiles:
    def test_detects_modified_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "file.py").write_text("original")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        (target / "file.py").write_text("modified")
        changed = mgr.changed_files(target)
        assert "file.py" in changed

    def test_detects_new_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "old.py").write_text("content")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        (target / "new.py").write_text("added")
        changed = mgr.changed_files(target)
        assert "new.py" in changed

    def test_detects_deleted_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "gone.py").write_text("will be deleted")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        (target / "gone.py").unlink()
        changed = mgr.changed_files(target)
        assert "gone.py" in changed

    def test_unchanged_returns_empty(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "same.py").write_text("untouched")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        assert mgr.changed_files(target) == []


class TestNonGitDiff:
    def test_produces_unified_diff(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "file.py").write_text("old line\n")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        (target / "file.py").write_text("new line\n")
        diff = mgr.diff(target)
        assert "--- a/file.py" in diff
        assert "+++ b/file.py" in diff
        assert "-old line" in diff
        assert "+new line" in diff

    def test_empty_diff_when_unchanged(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "same.py").write_text("untouched\n")

        mgr = WorktreeManager(instance_dir=tmp_path, workspace_root=workspace)
        target = mgr.create("test_wt")
        assert mgr.diff(target) == ""
