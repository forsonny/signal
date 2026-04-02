"""Tests for WorktreeProxy."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalagent.core.models import ToolResult
from signalagent.core.protocols import WorktreeProxyProtocol
from signalagent.worktrees.proxy import WorktreeProxy


@pytest.fixture
def mock_inner() -> AsyncMock:
    """Mock inner executor (HookExecutor chain)."""
    inner = AsyncMock()
    inner.return_value = ToolResult(output="inner result")
    return inner


@pytest.fixture
def mock_hook_registry() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.is_git = True
    mgr.create.return_value = Path("/tmp/wt/test_wt")
    mgr.changed_files.return_value = ["src/main.py"]
    mgr.diff.return_value = "--- a/src/main.py\n+++ b/src/main.py\n"
    return mgr


@pytest.fixture
def mock_manifest() -> MagicMock:
    return MagicMock()


@pytest.fixture
def proxy(
    mock_inner: AsyncMock,
    mock_hook_registry: MagicMock,
    mock_manager: MagicMock,
    mock_manifest: MagicMock,
    tmp_path: Path,
) -> WorktreeProxy:
    return WorktreeProxy(
        inner=mock_inner,
        hook_registry=mock_hook_registry,
        worktree_manager=mock_manager,
        manifest=mock_manifest,
        workspace_root=tmp_path / "workspace",
        instance_dir=tmp_path,
        agent_name="coder",
    )


class TestPassthroughMode:
    @pytest.mark.asyncio
    async def test_non_file_system_passes_through(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock,
    ) -> None:
        result = await proxy("bash", {"command": "ls"})
        mock_inner.assert_called_once_with("bash", {"command": "ls"})
        assert result.output == "inner result"

    @pytest.mark.asyncio
    async def test_file_system_read_passes_through(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock,
    ) -> None:
        result = await proxy("file_system", {"operation": "read", "path": "src/main.py"})
        mock_inner.assert_called_once_with(
            "file_system", {"operation": "read", "path": "src/main.py"},
        )

    @pytest.mark.asyncio
    async def test_file_system_list_passes_through(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock,
    ) -> None:
        await proxy("file_system", {"operation": "list", "path": "."})
        mock_inner.assert_called_once()


class TestIsolatedMode:
    @pytest.mark.asyncio
    async def test_first_write_creates_worktree(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        # Mock the worktree FileSystemTool execution
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="Written: src/main.py")
            await proxy("file_system", {"operation": "write", "path": "src/main.py", "content": "hello"})
        mock_manager.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_after_write_goes_to_worktree(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            # First write triggers isolation
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})
            # Subsequent read goes to worktree, not inner
            await proxy("file_system", {"operation": "read", "path": "f.py"})
        assert mock_exec.call_count == 2
        # Inner should NOT be called for file_system after isolation
        for call in mock_inner.call_args_list:
            assert call[0][0] != "file_system"

    @pytest.mark.asyncio
    async def test_non_file_system_still_passes_through_in_isolated(
        self, proxy: WorktreeProxy, mock_inner: AsyncMock, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})
        # Non-file_system should still go through inner
        await proxy("bash", {"command": "ls"})
        mock_inner.assert_called_with("bash", {"command": "ls"})


class TestHooksInIsolatedMode:
    @pytest.mark.asyncio
    async def test_before_and_after_hooks_fire(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        before_calls: list[tuple] = []
        after_calls: list[tuple] = []

        class FakeHook:
            name = "test_hook"
            async def before_tool_call(self, tool_name, arguments):
                before_calls.append((tool_name, arguments))
                return None
            async def after_tool_call(self, tool_name, arguments, result, blocked):
                after_calls.append((tool_name, arguments, blocked))

        proxy._hook_registry.get_all.return_value = [FakeHook()]

        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="Written: f.py")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})

        assert len(before_calls) == 1
        assert before_calls[0][0] == "file_system"
        assert len(after_calls) == 1
        assert after_calls[0][2] is False  # blocked=False

    @pytest.mark.asyncio
    async def test_hook_can_block(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")

        class BlockingHook:
            name = "blocker"
            async def before_tool_call(self, tool_name, arguments):
                return ToolResult(output="", error="Blocked by policy")
            async def after_tool_call(self, tool_name, arguments, result, blocked):
                pass

        proxy._hook_registry.get_all.return_value = [BlockingHook()]

        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            # Trigger isolation first with no hooks
            proxy._hook_registry.get_all.return_value = []
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})
            # Now add blocking hook
            proxy._hook_registry.get_all.return_value = [BlockingHook()]
            result = await proxy("file_system", {"operation": "write", "path": "g.py", "content": "y"})

        assert result.error == "Blocked by policy"

    @pytest.mark.asyncio
    async def test_before_hook_crash_fails_open(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")

        class CrashingHook:
            name = "crasher"
            async def before_tool_call(self, tool_name, arguments):
                raise RuntimeError("hook exploded")
            async def after_tool_call(self, tool_name, arguments, result, blocked):
                pass

        proxy._hook_registry.get_all.return_value = [CrashingHook()]

        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            # Trigger isolation first with no hooks
            proxy._hook_registry.get_all.return_value = []
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})
            # Now add crashing hook
            proxy._hook_registry.get_all.return_value = [CrashingHook()]
            result = await proxy("file_system", {"operation": "write", "path": "g.py", "content": "y"})

        # Execution should proceed despite hook crash (fail-open)
        mock_exec.assert_called()


class TestTakeResult:
    @pytest.mark.asyncio
    async def test_returns_result_after_writes(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})

        result = proxy.take_result()
        assert result is not None
        assert result.agent_name == "coder"
        assert result.changed_files == ["src/main.py"]

    def test_returns_none_without_writes(self, proxy: WorktreeProxy) -> None:
        assert proxy.take_result() is None

    @pytest.mark.asyncio
    async def test_resets_after_take(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})

        proxy.take_result()
        assert proxy.take_result() is None

    def test_satisfies_protocol(self) -> None:
        assert issubclass(WorktreeProxy, WorktreeProxyProtocol)

    @pytest.mark.asyncio
    async def test_proxy_reusable_after_take(
        self, proxy: WorktreeProxy, mock_manager: MagicMock, mock_manifest: MagicMock,
    ) -> None:
        """After take_result(), a second write creates a new worktree."""
        mock_manager.create.return_value = Path("/tmp/wt")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            # First task: write triggers isolation
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})

        first_result = proxy.take_result()
        assert first_result is not None

        # Second task: another write should create a NEW worktree
        mock_manager.create.return_value = Path("/tmp/wt2")
        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            await proxy("file_system", {"operation": "write", "path": "g.py", "content": "y"})

        second_result = proxy.take_result()
        assert second_result is not None
        # Should be a different worktree ID
        assert first_result.id != second_result.id
        # Manager.create should have been called twice total
        assert mock_manager.create.call_count == 2

    @pytest.mark.asyncio
    async def test_result_includes_all_fields(
        self, proxy: WorktreeProxy, mock_manager: MagicMock,
    ) -> None:
        mock_manager.create.return_value = Path("/tmp/wt")
        mock_manager.changed_files.return_value = ["a.py", "b.py"]
        mock_manager.diff.return_value = "diff content"
        mock_manager.is_git = True

        with patch.object(proxy, "_execute_in_worktree", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(output="ok")
            await proxy("file_system", {"operation": "write", "path": "f.py", "content": "x"})

        result = proxy.take_result()
        assert result is not None
        assert result.changed_files == ["a.py", "b.py"]
        assert result.diff == "diff content"
        assert result.is_git is True
        assert result.agent_name == "coder"
        assert result.id.startswith("wt_")
