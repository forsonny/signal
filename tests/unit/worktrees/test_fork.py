"""Tests for ForkRunner."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from signalagent.runtime.executor import ExecutorResult
from signalagent.worktrees.fork import ForkRunner
from signalagent.worktrees.models import ForkResult


@pytest.fixture
def mock_executor() -> AsyncMock:
    executor = AsyncMock()
    return executor


@pytest.fixture
def mock_manifest() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.changed_files.return_value = ["src/main.py"]
    return mgr


@pytest.fixture
def runner(mock_executor, mock_manifest, mock_manager) -> ForkRunner:
    return ForkRunner(
        executor=mock_executor,
        manifest=mock_manifest,
        manager=mock_manager,
        max_concurrent=2,
    )


class TestForkRunner:
    @pytest.mark.asyncio
    async def test_runs_all_branches(
        self, runner: ForkRunner, mock_executor: AsyncMock,
    ) -> None:
        mock_executor.run.return_value = ExecutorResult(
            content="Done.\n\nRun: signal worktree merge wt_abc12345",
        )
        results = await runner.run(["task A", "task B"])
        assert len(results) == 2
        assert mock_executor.run.call_count == 2

    @pytest.mark.asyncio
    async def test_extracts_worktree_id_from_response(
        self, runner: ForkRunner, mock_executor: AsyncMock, mock_manifest: MagicMock,
    ) -> None:
        mock_executor.run.return_value = ExecutorResult(
            content="Changed files:\n- src/main.py\n\nRun: signal worktree merge wt_deadbeef\nOr:  signal worktree discard wt_deadbeef",
        )
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_record = MagicMock()
        mock_record.worktree_path = mock_path
        mock_manifest.get.return_value = mock_record

        results = await runner.run(["task A"])
        assert results[0].worktree_id == "wt_deadbeef"
        assert results[0].changed_files == ["src/main.py"]

    @pytest.mark.asyncio
    async def test_no_worktree_when_no_match(
        self, runner: ForkRunner, mock_executor: AsyncMock,
    ) -> None:
        mock_executor.run.return_value = ExecutorResult(
            content="Analysis complete. No files changed.",
        )
        results = await runner.run(["analyze this"])
        assert results[0].worktree_id is None
        assert results[0].changed_files == []

    @pytest.mark.asyncio
    async def test_failed_branch(
        self, runner: ForkRunner, mock_executor: AsyncMock,
    ) -> None:
        mock_executor.run.return_value = ExecutorResult(
            content="", error="AI layer timeout",
        )
        results = await runner.run(["failing task"])
        assert results[0].success is False
        assert results[0].error == "AI layer timeout"

    @pytest.mark.asyncio
    async def test_exception_in_run_handled(
        self, runner: ForkRunner, mock_executor: AsyncMock,
    ) -> None:
        mock_executor.run.side_effect = RuntimeError("unexpected crash")
        results = await runner.run(["crashing task"])
        assert results[0].success is False
        assert "unexpected crash" in results[0].error

    @pytest.mark.asyncio
    async def test_branch_indices_preserved(
        self, runner: ForkRunner, mock_executor: AsyncMock,
    ) -> None:
        mock_executor.run.return_value = ExecutorResult(content="Done.")
        results = await runner.run(["task A", "task B", "task C"])
        assert [r.branch_index for r in results] == [0, 1, 2]
        assert [r.task_description for r in results] == ["task A", "task B", "task C"]

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrency(
        self, mock_executor: AsyncMock, mock_manifest: MagicMock, mock_manager: MagicMock,
    ) -> None:
        max_seen = 0
        current = 0

        async def slow_run(user_message, session_id=None):
            nonlocal max_seen, current
            current += 1
            if current > max_seen:
                max_seen = current
            await asyncio.sleep(0.05)
            current -= 1
            return ExecutorResult(content="Done.")

        mock_executor.run = slow_run
        runner = ForkRunner(
            executor=mock_executor,
            manifest=mock_manifest,
            manager=mock_manager,
            max_concurrent=2,
        )
        await runner.run(["A", "B", "C", "D"])
        assert max_seen <= 2

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(
        self, runner: ForkRunner, mock_executor: AsyncMock,
    ) -> None:
        call_count = 0

        async def alternating_run(user_message, session_id=None):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                return ExecutorResult(content="", error="failed")
            return ExecutorResult(
                content="Done.\n\nRun: signal worktree merge wt_aaa11111",
            )

        mock_executor.run = alternating_run
        results = await runner.run(["task A", "task B"])
        assert results[0].success is True
        assert results[1].success is False
