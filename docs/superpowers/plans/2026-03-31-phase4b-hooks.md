# Phase 4b: Hook Pipeline -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hook pipeline that intercepts tool calls with before/after events -- hooks can observe and block, but not modify. A built-in `log_tool_calls` hook proves the pipeline end-to-end.

**Architecture:** New `hooks/` package provides Hook protocol, HookRegistry, and HookExecutor. HookExecutor wraps any `ToolExecutor` with before/after lifecycle. Bootstrap replaces the bare tool executor closure with `HookExecutor(inner=closure, registry=hook_registry)`. The runner never changes -- it still calls `ToolExecutor(name, args)`.

**Tech Stack:** Python 3.11+, Pydantic v2, asyncio, pytest with asyncio_mode="auto"

---

### Task 1: Add HooksConfig model to core/models.py

**Files:**
- Modify: `src/signalagent/core/models.py:51-62`
- Modify: `tests/unit/core/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/core/test_models.py`:

```python
from signalagent.core.models import HooksConfig


class TestHooksConfig:
    def test_defaults(self):
        hc = HooksConfig()
        assert hc.active == []

    def test_with_hooks(self):
        hc = HooksConfig(active=["log_tool_calls", "path_guard"])
        assert hc.active == ["log_tool_calls", "path_guard"]

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            HooksConfig(active=[], extra="bad")


class TestProfileHooksField:
    def test_profile_has_hooks_default(self):
        p = Profile(name="test")
        assert p.hooks.active == []

    def test_profile_with_hooks(self):
        p = Profile(name="test", hooks=HooksConfig(active=["log_tool_calls"]))
        assert p.hooks.active == ["log_tool_calls"]
```

Ensure `from pydantic import ValidationError` and `from signalagent.core.models import Profile` are in the test file imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_models.py::TestHooksConfig -v`
Expected: FAIL -- `ImportError: cannot import name 'HooksConfig'`

- [ ] **Step 3: Add HooksConfig and hooks field to Profile**

In `src/signalagent/core/models.py`, add `HooksConfig` before the `Profile` class (after `HeartbeatConfig`):

```python
class HooksConfig(BaseModel):
    """Active hooks configuration -- instance-wide tool call interception."""
    model_config = ConfigDict(extra="forbid")

    active: list[str] = Field(default_factory=list)
```

Add `hooks` field to `Profile`:

```python
class Profile(BaseModel):
    """A Signal profile -- defines what an instance becomes."""
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    prime: PrimeConfig = Field(default_factory=PrimeConfig)
    micro_agents: list[MicroAgentConfig] = Field(default_factory=list)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_models.py -v`
Expected: All PASS

Run: `uv run pytest -x -q`
Expected: 219+ passed

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/core/models.py tests/unit/core/test_models.py
git commit -m "feat: add HooksConfig model with active hook list on Profile"
```

---

### Task 2: Hook protocol and HookRegistry

**Files:**
- Create: `src/signalagent/hooks/__init__.py`
- Create: `src/signalagent/hooks/protocol.py`
- Create: `src/signalagent/hooks/registry.py`
- Create: `tests/unit/hooks/__init__.py`
- Create: `tests/unit/hooks/test_registry.py`

- [ ] **Step 1: Write failing tests for HookRegistry**

```python
# tests/unit/hooks/__init__.py
# (empty)
```

```python
# tests/unit/hooks/test_registry.py
"""Unit tests for HookRegistry."""

from signalagent.core.models import ToolResult
from signalagent.hooks.registry import HookRegistry


class FakeHook:
    """Concrete hook for testing."""

    def __init__(self, name: str = "test_hook"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def before_tool_call(
        self, tool_name: str, arguments: dict
    ) -> ToolResult | None:
        return None

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool,
    ) -> None:
        pass


class TestHookRegistryRegisterAndGetAll:
    def test_empty_registry(self):
        registry = HookRegistry()
        assert registry.get_all() == []

    def test_register_and_get_all(self):
        registry = HookRegistry()
        hook = FakeHook()
        registry.register(hook)
        assert registry.get_all() == [hook]

    def test_register_multiple(self):
        registry = HookRegistry()
        h1 = FakeHook(name="a")
        h2 = FakeHook(name="b")
        registry.register(h1)
        registry.register(h2)
        result = registry.get_all()
        assert len(result) == 2
        assert h1 in result
        assert h2 in result

    def test_get_all_preserves_order(self):
        registry = HookRegistry()
        h1 = FakeHook(name="first")
        h2 = FakeHook(name="second")
        registry.register(h1)
        registry.register(h2)
        assert registry.get_all() == [h1, h2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/hooks/test_registry.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'signalagent.hooks'`

- [ ] **Step 3: Create the hooks package, protocol, and registry**

```python
# src/signalagent/hooks/__init__.py
# (empty)
```

```python
# src/signalagent/hooks/protocol.py
"""Hook protocol -- interface every hook must implement."""

from __future__ import annotations

from typing import Protocol

from signalagent.core.models import ToolResult


class Hook(Protocol):
    """Protocol for tool call hooks.

    Hooks observe and optionally block tool calls. They cannot modify
    arguments or results -- they are gates, not transforms.
    """

    @property
    def name(self) -> str: ...

    async def before_tool_call(
        self, tool_name: str, arguments: dict,
    ) -> ToolResult | None:
        """Called before tool execution.

        Return None to allow the call. Return a ToolResult with error
        to block it -- execution will be skipped and the ToolResult
        used as the result.
        """
        ...

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool,
    ) -> None:
        """Called after tool execution (or blocking). Observe only.

        Always fires, including when a before hook blocked the call.
        The blocked flag indicates whether execution was skipped.
        """
        ...
```

```python
# src/signalagent/hooks/registry.py
"""HookRegistry -- storage layer for active hooks."""

from __future__ import annotations

from signalagent.hooks.protocol import Hook


class HookRegistry:
    """Stores hooks and returns them in registration order."""

    def __init__(self) -> None:
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        """Register a hook."""
        self._hooks.append(hook)

    def get_all(self) -> list[Hook]:
        """Return all registered hooks in registration order."""
        return list(self._hooks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/hooks/test_registry.py -v`
Expected: All PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/hooks/__init__.py src/signalagent/hooks/protocol.py src/signalagent/hooks/registry.py tests/unit/hooks/__init__.py tests/unit/hooks/test_registry.py
git commit -m "feat: add Hook protocol and HookRegistry"
```

---

### Task 3: HookExecutor

The core of Phase 4b. Wraps any ToolExecutor with before/after hook lifecycle.

**Files:**
- Create: `src/signalagent/hooks/executor.py`
- Create: `tests/unit/hooks/test_executor.py`

- [ ] **Step 1: Write failing tests for HookExecutor**

```python
# tests/unit/hooks/test_executor.py
"""Unit tests for HookExecutor -- mock inner executor + fake hooks."""

import pytest
from unittest.mock import AsyncMock

from signalagent.core.models import ToolResult
from signalagent.hooks.executor import HookExecutor
from signalagent.hooks.registry import HookRegistry


class AllowHook:
    """Hook that always allows."""

    def __init__(self, name: str = "allow"):
        self._name = name
        self.before_calls: list[tuple] = []
        self.after_calls: list[tuple] = []

    @property
    def name(self) -> str:
        return self._name

    async def before_tool_call(self, tool_name, arguments):
        self.before_calls.append((tool_name, arguments))
        return None

    async def after_tool_call(self, tool_name, arguments, result, blocked):
        self.after_calls.append((tool_name, arguments, result, blocked))


class BlockHook:
    """Hook that blocks with an error."""

    def __init__(self, reason: str = "Blocked by policy"):
        self._reason = reason

    @property
    def name(self) -> str:
        return "blocker"

    async def before_tool_call(self, tool_name, arguments):
        return ToolResult(output="", error=f"Blocked: {self._reason}")

    async def after_tool_call(self, tool_name, arguments, result, blocked):
        pass


class CrashingBeforeHook:
    """Hook whose before_tool_call raises."""

    @property
    def name(self) -> str:
        return "crasher_before"

    async def before_tool_call(self, tool_name, arguments):
        raise RuntimeError("hook crashed")

    async def after_tool_call(self, tool_name, arguments, result, blocked):
        pass


class CrashingAfterHook:
    """Hook whose after_tool_call raises."""

    @property
    def name(self) -> str:
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
        """With no hooks, passes through to inner executor."""
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
        """Once one hook blocks, remaining before hooks don't run."""
        registry = HookRegistry()
        blocker = BlockHook()
        after_blocker = AllowHook(name="should_not_run")
        registry.register(blocker)
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
        """After hooks always fire, even when before hook blocked."""
        registry = HookRegistry()
        blocker = BlockHook()
        observer = AllowHook(name="observer")
        registry.register(blocker)
        registry.register(observer)
        executor = HookExecutor(inner=inner_executor, registry=registry)
        await executor("file_system", {})
        # Observer's after_tool_call should have been called
        assert len(observer.after_calls) == 1
        _, _, result, blocked = observer.after_calls[0]
        assert blocked is True
        assert "Blocked" in result.error


class TestHookExecutorErrorHandling:
    @pytest.mark.asyncio
    async def test_before_hook_crash_fails_open(self, inner_executor):
        """Crashing before hook is treated as allow -- tool executes."""
        registry = HookRegistry()
        registry.register(CrashingBeforeHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        assert result.output == "tool result"
        inner_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_after_hook_crash_swallowed(self, inner_executor):
        """Crashing after hook is swallowed -- result still returned."""
        registry = HookRegistry()
        registry.register(CrashingAfterHook())
        executor = HookExecutor(inner=inner_executor, registry=registry)
        result = await executor("file_system", {})
        assert result.output == "tool result"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/hooks/test_executor.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'signalagent.hooks.executor'`

- [ ] **Step 3: Implement HookExecutor**

```python
# src/signalagent/hooks/executor.py
"""HookExecutor -- wraps a ToolExecutor with before/after hook lifecycle."""

from __future__ import annotations

import logging

from signalagent.core.models import ToolResult
from signalagent.core.protocols import ToolExecutor
from signalagent.hooks.registry import HookRegistry

logger = logging.getLogger(__name__)


class HookExecutor:
    """Wraps any ToolExecutor with before/after hook lifecycle.

    Implements the ToolExecutor protocol (async callable).

    Lifecycle:
    1. Run before_tool_call on each hook. If any returns a ToolResult,
       stop and use it (blocked). Set blocked=True.
    2. If not blocked: call inner executor. Set blocked=False.
    3. Run after_tool_call on all hooks. Always fires. Pass blocked flag.
    4. Return result.
    """

    # NOTE: Fail-open is correct for observer hooks (log_tool_calls)
    # where a logging failure should not block work. When safety-gate
    # hooks land, this should become configurable -- a gate hook that
    # crashes may indicate a dangerous edge case, and fail-closed
    # would be safer. For now, all hooks fail open.

    def __init__(
        self,
        inner: ToolExecutor,
        registry: HookRegistry,
    ) -> None:
        self._inner = inner
        self._registry = registry

    async def __call__(
        self, tool_name: str, arguments: dict,
    ) -> ToolResult:
        hooks = self._registry.get_all()
        blocked = False
        result: ToolResult | None = None

        # Before hooks
        for hook in hooks:
            try:
                before_result = await hook.before_tool_call(tool_name, arguments)
            except Exception as e:
                logger.warning(
                    "Hook '%s' before_tool_call raised (fail open): %s",
                    hook.name, e,
                )
                continue

            if before_result is not None:
                result = before_result
                blocked = True
                break

        # Execute tool if not blocked
        if not blocked:
            result = await self._inner(tool_name, arguments)

        assert result is not None  # either blocked or executed

        # After hooks (always fire)
        for hook in hooks:
            try:
                await hook.after_tool_call(
                    tool_name, arguments, result, blocked,
                )
            except Exception as e:
                logger.warning(
                    "Hook '%s' after_tool_call raised: %s",
                    hook.name, e,
                )

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/hooks/test_executor.py -v`
Expected: All PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/hooks/executor.py tests/unit/hooks/test_executor.py
git commit -m "feat: add HookExecutor with before/after lifecycle, fail-open error handling"
```

---

### Task 4: Built-in log_tool_calls hook

**Files:**
- Create: `src/signalagent/hooks/builtins/__init__.py`
- Create: `src/signalagent/hooks/builtins/log_tool_calls.py`
- Create: `tests/unit/hooks/builtins/__init__.py`
- Create: `tests/unit/hooks/builtins/test_log_tool_calls.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hooks/builtins/__init__.py
# (empty)
```

```python
# tests/unit/hooks/builtins/test_log_tool_calls.py
"""Unit tests for LogToolCallsHook -- uses tmp_path for isolation."""

import json
import pytest

from signalagent.core.models import ToolResult
from signalagent.hooks.builtins.log_tool_calls import LogToolCallsHook


@pytest.fixture
def hook(tmp_path):
    return LogToolCallsHook(log_dir=tmp_path)


@pytest.fixture
def log_file(tmp_path):
    return tmp_path / "tool_calls.jsonl"


class TestLogToolCallsHookProperties:
    def test_name(self, hook):
        assert hook.name == "log_tool_calls"


class TestLogToolCallsBeforeHook:
    @pytest.mark.asyncio
    async def test_always_allows(self, hook):
        result = await hook.before_tool_call("file_system", {"op": "read"})
        assert result is None


class TestLogToolCallsAfterHook:
    @pytest.mark.asyncio
    async def test_writes_jsonl_entry(self, hook, log_file):
        await hook.before_tool_call("file_system", {"operation": "read", "path": "test.txt"})
        await hook.after_tool_call(
            "file_system",
            {"operation": "read", "path": "test.txt"},
            ToolResult(output="hello"),
            blocked=False,
        )
        assert log_file.exists()
        line = log_file.read_text().strip()
        entry = json.loads(line)
        assert entry["tool_name"] == "file_system"
        assert entry["arguments"] == {"operation": "read", "path": "test.txt"}
        assert entry["error"] is None
        assert entry["blocked"] is False
        assert "timestamp" in entry
        assert "duration_ms" in entry

    @pytest.mark.asyncio
    async def test_logs_error(self, hook, log_file):
        await hook.before_tool_call("file_system", {"op": "read"})
        await hook.after_tool_call(
            "file_system",
            {"op": "read"},
            ToolResult(output="", error="File not found"),
            blocked=False,
        )
        entry = json.loads(log_file.read_text().strip())
        assert entry["error"] == "File not found"
        assert entry["blocked"] is False

    @pytest.mark.asyncio
    async def test_logs_blocked_call(self, hook, log_file):
        await hook.before_tool_call("file_system", {})
        await hook.after_tool_call(
            "file_system",
            {},
            ToolResult(output="", error="Blocked: policy"),
            blocked=True,
        )
        entry = json.loads(log_file.read_text().strip())
        assert entry["blocked"] is True
        assert entry["error"] == "Blocked: policy"

    @pytest.mark.asyncio
    async def test_appends_multiple_entries(self, hook, log_file):
        for i in range(3):
            await hook.before_tool_call("tool", {"i": i})
            await hook.after_tool_call(
                "tool", {"i": i}, ToolResult(output=f"result_{i}"), blocked=False,
            )
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_creates_log_dir_if_missing(self, tmp_path):
        log_dir = tmp_path / "nested" / "logs"
        hook = LogToolCallsHook(log_dir=log_dir)
        await hook.before_tool_call("t", {})
        await hook.after_tool_call("t", {}, ToolResult(output="ok"), blocked=False)
        assert (log_dir / "tool_calls.jsonl").exists()

    @pytest.mark.asyncio
    async def test_duration_is_positive(self, hook, log_file):
        await hook.before_tool_call("t", {})
        await hook.after_tool_call("t", {}, ToolResult(output="ok"), blocked=False)
        entry = json.loads(log_file.read_text().strip())
        assert entry["duration_ms"] >= 0


class TestLoadBuiltinHook:
    def test_loads_log_tool_calls(self, tmp_path):
        from signalagent.hooks.builtins import load_builtin_hook
        hook = load_builtin_hook("log_tool_calls", tmp_path)
        assert hook is not None
        assert hook.name == "log_tool_calls"

    def test_returns_none_for_unknown(self, tmp_path):
        from signalagent.hooks.builtins import load_builtin_hook
        assert load_builtin_hook("unknown_hook", tmp_path) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/hooks/builtins/test_log_tool_calls.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'signalagent.hooks.builtins'`

- [ ] **Step 3: Implement LogToolCallsHook and loader**

```python
# src/signalagent/hooks/builtins/__init__.py
"""Built-in hook loading."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signalagent.hooks.protocol import Hook


def load_builtin_hook(name: str, instance_dir: Path) -> Hook | None:
    """Load a built-in hook by name. Returns None for unknown names."""
    if name == "log_tool_calls":
        from signalagent.hooks.builtins.log_tool_calls import LogToolCallsHook
        return LogToolCallsHook(log_dir=instance_dir / "logs")
    return None
```

```python
# src/signalagent/hooks/builtins/log_tool_calls.py
"""LogToolCallsHook -- logs tool calls to JSONL."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from signalagent.core.models import ToolResult

logger = logging.getLogger(__name__)


class LogToolCallsHook:
    """Logs every tool call to a JSONL file.

    Exercises both before_tool_call (records start time) and
    after_tool_call (writes the log entry with duration).
    """

    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._pending_start: float | None = None
        # NOTE: _pending_start as instance state works because hooks
        # are called sequentially on a single coroutine (no concurrent
        # tool calls in 4b). If Phase 5+ adds concurrency, this needs
        # to change (e.g., pass context through lifecycle, or key by
        # tool_call_id).

    @property
    def name(self) -> str:
        return "log_tool_calls"

    async def before_tool_call(
        self, tool_name: str, arguments: dict,
    ) -> ToolResult | None:
        """Record start time. Always allows (returns None)."""
        self._pending_start = time.monotonic()
        return None

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool,
    ) -> None:
        """Write JSONL log entry with timing and result info."""
        duration_ms = 0
        if self._pending_start is not None:
            duration_ms = int((time.monotonic() - self._pending_start) * 1000)
            self._pending_start = None

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "arguments": arguments,
            "error": result.error,
            "duration_ms": duration_ms,
            "blocked": blocked,
        }

        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._log_dir / "tool_calls.jsonl"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning("Failed to write tool call log: %s", e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/hooks/builtins/test_log_tool_calls.py -v`
Expected: All PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/hooks/builtins/__init__.py src/signalagent/hooks/builtins/log_tool_calls.py tests/unit/hooks/builtins/__init__.py tests/unit/hooks/builtins/test_log_tool_calls.py
git commit -m "feat: add log_tool_calls hook with JSONL logging"
```

---

### Task 5: Wire hook pipeline in bootstrap and update tests

**Files:**
- Modify: `src/signalagent/runtime/bootstrap.py`
- Modify: `tests/unit/runtime/test_bootstrap.py`

- [ ] **Step 1: Update bootstrap.py**

Replace `src/signalagent/runtime/bootstrap.py`:

```python
"""Bootstrap -- single wiring point for the multi-agent runtime."""
from __future__ import annotations
from pathlib import Path

from signalagent.agents.host import AgentHost
from signalagent.agents.micro import MicroAgent
from signalagent.agents.prime import PrimeAgent
from signalagent.ai.layer import AILayer
from signalagent.comms.bus import MessageBus
from signalagent.core.config import SignalConfig
from signalagent.core.models import Profile, ToolResult
from signalagent.hooks.builtins import load_builtin_hook
from signalagent.hooks.executor import HookExecutor
from signalagent.hooks.registry import HookRegistry
from signalagent.runtime.executor import Executor
from signalagent.runtime.runner import AgenticRunner
from signalagent.tools.builtins import load_builtin_tool
from signalagent.tools.registry import ToolRegistry


async def bootstrap(
    instance_dir: Path,
    config: SignalConfig,
    profile: Profile,
) -> tuple[Executor, MessageBus, AgentHost]:
    """Wire up the full multi-agent runtime."""
    ai = AILayer(config)
    bus = MessageBus()
    host = AgentHost(bus)

    # Tool registry
    registry = ToolRegistry()
    for tool_name in profile.plugins.available:
        tool = load_builtin_tool(tool_name, instance_dir)
        if tool is not None:
            registry.register(tool)

    # Inner tool executor -- registry lookup + error handling
    async def inner_executor(tool_name: str, arguments: dict) -> ToolResult:
        tool = registry.get(tool_name)
        if tool is None:
            return ToolResult(output="", error=f"Unknown tool: {tool_name}")
        try:
            return await tool.execute(**arguments)
        except Exception as e:
            return ToolResult(output="", error=str(e))

    # Hook registry
    hook_registry = HookRegistry()
    for hook_name in profile.hooks.active:
        hook = load_builtin_hook(hook_name, instance_dir)
        if hook is not None:
            hook_registry.register(hook)

    # Wrap inner executor with hooks
    tool_executor = HookExecutor(inner=inner_executor, registry=hook_registry)

    global_max = config.tools.max_iterations

    # Prime agent -- no agentic tool loop. If Prime gains tools in a
    # future phase, apply global_max cap here too.
    prime = PrimeAgent(identity=profile.prime.identity, ai=ai, host=host, bus=bus)
    host.register(prime, talks_to=None)

    # Micro-agents with runners
    for micro_config in profile.micro_agents:
        agent_max = min(micro_config.max_iterations, global_max)
        tool_schemas = registry.get_schemas(micro_config.plugins)
        runner = AgenticRunner(
            ai=ai, tool_executor=tool_executor,
            tool_schemas=tool_schemas, max_iterations=agent_max,
        )
        agent = MicroAgent(config=micro_config, runner=runner)
        talks_to = set(micro_config.talks_to)
        host.register(agent, talks_to=talks_to)

    executor = Executor(bus=bus)
    return executor, bus, host
```

- [ ] **Step 2: Add bootstrap test with hooks active**

Update the imports at the top of `tests/unit/runtime/test_bootstrap.py` to:

```python
from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
    PluginsConfig,
    HooksConfig,
    ToolCallRequest,
)
```

Then add the new fixture and test:

```python
# Add new fixture:
@pytest.fixture
def profile_with_hooks():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        hooks=HooksConfig(active=["log_tool_calls"]),
        micro_agents=[
            MicroAgentConfig(name="researcher", skill="Research files",
                             talks_to=["prime"], plugins=["file_system"]),
        ],
    )

# Add new test to TestBootstrap class:
    @pytest.mark.asyncio
    async def test_hooks_log_tool_calls(self, tmp_path, config, profile_with_hooks, monkeypatch):
        """Tool calls are logged to JSONL when log_tool_calls hook is active."""
        (tmp_path / "notes.txt").write_text("data")
        tc = ToolCallRequest(id="call_1", name="file_system",
                             arguments={"operation": "read", "path": "notes.txt"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("", tool_calls=[tc]),
            _make_ai_response("Got it"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)
        executor, bus, host = await bootstrap(tmp_path, config, profile_with_hooks)
        result = await executor.run("read notes")
        assert result.content == "Got it"

        # Verify log file was written
        import json
        log_file = tmp_path / "logs" / "tool_calls.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["tool_name"] == "file_system"
        assert entry["blocked"] is False
```


- [ ] **Step 3: Run all tests**

Run: `uv run pytest -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/signalagent/runtime/bootstrap.py tests/unit/runtime/test_bootstrap.py
git commit -m "feat: wire hook pipeline in bootstrap, add integration test"
```

---

### Task 6: Update docs, bump version, verify end-to-end

**Files:**
- Modify: `docs/dev/architecture.md`
- Modify: `docs/dev/project-structure.md`
- Modify: `docs/dev/testing.md`
- Modify: `docs/dev/roadmap.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`
- Modify: `src/signalagent/__init__.py`

- [ ] **Step 1: Run full test suite and count**

Run: `uv run pytest -x -q`
Expected: All pass. Note the test count.

- [ ] **Step 2: Update architecture.md**

Add a "Hook Pipeline" subsection under Tool Execution Architecture:
- HookExecutor wraps the inner ToolExecutor with before/after hook lifecycle
- Before hooks can block (return ToolResult with error), after hooks are observe-only
- After hooks always fire, including on blocked calls (receive blocked flag)
- Hooks fail open on error (documented for future configurability)
- Update header to "Phase 4b"

- [ ] **Step 3: Update project-structure.md**

Add:
- `hooks/` package: protocol, registry, executor
- `hooks/builtins/`: built-in hooks (log_tool_calls)
- Add test directories
- Remove hooks references from "Modules Planned" if any

- [ ] **Step 4: Update roadmap.md**

Phase 4b status: Complete

- [ ] **Step 5: Update testing.md**

Update test count. Add hook test patterns section.

- [ ] **Step 6: Update README.md**

Update status to "Phase 4b of 10 complete." Add hook pipeline description.

- [ ] **Step 7: Update CHANGELOG.md**

Add `## [0.5.0] - 2026-03-31` section:
### Added
- Hook protocol with before_tool_call (block/allow) and after_tool_call (observe)
- HookRegistry for instance-wide hook management
- HookExecutor wrapping ToolExecutor with hook lifecycle
- LogToolCallsHook: JSONL logging of all tool calls with timing
- HooksConfig model with active hook list on Profile
### Changed
- Bootstrap wires hook pipeline: inner executor -> HookExecutor

- [ ] **Step 8: Bump version**

`src/signalagent/__init__.py`: `__version__ = "0.5.0"`
`VERSION`: `0.5.0`

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest -v`
Expected: All pass

- [ ] **Step 10: Commit**

```bash
git add docs/ README.md CHANGELOG.md
git commit -m "docs: update architecture, structure, testing, and roadmap for Phase 4b"

git add VERSION src/signalagent/__init__.py
git commit -m "chore: bump version to 0.5.0 for Phase 4b hook pipeline"
```

---

## Self-Review

**Spec coverage check:**
- (a) Hook protocol with before/after: Task 2
- (b) HookRegistry with get_all(): Task 2
- (c) HookExecutor lifecycle, after hooks always fire: Task 3
- (d) before_tool_call blocks with ToolResult, no mutation: Task 3
- (e) Hook errors fail open, documented: Task 3
- (f) HooksConfig with active list on Profile: Task 1
- (g) log_tool_calls JSONL hook: Task 4
- (h) Bootstrap wires hook pipeline: Task 5
- (i) End-to-end with hooks: Task 5 (test_hooks_log_tool_calls)
- (j) No-hooks passthrough: Task 3 (test_passthrough)

All 10 done-when criteria covered.

**Placeholder scan:** No TBD, TODO, or vague steps found.

**Type consistency check:**
- `Hook` protocol used consistently: Task 2 (definition), Task 3 (FakeHook/BlockHook in tests), Task 4 (LogToolCallsHook)
- `HookRegistry` used consistently: Task 2 (definition), Task 3 (HookExecutor tests), Task 5 (bootstrap)
- `HookExecutor(inner=, registry=)` consistent between Task 3 (implementation) and Task 5 (bootstrap wiring)
- `before_tool_call(tool_name, arguments) -> ToolResult | None` consistent across all files
- `after_tool_call(tool_name, arguments, result, blocked) -> None` consistent across all files
- `load_builtin_hook(name, instance_dir) -> Hook | None` consistent between Task 4 (implementation) and Task 5 (bootstrap call)
- `HooksConfig(active=)` consistent between Task 1 (model) and Task 5 (bootstrap/test fixtures)
