# Extending Hooks

## What you'll learn

- The Hook protocol and the before/after tool call lifecycle
- How hooks block or allow tool calls
- Fail-open vs fail-closed semantics
- How to register a hook and configure it in profiles
- How to test a custom hook
- A complete working example

---

## Hook protocol

Every hook implements the `Hook` protocol defined in
`src/signalagent/hooks/protocol.py`:

```python
class Hook(Protocol):
    @property
    def name(self) -> str:
        """Unique hook name for logging and diagnostics."""
        ...

    async def before_tool_call(
        self, tool_name: str, arguments: dict, agent: str = "",
    ) -> ToolResult | None:
        """Inspect or block a tool call before execution.

        Returns None to allow, or a ToolResult to block.
        """
        ...

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool, agent: str = "",
    ) -> None:
        """Observe a completed (or blocked) tool call. Always fires."""
        ...
```

Hooks cannot modify arguments or results. They observe and optionally
block.

---

## Lifecycle

The `HookExecutor` wraps the inner tool executor with this sequence:

```
1. For each hook (registration order):
      call before_tool_call()
      if it returns a ToolResult -> BLOCKED, stop before-hooks
2. If not blocked:
      call inner executor (the actual tool)
3. For each hook (registration order):
      call after_tool_call(blocked=True/False)
```

### before_tool_call

- Return `None` to allow the call to proceed.
- Return a `ToolResult` (typically with `error` set) to block the call.
  The returned `ToolResult` becomes the result seen by the LLM.
- Once one hook blocks, no further before-hooks run and the tool is
  skipped.

### after_tool_call

- Always fires, even when a before-hook blocked the call.
- Receives the `blocked` flag so it knows whether the tool actually ran.
- Return value is ignored.
- Used for logging, metrics, audit trails.

---

## Fail-open vs fail-closed

When a hook's method raises an exception:

### Fail-open (default)

The exception is logged and the hook is skipped. The tool call
proceeds normally. This is the safe default for observability hooks
like `log_tool_calls`.

### Fail-closed

If the hook has a `fail_closed` property that returns `True`, an
exception in `before_tool_call` blocks the tool call with the error.
This is used for security-critical hooks like `PolicyHook`.

Detection is via `getattr(hook, 'fail_closed', False)`. You opt in
by adding a property:

```python
@property
def fail_closed(self) -> bool:
    return True
```

---

## Implementing a custom hook

### Example: Rate limiter

A hook that blocks tool calls when an agent exceeds a per-minute rate
limit:

```python
"""RateLimitHook -- blocks tool calls that exceed a per-minute limit."""
from __future__ import annotations

import time
from collections import defaultdict

from signalagent.core.models import ToolResult


class RateLimitHook:
    """Blocks tool calls when an agent exceeds calls_per_minute."""

    def __init__(self, calls_per_minute: int = 30) -> None:
        """Initialise the rate limiter.

        Args:
            calls_per_minute: Maximum tool calls per agent per minute.
        """
        self._limit = calls_per_minute
        self._calls: dict[str, list[float]] = defaultdict(list)

    @property
    def name(self) -> str:
        return "rate_limit"

    async def before_tool_call(
        self, tool_name: str, arguments: dict, agent: str = "",
    ) -> ToolResult | None:
        """Check rate limit. Block if exceeded."""
        now = time.monotonic()
        window = self._calls[agent]

        # Remove entries older than 60 seconds
        window[:] = [t for t in window if now - t < 60]

        if len(window) >= self._limit:
            return ToolResult(
                output="",
                error=f"Rate limit exceeded: {self._limit} calls/minute",
            )

        window.append(now)
        return None

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool, agent: str = "",
    ) -> None:
        """No-op. Rate tracking happens in before_tool_call."""
        pass
```

---

## Registration

### Built-in hooks

Add your hook to the `load_builtin_hook` factory in
`src/signalagent/hooks/builtins/__init__.py`:

```python
def load_builtin_hook(name: str, instance_dir: Path) -> "Hook | None":
    if name == "log_tool_calls":
        from signalagent.hooks.builtins.log_tool_calls import LogToolCallsHook
        return LogToolCallsHook(log_dir=instance_dir / "logs")
    if name == "rate_limit":
        from signalagent.hooks.builtins.rate_limit import RateLimitHook
        return RateLimitHook(calls_per_minute=30)
    return None
```

### Profile configuration

Activate hooks in the profile YAML under `hooks.active`:

```yaml
hooks:
  active:
    - log_tool_calls
    - rate_limit
```

Hooks are registered in the order listed. This matters for before-hooks
that may block: a security hook listed first blocks before a logging
hook records the attempt.

### Registration order

The `HookRegistry` stores hooks as an ordered list. Hooks registered
first run first. The `PolicyHook` (when security policies exist) is
registered after all profile-configured hooks.

---

## Built-in hooks

### log_tool_calls

Logs every tool call to `{instance_dir}/logs/tool_calls.jsonl`. Each
line contains:

```json
{
    "timestamp": "2025-01-15T10:30:00+00:00",
    "tool_name": "file_system",
    "arguments": {"operation": "read", "path": "config.yaml"},
    "error": null,
    "duration_ms": 12,
    "blocked": false
}
```

Observe-only: `before_tool_call` always returns `None`.

### policy (PolicyHook)

Enforces tool access policies from the profile's `security.policies`
section. Fail-closed: a crash blocks the call. Automatically registered
when any security policies exist.

---

## Testing a custom hook

### Test blocking behavior

```python
import pytest
from signalagent.core.models import ToolResult


class TestRateLimitHook:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        from my_hooks.rate_limit import RateLimitHook

        hook = RateLimitHook(calls_per_minute=5)
        result = await hook.before_tool_call(
            "file_system", {"operation": "read"}, agent="coder",
        )
        assert result is None  # allowed

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        from my_hooks.rate_limit import RateLimitHook

        hook = RateLimitHook(calls_per_minute=3)

        # Make 3 allowed calls
        for _ in range(3):
            result = await hook.before_tool_call(
                "file_system", {}, agent="coder",
            )
            assert result is None

        # 4th call is blocked
        result = await hook.before_tool_call(
            "file_system", {}, agent="coder",
        )
        assert result is not None
        assert "Rate limit exceeded" in result.error
```

### Test integration with HookExecutor

```python
from unittest.mock import AsyncMock
from signalagent.hooks.executor import HookExecutor
from signalagent.hooks.registry import HookRegistry
from signalagent.core.models import ToolResult


class TestRateLimitIntegration:
    @pytest.mark.asyncio
    async def test_executor_respects_block(self):
        from my_hooks.rate_limit import RateLimitHook

        hook = RateLimitHook(calls_per_minute=1)
        registry = HookRegistry()
        registry.register(hook)

        inner = AsyncMock(return_value=ToolResult(output="ok"))
        executor = HookExecutor(inner=inner, registry=registry)

        # First call succeeds
        result = await executor("file_system", {})
        assert result.output == "ok"
        assert inner.call_count == 1

        # Second call blocked by rate limit
        result = await executor("file_system", {})
        assert result.error is not None
        assert inner.call_count == 1  # inner not called again
```

### Test after_tool_call receives blocked flag

```python
class TestAfterHookBlockedFlag:
    @pytest.mark.asyncio
    async def test_after_hook_sees_blocked_true(self):
        after_calls = []

        class SpyHook:
            name = "spy"
            async def before_tool_call(self, tool_name, arguments, agent=""):
                return None
            async def after_tool_call(self, tool_name, arguments, result,
                                      blocked, agent=""):
                after_calls.append(blocked)

        class BlockerHook:
            name = "blocker"
            async def before_tool_call(self, tool_name, arguments, agent=""):
                return ToolResult(output="", error="blocked")
            async def after_tool_call(self, tool_name, arguments, result,
                                      blocked, agent=""):
                after_calls.append(blocked)

        registry = HookRegistry()
        registry.register(BlockerHook())
        registry.register(SpyHook())

        inner = AsyncMock(return_value=ToolResult(output="ok"))
        executor = HookExecutor(inner=inner, registry=registry)
        await executor("tool", {})

        # Both after_tool_call methods see blocked=True
        assert all(b is True for b in after_calls)
```

---

## Next steps

- [Architecture](architecture.md) -- hook pipeline in the execution chain
- [Extending Tools](extending-tools.md) -- the tools that hooks wrap
- [Error Handling](error-handling.md) -- fail-open/fail-closed details
- [Testing](testing.md) -- more hook test patterns
