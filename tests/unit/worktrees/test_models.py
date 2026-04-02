"""Tests for worktree data models."""
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from signalagent.worktrees.models import WorktreeResult, WorktreeRecord, ForkResult, WORKTREE_MERGE_PATTERN


class TestWorktreeResult:
    def test_construction(self) -> None:
        r = WorktreeResult(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            changed_files=["src/main.py", "src/utils.py"],
            diff="--- a/src/main.py\n+++ b/src/main.py\n",
            agent_name="coder",
            is_git=True,
        )
        assert r.id == "wt_abc12345"
        assert r.changed_files == ["src/main.py", "src/utils.py"]
        assert r.is_git is True
        assert r.agent_name == "coder"

    def test_extra_forbidden(self) -> None:
        with pytest.raises(Exception):
            WorktreeResult(
                id="wt_abc12345",
                worktree_path=Path("/tmp/wt"),
                workspace_root=Path("/project"),
                changed_files=[],
                diff="",
                agent_name="coder",
                is_git=True,
                surprise="bad",
            )


class TestWorktreeRecord:
    def test_construction(self) -> None:
        r = WorktreeRecord(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            agent_name="coder",
            created=datetime(2026, 4, 2, tzinfo=timezone.utc),
            status="pending",
            is_git=True,
            branch_name="signal/worktree/coder_wt_abc12345",
        )
        assert r.status == "pending"
        assert r.branch_name == "signal/worktree/coder_wt_abc12345"

    def test_branch_name_optional(self) -> None:
        r = WorktreeRecord(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            agent_name="coder",
            created=datetime(2026, 4, 2, tzinfo=timezone.utc),
            status="pending",
            is_git=False,
        )
        assert r.branch_name is None

    def test_extra_forbidden(self) -> None:
        with pytest.raises(Exception):
            WorktreeRecord(
                id="wt_abc12345",
                worktree_path=Path("/tmp/wt"),
                workspace_root=Path("/project"),
                agent_name="coder",
                created=datetime(2026, 4, 2, tzinfo=timezone.utc),
                status="pending",
                is_git=True,
                surprise="bad",
            )

    def test_json_roundtrip(self) -> None:
        r = WorktreeRecord(
            id="wt_abc12345",
            worktree_path=Path("/tmp/wt"),
            workspace_root=Path("/project"),
            agent_name="coder",
            created=datetime(2026, 4, 2, tzinfo=timezone.utc),
            status="pending",
            is_git=True,
            branch_name="signal/worktree/coder_wt_abc12345",
        )
        json_str = r.model_dump_json()
        restored = WorktreeRecord.model_validate_json(json_str)
        assert restored.id == r.id
        assert restored.worktree_path == r.worktree_path
        assert restored.created == r.created
        assert restored.branch_name == r.branch_name


class TestWorktreeMergePattern:
    def test_matches_standard_format(self) -> None:
        text = "Run: signal worktree merge wt_abc12345\nOr:  signal worktree discard wt_abc12345"
        match = re.search(WORKTREE_MERGE_PATTERN, text)
        assert match is not None
        assert match.group(1) == "wt_abc12345"

    def test_no_match_without_worktree(self) -> None:
        text = "Task complete. No files changed."
        match = re.search(WORKTREE_MERGE_PATTERN, text)
        assert match is None

    def test_extracts_from_multiline_response(self) -> None:
        text = (
            "I fixed the bug in main.py.\n\n"
            "Changes ready for review:\n- src/main.py\n\n"
            "Run: signal worktree merge wt_deadbeef\n"
            "Or:  signal worktree discard wt_deadbeef"
        )
        match = re.search(WORKTREE_MERGE_PATTERN, text)
        assert match is not None
        assert match.group(1) == "wt_deadbeef"


class TestForkResult:
    def test_construction(self) -> None:
        r = ForkResult(
            branch_index=0,
            task_description="fix with dataclasses",
            response="Done.",
            worktree_id="wt_abc12345",
            changed_files=["src/main.py"],
            success=True,
        )
        assert r.branch_index == 0
        assert r.worktree_id == "wt_abc12345"
        assert r.error is None

    def test_failed_branch(self) -> None:
        r = ForkResult(
            branch_index=1,
            task_description="fix with TypedDict",
            response="",
            worktree_id=None,
            changed_files=[],
            success=False,
            error="AI layer timeout",
        )
        assert r.success is False
        assert r.error == "AI layer timeout"

    def test_extra_forbidden(self) -> None:
        with pytest.raises(Exception):
            ForkResult(
                branch_index=0,
                task_description="test",
                response="",
                worktree_id=None,
                changed_files=[],
                success=True,
                surprise="bad",
            )
