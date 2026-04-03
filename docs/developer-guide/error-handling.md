# Error Handling

## What you'll learn

- The `SignalError` exception hierarchy and when to use each subclass
- How error boundaries work at each layer of the runtime
- How the executor, runner, and hook executor handle failures
- Hook failure modes (fail-open vs fail-closed)

---

## Exception hierarchy

All Signal-specific exceptions inherit from `SignalError`. The hierarchy
is intentionally flat -- one level of specialization per concern boundary.

```
SignalError
    |
    +-- ConfigError          Config loading or validation failed
    |
    +-- AIError              LLM call failed, provider unavailable
    |
    +-- InstanceError        Instance init/start/stop failures
    |
    +-- MemoryStoreError     Memory storage, index, or retrieval failure
    |
    +-- RoutingError         Message routing failed (no match, talks_to violation)
    |
    +-- ToolExecutionError   Tool execute() encountered an unrecoverable error
```

Defined in `src/signalagent/core/errors.py`.

### When to use each exception

| Exception | Raise when | Caught by |
|---|---|---|
| `ConfigError` | YAML parse failure, missing config file, Pydantic validation error in config | CLI layer, shown to user |
| `AIError` | `litellm.acompletion` fails, tool call JSON parsing fails | Runner (feeds error to LLM), Prime (falls back to direct handling) |
| `InstanceError` | `create_instance` on existing dir, `find_instance` with no `.signal/` | CLI layer, shown to user |
| `MemoryStoreError` | Memory file missing/corrupt, index read failure | `MemoryEngine` (skips corrupt entries), agents (proceeds without context) |
| `RoutingError` | Unknown sender/recipient, `talks_to` violation | `Executor` (returns `ExecutorResult.error`) |
| `ToolExecutionError` | Tool hits an unrecoverable state | Runner (feeds error to LLM) |

### Catching broad vs narrow

```python
# Catch any Signal error
try:
    result = await executor.run(message)
except SignalError as e:
    log.error("Signal error: %s", e)

# Catch only routing issues
try:
    await bus.send(message)
except RoutingError as e:
    log.warning("Routing failed: %s", e)
```

---

## Error boundaries

### Executor boundary

The `Executor` is the outermost error boundary. It wraps the entire
message delivery chain in a try/except and returns `ExecutorResult`
with `error` and `error_type` set. It never raises to the caller.

```python
class Executor:
    async def run(self, user_message: str, session_id: str | None = None) -> ExecutorResult:
        try:
            response = await self._bus.send(message)
            # ... handle response
            return ExecutorResult(content=response.content)
        except Exception as e:
            logger.error("Executor error: %s", e, exc_info=True)
            return ExecutorResult(
                content="",
                error=str(e),
                error_type=type(e).__name__,
            )
```

This means the CLI and any external caller can always expect a result
object, never an unhandled exception.

### Runner boundary

The `AgenticRunner` catches exceptions raised by the tool executor
during each tool call. Errors are converted to `ToolResult(error=...)`
and fed back to the LLM as a tool response message:

```python
for tc in response.tool_calls:
    try:
        result = await self._tool_executor(tc.name, tc.arguments)
    except Exception as e:
        result = ToolResult(output="", error=str(e))

    if result.error:
        content = f"Error: {result.error}"
    else:
        content = result.output
    messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
```

This allows the LLM to see the error and decide how to proceed (retry,
try a different approach, or give up gracefully).

The runner also catches errors from the inner executor closure at
bootstrap, which handles unknown tools:

```python
async def inner_executor(tool_name: str, arguments: dict) -> ToolResult:
    tool = registry.get(tool_name)
    if tool is None:
        return ToolResult(output="", error=f"Unknown tool: {tool_name}")
    try:
        return await tool.execute(**arguments)
    except Exception as e:
        return ToolResult(output="", error=str(e))
```

### Agent boundary

`MicroAgent._handle()` catches runner exceptions and wraps them in a
result message:

```python
try:
    result = await self._runner.run(
        system_prompt=system_prompt,
        user_content=message.content,
    )
    content = result.content
except Exception as exc:
    error = exc
    content = f"Task failed: {exc}"
```

If a worktree was created before the failure, `take_result()` is still
called to harvest any partial file changes.

### Prime routing boundary

`PrimeAgent._route()` wraps the routing LLM call in a try/except. If
the routing call fails, it returns `None`, causing Prime to handle the
request directly:

```python
try:
    response = await self._ai.complete(messages=[...])
except Exception:
    logger.warning("Routing LLM call failed, falling back to direct handling")
    return None
```

Memory retrieval failures in both Prime and MicroAgent are also caught
and logged, with the agent proceeding without context.

---

## Hook failure handling

### Fail-open hooks

When a hook's `before_tool_call()` raises an exception:

1. The exception is logged as a warning.
2. The hook is skipped.
3. Processing continues with the next hook.
4. The tool call proceeds normally.

When a hook's `after_tool_call()` raises:

1. The exception is logged as a warning.
2. Processing continues with the next hook.

### Fail-closed hooks

When a hook has `fail_closed = True`:

1. If `before_tool_call()` raises, the tool call is blocked immediately.
   A `ToolResult(error="Policy hook error: ...")` is returned.
2. If `after_tool_call()` raises, it is logged as an error (not a
   warning), but does not change the already-computed result.

The `PolicyHook` is the only built-in fail-closed hook. It enforces
security policies, so a crash must block rather than silently allow.

### Detection mechanism

The `HookExecutor` checks for fail-closed via duck typing:

```python
if getattr(hook, 'fail_closed', False):
    return ToolResult(output="", error=f"Policy hook error: {e}")
```

To make your hook fail-closed, add:

```python
@property
def fail_closed(self) -> bool:
    return True
```

---

## Heartbeat error handling

The `HeartbeatScheduler` catches all exceptions during trigger evaluation
and dispatch:

- Evaluation errors are logged and skipped.
- Dispatch errors increment `consecutive_errors` on the trigger state.
- When `consecutive_errors >= error_threshold`, the trigger is disabled.

This prevents a broken trigger from blocking other triggers or crashing
the scheduler.

---

## Memory error handling

`MemoryEngine` operations have specific recovery strategies:

- **`store()`**: file is written first. If index upsert or embedding
  fails, the file is still on disk. `rebuild_index()` or
  `rebuild_embeddings()` can recover.
- **`search()`**: corrupt memory files are logged and skipped via
  `MemoryStoreError` handling in `_load_results()`.
- **`archive()` / `consolidate()`**: missing index entries or corrupt
  files are handled gracefully (no-op or skip).

### Embedding failures

If the embedding call fails during `store()`, the memory is stored
without a vector:

```python
try:
    vectors = await self._embedder.embed([memory.content])
    await self._index.store_embedding(memory.id, vectors[0])
except Exception:
    logger.warning("Embedding failed for %s, memory stored without vector", memory.id)
```

`rebuild_embeddings()` can backfill missing vectors later.

---

## Guidelines for new code

### Return errors from tools

Tools should catch exceptions internally and return
`ToolResult(output="", error=...)` rather than raising. This gives the
LLM a clean error message.

### Use the right exception class

If your error fits an existing subclass, use it. If it does not, raise
`SignalError` directly. Do not create new subclasses unless the error
represents a genuinely new concern boundary.

### Never crash the runtime

Agent-level errors must not propagate to the executor. Tool-level
errors must not crash the agent. Hook errors must not block the tool
(unless fail-closed). Each layer is responsible for containing its own
failures.

### Log at the boundary

Log errors where they are caught, not where they are raised. The
catching layer has the context to write a meaningful log message.

---

## Next steps

- [Architecture](architecture.md) -- error boundary locations in the system
- [Extending Hooks](extending-hooks.md) -- fail-open/fail-closed hook design
- [Testing](testing.md) -- testing error paths
- [Contributing](contributing.md) -- architectural rules
