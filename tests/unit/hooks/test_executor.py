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
    async def before_tool_call(self, tool_name, arguments, agent=""):
        self.before_calls.append((tool_name, arguments))
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        self.after_calls.append((tool_name, arguments, result, blocked))


class BlockHook:
    def __init__(self, reason="Blocked by policy"):
        self._reason = reason
    @property
    def name(self):
        return "blocker"
    async def before_tool_call(self, tool_name, arguments, agent=""):
        return ToolResult(output="", error=f"Blocked: {self._reason}")
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        pass


class CrashingBeforeHook:
    @property
    def name(self):
        return "crasher_before"
    async def before_tool_call(self, tool_name, arguments, agent=""):
        raise RuntimeError("hook crashed")
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        pass


class CrashingAfterHook:
    @property
    def name(self):
        return "crasher_after"
    async def before_tool_call(self, tool_name, arguments, agent=""):
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
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


class FailClosedBeforeHook:
    @property
    def name(self):
        return "fail_closed_before"
    @property
    def fail_closed(self):
        return True
    async def before_tool_call(self, tool_name, arguments, agent=""):
        raise RuntimeError("safety hook crashed")
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        pass


class FailClosedAfterHook:
    @property
    def name(self):
        return "fail_closed_after"
    @property
    def fail_closed(self):
        return True
    async def before_tool_call(self, tool_name, arguments, agent=""):
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        raise RuntimeError("safety after hook crashed")


class AgentAwareHook:
    def __init__(self):
        self.agents_seen: list[str] = []
    @property
    def name(self):
        return "agent_aware"
    async def before_tool_call(self, tool_name, arguments, agent=""):
        self.agents_seen.append(agent)
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        pass


class TestHookExecutorFailClosed:
    @pytest.mark.asyncio
    async def test_fail_closed_before_blocks_call(self, inner_executor):
        registry = HookRegistry()
        registry.register(FailClosedBeforeHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        assert result.error is not None
        assert "Policy hook error" in result.error
        inner_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_fail_open_before_allows_call(self, inner_executor):
        """Existing CrashingBeforeHook (no fail_closed) still fails open."""
        registry = HookRegistry()
        registry.register(CrashingBeforeHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        assert result.output == "tool result"
        inner_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_closed_after_logs_error(self, inner_executor):
        """Fail-closed after_tool_call escalates log level but doesn't block result."""
        registry = HookRegistry()
        registry.register(FailClosedAfterHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        # Tool already executed, result still returned
        assert result.output == "tool result"


class TestHookExecutorAgentPassing:
    @pytest.mark.asyncio
    async def test_agent_passed_to_hooks(self, inner_executor):
        registry = HookRegistry()
        hook = AgentAwareHook()
        registry.register(hook)
        executor = HookExecutor(inner=inner_executor, registry=registry, agent="researcher")
        await executor("file_system", {})
        assert hook.agents_seen == ["researcher"]

    @pytest.mark.asyncio
    async def test_agent_defaults_to_empty(self, inner_executor):
        registry = HookRegistry()
        hook = AgentAwareHook()
        registry.register(hook)
        executor = HookExecutor(inner=inner_executor, registry=registry)
        await executor("file_system", {})
        assert hook.agents_seen == [""]
