"""Unit tests for HookExecutor -- mock inner executor + fake hooks."""
import pytest
from unittest.mock import AsyncMock
from signalagent.core.models import ToolResult
from signalagent.hooks.executor import HookExecutor
from signalagent.hooks.registry import HookRegistry


class AllowHook:
    def __init__(self, name="allow"):
        self._name = name
        self.before_calls = []
        self.after_calls = []
    @property
    def name(self):
        return self._name
    async def before_tool_call(self, tool_name, arguments):
        self.before_calls.append((tool_name, arguments))
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked):
        self.after_calls.append((tool_name, arguments, result, blocked))


class BlockHook:
    def __init__(self, reason="Blocked by policy"):
        self._reason = reason
    @property
    def name(self):
        return "blocker"
    async def before_tool_call(self, tool_name, arguments):
        return ToolResult(output="", error=f"Blocked: {self._reason}")
    async def after_tool_call(self, tool_name, arguments, result, blocked):
        pass


class CrashingBeforeHook:
    @property
    def name(self):
        return "crasher_before"
    async def before_tool_call(self, tool_name, arguments):
        raise RuntimeError("hook crashed")
    async def after_tool_call(self, tool_name, arguments, result, blocked):
        pass


class CrashingAfterHook:
    @property
    def name(self):
        return "crasher_after"
    async def before_tool_call(self, tool_name, arguments):
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked):
        raise RuntimeError("after hook crashed")


@pytest.fixture
def inner_executor():
    return AsyncMock(return_value=ToolResult(output="tool result"))


class TestHookExecutorNoHooks:
    @pytest.mark.asyncio
    async def test_passthrough(self, inner_executor):
        registry = HookRegistry()
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {"operation": "read"})
        assert result.output == "tool result"
        inner_executor.assert_called_once_with("file_system", {"operation": "read"})


class TestHookExecutorBeforeHooks:
    @pytest.mark.asyncio
    async def test_before_hook_called(self, inner_executor):
        registry = HookRegistry()
        hook = AllowHook()
        registry.register(hook)
        executor = HookExecutor(inner=inner_executor, registry=registry)
        await executor("file_system", {"op": "read"})
        assert len(hook.before_calls) == 1
        assert hook.before_calls[0] == ("file_system", {"op": "read"})

    @pytest.mark.asyncio
    async def test_before_hook_blocks(self, inner_executor):
        registry = HookRegistry()
        registry.register(BlockHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {"op": "read"})
        assert result.error is not None
        assert "Blocked" in result.error
        inner_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_block_stops_remaining_before_hooks(self, inner_executor):
        registry = HookRegistry()
        registry.register(BlockHook())
        after_blocker = AllowHook(name="should_not_run")
        registry.register(after_blocker)
        executor = HookExecutor(inner=inner_executor, registry=registry)
        await executor("file_system", {})
        assert len(after_blocker.before_calls) == 0


class TestHookExecutorAfterHooks:
    @pytest.mark.asyncio
    async def test_after_hook_called_on_success(self, inner_executor):
        registry = HookRegistry()
        hook = AllowHook()
        registry.register(hook)
        executor = HookExecutor(inner=inner_executor, registry=registry)
        await executor("file_system", {"op": "read"})
        assert len(hook.after_calls) == 1
        name, args, result, blocked = hook.after_calls[0]
        assert name == "file_system"
        assert result.output == "tool result"
        assert blocked is False

    @pytest.mark.asyncio
    async def test_after_hook_fires_on_blocked_call(self, inner_executor):
        registry = HookRegistry()
        blocker = BlockHook()
        observer = AllowHook(name="observer")
        registry.register(blocker)
        registry.register(observer)
        executor = HookExecutor(inner=inner_executor, registry=registry)
        await executor("file_system", {})
        assert len(observer.after_calls) == 1
        _, _, result, blocked = observer.after_calls[0]
        assert blocked is True
        assert "Blocked" in result.error


class TestHookExecutorErrorHandling:
    @pytest.mark.asyncio
    async def test_before_hook_crash_fails_open(self, inner_executor):
        registry = HookRegistry()
        registry.register(CrashingBeforeHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        assert result.output == "tool result"
        inner_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_after_hook_crash_swallowed(self, inner_executor):
        registry = HookRegistry()
        registry.register(CrashingAfterHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        assert result.output == "tool result"
