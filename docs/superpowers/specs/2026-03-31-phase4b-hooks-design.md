# Phase 4b: Hook Pipeline -- Design Spec

## Goal

Add a hook pipeline that intercepts tool calls with before/after events. Hooks are instance-wide safety gates: they can observe and block tool calls, but cannot modify arguments or results. A built-in `log_tool_calls` hook proves the pipeline end-to-end.

## Architecture

Phase 4b adds one new package and modifies two existing modules:

**New:**
- `hooks/` -- Hook protocol, HookRegistry, HookExecutor, built-in log_tool_calls hook

**Modified:**
- `core/models.py` -- HooksConfig model for profile YAML
- `runtime/bootstrap.py` -- Wire hook registry, create HookExecutor instead of closure

### Execution Flow

```
AgenticRunner calls ToolExecutor(name, args)
        |
        v
   HookExecutor
        |
        v
  before_tool_call hooks (sequential)
        |
        +--> any hook blocks? --> skip execution, use blocked result
        |
        +--> all hooks allow? --> execute tool via inner executor
        |
        v
  after_tool_call hooks (sequential, always fire)
        |
        v
  return ToolResult to runner
```

The runner doesn't change. It still calls `ToolExecutor(name, args)`. `HookExecutor` implements the same protocol and wraps the real execution with the hook lifecycle.

### Dependency Graph

```
hooks/protocol.py   --> core/models (ToolResult)
hooks/registry.py   --> hooks/protocol
hooks/executor.py   --> hooks/protocol, hooks/registry, core/protocols (ToolExecutor)
hooks/builtins/*    --> hooks/protocol, core/models
runtime/bootstrap   --> hooks/* (wiring point)
```

No dependency on `tools/` from `hooks/`. HookExecutor wraps any ToolExecutor implementation, not specifically the registry-based one. Hooks and tools are fully decoupled.

---

## Components

### 1. Hook Protocol (hooks/protocol.py)

Every hook implements:

```python
class Hook(Protocol):
    @property
    def name(self) -> str: ...

    async def before_tool_call(
        self, tool_name: str, arguments: dict
    ) -> ToolResult | None: ...

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool,
    ) -> None: ...
```

`before_tool_call` returns `None` to allow the call, or a `ToolResult` with error to block it. No argument mutation -- every hook sees the same arguments regardless of ordering.

`after_tool_call` is observe-only. Returns nothing, cannot modify the result. Always fires, including on blocked calls -- so observer hooks like `log_tool_calls` see the full picture.

A hook that only cares about one event returns `None` / does nothing for the other. No configuration needed to express this.

### 2. Hook Registry (hooks/registry.py)

Simple storage layer:

```python
class HookRegistry:
    def register(self, hook: Hook) -> None: ...
    def get_all(self) -> list[Hook]: ...
```

One list, one method. The HookExecutor calls `before_tool_call` on all hooks, then `after_tool_call` on all hooks. The hook itself decides which events it cares about.

### 3. HookExecutor (hooks/executor.py)

Wraps any `ToolExecutor` with the hook lifecycle:

```python
class HookExecutor:
    def __init__(
        self,
        inner: ToolExecutor,
        registry: HookRegistry,
    ) -> None: ...

    async def __call__(
        self, tool_name: str, arguments: dict
    ) -> ToolResult: ...
```

Implements the `ToolExecutor` protocol (async callable with `(tool_name, arguments) -> ToolResult`).

**Lifecycle in `__call__`:**

1. Run `before_tool_call` on each hook (sequential). If any returns a `ToolResult` (blocked), stop running remaining before hooks, skip tool execution, use the blocked result. Set `blocked = True`.
2. If no hook blocked: call `self._inner(tool_name, arguments)`. Set `blocked = False`.
3. Run `after_tool_call` on all hooks (sequential, always fires). Pass the result and `blocked` flag.
4. Return the result.

**Error handling in hooks:**

If a hook's `before_tool_call` or `after_tool_call` raises an unexpected exception, the executor catches it and logs a warning. The pipeline continues:

- For before hooks: a raised exception is treated as "allow" (fail open). The tool call proceeds.
- For after hooks: a raised exception is swallowed with a log warning.

```python
# NOTE: Fail-open is correct for observer hooks (log_tool_calls) where a
# logging failure should not block work. When safety-gate hooks land,
# this should become configurable -- a gate hook that crashes may indicate
# a dangerous edge case, and fail-closed would be safer. For now, all
# hooks fail open.
```

### 4. Profile Model (core/models.py)

```python
class HooksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: list[str] = Field(default_factory=list)
```

Added to Profile as `hooks: HooksConfig = Field(default_factory=HooksConfig)`.

Profile YAML:
```yaml
hooks:
  active: [log_tool_calls]
```

One list of active hook names. Instance-wide -- applies to all tool calls across all agents. The profile is the single source of truth for what guards are in place.

### 5. Built-in log_tool_calls Hook (hooks/builtins/log_tool_calls.py)

Exercises both events. Logs to `{instance_dir}/logs/tool_calls.jsonl`.

```python
class LogToolCallsHook:
    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._pending_start: float | None = None
        # NOTE: _pending_start as instance state works because hooks are
        # called sequentially on a single coroutine (no concurrent tool
        # calls in 4b). If Phase 5+ adds concurrency, this needs to
        # change (e.g., pass context through lifecycle, or key by
        # tool_call_id).

    @property
    def name(self) -> str:
        return "log_tool_calls"

    async def before_tool_call(
        self, tool_name: str, arguments: dict
    ) -> ToolResult | None:
        self._pending_start = time.monotonic()
        return None  # always allows

    async def after_tool_call(
        self, tool_name: str, arguments: dict, result: ToolResult,
        blocked: bool,
    ) -> None:
        # Compute duration
        # Append JSON line to log file with blocked flag
```

Each log entry (one JSON object per line):

```json
{
    "timestamp": "2026-03-31T12:00:00Z",
    "tool_name": "file_system",
    "arguments": {"operation": "read", "path": "notes.txt"},
    "error": null,
    "duration_ms": 12,
    "blocked": false
}
```

- `error`: the error string if the tool call failed or was blocked, null on success
- `blocked`: true if a before hook blocked the call. The `blocked` flag is passed explicitly by HookExecutor to `after_tool_call` -- hooks don't need to infer it.
- `arguments`: logged in full (typically small)
- Output is NOT logged (can be large). The `error` field captures failure information.

**Loading:** `hooks/builtins/__init__.py` exports `load_builtin_hook(name: str, instance_dir: Path) -> Hook | None`. Maps `"log_tool_calls"` to `LogToolCallsHook(log_dir=instance_dir / "logs")`. Returns None for unknown names.

### 6. Bootstrap Changes (runtime/bootstrap.py)

Bootstrap creates the hook pipeline:

```python
# Inner executor -- same closure as 4a
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
```

The `tool_executor` passed to each `AgenticRunner` is now a `HookExecutor`. The runner's interface is unchanged.

When no hooks are active, `HookRegistry.get_all()` returns an empty list, and `HookExecutor` passes through directly to the inner executor -- zero overhead for the no-hooks case.

---

## Error Handling

- **Hook blocks a call:** `before_tool_call` returns `ToolResult(output="", error="Blocked: {reason}")`. Tool execution is skipped. After hooks still fire with the blocked result and `blocked=True`.
- **Hook raises exception (before):** Caught, logged as warning, treated as "allow" (fail open). Documented for future configurability.
- **Hook raises exception (after):** Caught, logged as warning, swallowed. Result already determined, nothing to change.
- **Log file write fails:** Caught within `log_tool_calls` hook. The hook's own error handling swallows the I/O error with a log warning. Tool execution is not affected.

---

## File Layout

```
src/signalagent/
  hooks/
    __init__.py           -- NEW: package init
    protocol.py           -- NEW: Hook protocol
    registry.py           -- NEW: HookRegistry
    executor.py           -- NEW: HookExecutor
    builtins/
      __init__.py         -- NEW: load_builtin_hook() mapping
      log_tool_calls.py   -- NEW: LogToolCallsHook

  core/
    models.py             -- MODIFIED: add HooksConfig, add hooks field to Profile

  runtime/
    bootstrap.py          -- MODIFIED: wire hook pipeline

tests/
  unit/
    hooks/
      __init__.py         -- NEW
      test_registry.py    -- NEW: HookRegistry tests
      test_executor.py    -- NEW: HookExecutor tests
      builtins/
        __init__.py       -- NEW
        test_log_tool_calls.py -- NEW: LogToolCallsHook tests (tmp_path)
    runtime/
      test_bootstrap.py   -- MODIFIED: add test with hooks active
```

---

## Done-When Criteria

**(a)** `Hook` protocol with `before_tool_call` (returns `ToolResult | None`) and `after_tool_call` (returns `None`)

**(b)** `HookRegistry` stores hooks and returns them via `get_all()`

**(c)** `HookExecutor` wraps any `ToolExecutor`, runs before hooks -> inner -> after hooks. After hooks always fire, including on blocked calls.

**(d)** `before_tool_call` blocks by returning a `ToolResult` with error. No argument mutation.

**(e)** Hook errors are caught and logged -- fail-open for now, documented for future configurability

**(f)** `HooksConfig` model with `active: list[str]`, added to `Profile`

**(g)** `log_tool_calls` built-in hook logs to JSONL, exercises both events

**(h)** Bootstrap wires hook pipeline: inner executor -> HookExecutor wrapping it

**(i)** `signal talk` works end-to-end with hooks active -- tool calls logged to JSONL

**(j)** Existing tests unaffected -- no-hooks case works identically (empty HookRegistry, HookExecutor passes through to inner)
