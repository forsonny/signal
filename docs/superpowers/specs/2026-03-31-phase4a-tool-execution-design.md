# Phase 4a: Tool Execution + Agentic Loop -- Design Spec

## Goal

Give micro-agents the ability to call tools. An agent receives a task, reasons about it, calls tools to gather information or take action, observes results, and iterates until it has a final answer. This transforms agents from single-shot LLM calls into agentic loops that can interact with the world.

## Architecture

Phase 4a adds three new packages and modifies four existing modules:

**New:**
- `core/protocols.py` -- AILayerProtocol (moved from runtime/executor.py), RunnerProtocol, ToolExecutor
- `tools/` -- Tool protocol, ToolRegistry, built-in file_system tool
- `runtime/runner.py` -- AgenticRunner (concrete implementation of RunnerProtocol)

**Modified:**
- `ai/layer.py` -- Optional `tools` param on `complete()`, `tool_calls` field on `AIResponse`
- `agents/micro.py` -- Delegates to RunnerProtocol, no direct AI reference
- `runtime/executor.py` -- Imports AILayerProtocol from core/protocols
- `runtime/bootstrap.py` -- Wires tool registry, executor callable, runners

### Data Flow

```
User -> Executor -> Bus -> PrimeAgent -> routes -> Bus -> MicroAgent
                                                            |
                                                      AgenticRunner
                                                       |         ^
                                                       v         |
                                                    AILayer    tool results
                                                   (w/ tools)    ^
                                                       |         |
                                                       v         |
                                                   tool_calls ---+
                                                       |
                                                       v
                                               ToolExecutor(name, args)
                                                       |
                                                       v
                                               registry.get(name).execute(**args)
                                                       |
                                                       v
                                                final text -> Message back to Prime
```

The runner loops until the LLM returns a final text response (no tool_calls) or the iteration limit is hit. The ToolExecutor is an injected callable -- in 4a it wraps registry lookup + execution; in 4b it gets replaced with a hook-aware version without changing the runner.

### Dependency Graph

```
core/protocols.py    -- AILayerProtocol, RunnerProtocol, ToolExecutor (depends on nothing)
core/models.py       -- ToolCallRequest, ToolResult, ToolConfig (depends on nothing)
tools/protocol.py    --> core/models (ToolResult)
tools/registry.py    --> tools/protocol
tools/builtins/*     --> tools/protocol, core/models
runtime/runner.py    --> core/protocols, core/models
agents/micro.py      --> core/protocols (RunnerProtocol)
runtime/bootstrap.py --> everything (wiring point)
```

No circular dependencies. Agents depend on abstractions in core/, runtime provides concrete implementations, bootstrap wires them together.

---

## Components

### 1. Core Protocols (core/protocols.py)

Moved and expanded from runtime/executor.py. All protocol types that agents depend on live here.

```python
@runtime_checkable
class AILayerProtocol(Protocol):
    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: list[dict] | None = None,
    ) -> Any: ...

class RunnerProtocol(Protocol):
    async def run(
        self,
        system_prompt: str,
        user_content: str,
    ) -> Any: ...

class ToolExecutor(Protocol):
    async def __call__(
        self, tool_name: str, arguments: dict
    ) -> Any: ...
```

### 2. Core Models (core/models.py additions)

**ToolCallRequest** -- what the LLM wants to do (on AIResponse):

```python
class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    arguments: dict[str, Any]
```

Named ToolCallRequest (not ToolCall) to avoid collision with the full execution record model planned for Phase 10 tracing/audit.

**ToolResult** -- what a tool execution produced:

```python
class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: str
    error: str | None = None
```

**ToolConfig** -- global tool execution settings:

```python
class ToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_iterations: int = 20
```

Added to SignalConfig as `tools: ToolConfig = Field(default_factory=ToolConfig)`.

### 3. AI Layer Changes (ai/layer.py)

`AILayer.complete()` gains an optional `tools` parameter:

```python
async def complete(
    self,
    messages: list[dict],
    model: Optional[str] = None,
    tools: list[dict] | None = None,
) -> AIResponse:
```

When `tools` is passed, LiteLLM includes them in the request. The response is parsed for tool_calls -- if present, they are normalized into `ToolCallRequest` objects on `AIResponse.tool_calls`. If no tool_calls, the list is empty.

`AIResponse` gains:

```python
tool_calls: list[ToolCallRequest] = Field(default_factory=list)
```

Existing callers that don't pass `tools` get identical behavior -- the field defaults to an empty list.

### 4. Tool Protocol (tools/protocol.py)

Every tool implements:

```python
class Tool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict: ...  # JSON Schema for the tool's arguments

    async def execute(self, **kwargs) -> ToolResult: ...
```

### 5. Tool Registry (tools/registry.py)

Lookup layer only. Maps tool names to implementations and produces LiteLLM-format schemas.

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None: ...
    def get(self, name: str) -> Tool | None: ...
    def get_schemas(self, names: list[str]) -> list[dict]: ...
```

`get_schemas()` returns full LiteLLM tool format:

```python
[
    {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }
]
```

The wrapping happens in one place (the registry), not in the runner.

### 6. Built-in file_system Tool (tools/builtins/file_system.py)

Single built-in tool for 4a. Scoped to the instance directory.

**Operations:** read, write, list.

**Security constraints:**
- All paths resolved relative to the instance directory root
- Path traversal check: resolved path must be under root, `..` that escapes is rejected
- No symlink following outside root
- Read capped at max_read_bytes (default 1MB); files exceeding the cap return truncated content with a note: `"[truncated at 1MB, file is {actual_size}]"`
- No destructive operations (delete, move, chmod). Agents can read context and write results.

**Parameters schema:**

```python
{
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["read", "write", "list"]},
        "path": {"type": "string", "description": "Relative path within workspace"},
        "content": {"type": "string", "description": "Content to write (write only)"},
    },
    "required": ["operation", "path"],
}
```

**Tool loading:** `tools/builtins/__init__.py` exports `load_builtin_tool(name: str, instance_dir: Path) -> Tool | None`. Maps `"file_system"` to `FileSystemTool(root=instance_dir)`. Returns None for unknown names (unimplemented tools silently skipped).

### 7. AgenticRunner (runtime/runner.py)

Concrete implementation of RunnerProtocol. Encapsulates the tool-calling loop.

```python
class AgenticRunner:
    def __init__(
        self,
        ai: AILayerProtocol,
        tool_executor: ToolExecutor,
        tool_schemas: list[dict],
        max_iterations: int,
    ) -> None: ...

    async def run(
        self,
        system_prompt: str,
        user_content: str,
    ) -> RunnerResult: ...
```

**Loop mechanics:**

1. Build initial messages: `[{"role": "system", ...}, {"role": "user", ...}]`
2. Call `ai.complete(messages, tools=tool_schemas if tool_schemas else None)`
3. If `response.tool_calls` is empty -- done, return final text
4. Append assistant message with tool calls to messages (LiteLLM input format):
   ```python
   messages.append({
       "role": "assistant",
       "tool_calls": [
           {
               "id": tc.id,
               "type": "function",
               "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
           }
           for tc in response.tool_calls
       ],
   })
   ```
5. For each `ToolCallRequest` in response.tool_calls:
   - Call `tool_executor(request.name, request.arguments)`
   - If executor raises an unexpected exception, catch it and convert to `ToolResult(output="", error=str(e))`
   - Append tool result message (must match tool_call_id from the request):
     ```python
     messages.append({
         "role": "tool",
         "tool_call_id": tc.id,
         "content": result.output if not result.error else f"Error: {result.error}",
     })
     ```
6. Increment iteration counter. If counter >= max_iterations, stop and return with truncated=True
7. Go to step 2

**Key behaviors:**
- Multiple tool calls per iteration: the LLM can return N tool calls in one response. All are executed sequentially, all results appended, one iteration counter increment per round trip.
- Tool errors never crash the loop: errors from ToolExecutor (both returned ToolResult.error and unexpected exceptions) are fed back to the LLM as tool result content. The agent sees the error and can retry, try a different tool, or give up.
- Zero-tool passthrough: when tool_schemas is empty, the LLM never returns tool_calls, so the loop exits on the first iteration. Same code path for all agents.

**RunnerResult:**

```python
class RunnerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str
    iterations: int
    tool_calls_made: int
    truncated: bool = False
```

### 8. MicroAgent Changes (agents/micro.py)

MicroAgent drops its direct `ai` reference. All LLM interaction goes through the runner.

```python
class MicroAgent(BaseAgent):
    def __init__(self, config: MicroAgentConfig, runner: RunnerProtocol) -> None:
        super().__init__(name=config.name, agent_type=AgentType.MICRO)
        self._config = config
        self._runner = runner
        self._system_prompt = self._build_system_prompt()

    async def _handle(self, message: Message) -> Message | None:
        result = await self._runner.run(
            system_prompt=self._system_prompt,
            user_content=message.content,
        )
        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=result.content,
            parent_id=message.id,
        )
```

### 9. MicroAgentConfig Changes (core/models.py)

New field for per-agent iteration limit:

```python
class MicroAgentConfig(BaseModel):
    # existing fields unchanged
    max_iterations: int = 10
```

At bootstrap, the per-agent limit is clamped: `min(micro_config.max_iterations, config.tools.max_iterations)`.

### 10. Bootstrap Changes (runtime/bootstrap.py)

Bootstrap wires the tool pipeline:

1. Create AILayer, MessageBus, AgentHost (unchanged)
2. Create ToolRegistry, load built-in tools from `profile.plugins.available`
3. Create ToolExecutor callable (wraps registry lookup + error handling)
4. Create and register PrimeAgent (unchanged, no tools)
5. For each micro-agent: resolve tool schemas from config.plugins, create AgenticRunner with clamped iteration limit, create MicroAgent with runner
6. Create Executor (unchanged)

The ToolExecutor callable handles tool-not-found (returns ToolResult with error) and unexpected exceptions (catches, converts to ToolResult with error). This logic lives in one place, not in the runner.

---

## Configuration

### config.yaml (instance)

```yaml
tools:
  max_iterations: 20  # global ceiling
```

### profile.yaml

```yaml
plugins:
  available: [file_system]

micro_agents:
  - name: researcher
    skill: "Research topics using workspace files"
    plugins: [file_system]
    max_iterations: 15  # clamped to global ceiling at bootstrap
```

---

## Error Handling

- **Tool not found:** ToolExecutor returns `ToolResult(output="", error="Unknown tool: {name}")`. Agent sees it as a failed tool call.
- **Tool execution error:** Tool raises exception, ToolExecutor catches and returns `ToolResult(output="", error=str(e))`. Agent sees the error.
- **Unexpected executor exception:** Runner catches any exception from executor, converts to `ToolResult(output="", error=str(e))`. Loop continues.
- **Iteration limit hit:** Runner stops, returns `RunnerResult(truncated=True)` with whatever content the LLM last produced.
- **Path traversal:** FileSystemTool rejects paths resolving outside root with `ToolResult(output="", error="Path outside workspace")`.
- **Read size exceeded:** FileSystemTool truncates content and returns `ToolResult(output="[content...][truncated at 1MB, file is 500MB]")`.

New error type in core/errors.py:

```python
class ToolExecutionError(SignalError):
    """Tool execution failed."""
```

---

## File Layout

```
src/signalagent/
  core/
    protocols.py          -- NEW: AILayerProtocol, RunnerProtocol, ToolExecutor
    models.py             -- MODIFIED: add ToolCallRequest, ToolResult, ToolConfig
    errors.py             -- MODIFIED: add ToolExecutionError

  ai/
    layer.py              -- MODIFIED: optional tools param, tool_calls on AIResponse

  tools/
    __init__.py           -- NEW: package init
    protocol.py           -- NEW: Tool protocol
    registry.py           -- NEW: ToolRegistry
    builtins/
      __init__.py         -- NEW: load_builtin_tool() mapping
      file_system.py      -- NEW: FileSystemTool

  runtime/
    runner.py             -- NEW: AgenticRunner
    executor.py           -- MODIFIED: import AILayerProtocol from core/protocols
    bootstrap.py          -- MODIFIED: wire tool pipeline

  agents/
    micro.py              -- MODIFIED: delegate to RunnerProtocol, drop ai reference

tests/
  unit/
    core/
      test_protocols.py   -- NEW: protocol compliance tests
    tools/
      __init__.py         -- NEW
      test_registry.py    -- NEW: ToolRegistry tests
      builtins/
        __init__.py       -- NEW
        test_file_system.py -- NEW: FileSystemTool tests (tmp_path)
    runtime/
      test_runner.py      -- NEW: AgenticRunner tests (mock AI + mock executor)
    agents/
      test_micro.py       -- MODIFIED: updated for runner-based MicroAgent
```

---

## Done-When Criteria

**(a)** `AILayer.complete()` accepts an optional `tools` parameter and returns `ToolCallRequest` objects on `AIResponse.tool_calls`

**(b)** `ToolRegistry` resolves tool names to implementations and produces LiteLLM-format schemas

**(c)** `AgenticRunner` loops: call AI with tools, execute tool calls via injected `ToolExecutor`, feed results back, repeat until final text or iteration limit

**(d)** `ToolExecutor` handles tool-not-found and execution errors as `ToolResult` errors fed back to the LLM, never crashing the loop

**(e)** `FileSystemTool` supports read (with size cap + truncation), write, and list -- all scoped to instance directory with path traversal protection

**(f)** Two-tier iteration limits: per-agent config clamped to global ceiling at bootstrap

**(g)** `MicroAgent` delegates to `RunnerProtocol` for all LLM interaction -- no direct `ai` reference

**(h)** `signal talk` works end-to-end: user message -> Prime routes -> micro-agent uses tool -> result flows back

**(i)** All protocols (`AILayerProtocol`, `RunnerProtocol`, `ToolExecutor`) live in `core/protocols.py` -- agents depend on abstractions, runtime provides implementations

**(j)** Multiple tool calls per iteration are handled -- the LLM can return N tool calls in one response, all executed sequentially, all results fed back before the next LLM call
