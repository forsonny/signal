# Architecture

## System Overview

Signal is a multi-agent runtime. A user communicates with a **Prime Agent**, which routes tasks to specialist **micro-agents**. Each agent has persistent memory scoped to its domain. A **heartbeat daemon** triggers agents autonomously based on schedules, events, or conditions, without requiring a user prompt.

This is the target architecture. The current implementation covers Phase 3 (see below).

---

## Current Architecture (Phase 4c)

Phase 4c adds sub-agent spawning. Micro-agents marked with `can_spawn_subs` can delegate work to ephemeral sub-agents via a tool call. The hook pipeline from Phase 4b and the agentic loop from Phase 4a continue unchanged underneath.

**Components built:**

- `cli/` -- Typer-based CLI with `signal init`, `signal talk`, and `signal memory` commands
- `core/config` -- YAML-backed config, instance management, profile loading
- `core/models` -- Pydantic models: Profile, Memory, ToolCallRequest, ToolResult, ToolConfig, and supporting types
- `core/types` -- Enums: AgentType, AgentStatus, TaskStatus, TaskPriority, MessageType, MemoryType
- `core/protocols` -- Protocol definitions: AILayerProtocol, RunnerProtocol, ToolExecutor
- `ai/layer` -- LiteLLM wrapper, async completion with optional tools parameter, response normalization
- `runtime/executor` -- Single-turn executor with error boundary
- `runtime/runner` -- AgenticRunner: agentic loop with tool calling and two-tier iteration limits
- `runtime/bootstrap` -- Single wiring point connecting all components (including tool pipeline and hook pipeline)
- `memory/storage` -- Atomic markdown file I/O with YAML frontmatter
- `memory/index` -- Async SQLite metadata index with tag+recency scoring
- `memory/engine` -- Orchestrator tying storage and index together
- `agents/base` -- BaseAgent with template method for status management (BUSY/IDLE)
- `agents/host` -- AgentHost registry, wires agents to the message bus
- `agents/prime` -- PrimeAgent with LLM-based routing and direct handling fallback
- `agents/micro` -- MicroAgent with skill-based system prompt, delegates to RunnerProtocol
- `comms/bus` -- In-process MessageBus with talks_to enforcement and message logging
- `tools/protocol` -- ToolProtocol defining the interface all tools implement
- `tools/registry` -- ToolRegistry for name-to-implementation lookup, LiteLLM-format schema generation
- `tools/builtins/file_system` -- FileSystemTool: read/write/list, scoped to workspace, size-capped reads
- `hooks/protocol` -- Hook protocol: before_tool_call (block/allow) and after_tool_call (observe)
- `hooks/registry` -- HookRegistry: manages active hooks by name
- `hooks/executor` -- HookExecutor: wraps inner ToolExecutor with before/after lifecycle
- `hooks/builtins/log_tool_calls` -- LogToolCallsHook: JSONL logging with timing and blocked status
- `tools/builtins/spawn_sub_agent` -- SpawnSubAgentTool: ephemeral sub-agent delegation via tool call

**Module dependency diagram:**

```
cli/ --> core/config --> core/models --> core/types
 |                         |
 +--> runtime/bootstrap --> agents/prime --> ai/layer --> LiteLLM
 |         |            --> agents/micro --> core/protocols (RunnerProtocol)
 |         |            --> agents/host  --> comms/bus
 |         |            --> runtime/runner --> core/protocols (AILayerProtocol, ToolExecutor)
 |         |            --> tools/registry --> tools/protocol
 |         |            --> tools/builtins/file_system
 |         |            --> hooks/executor --> hooks/registry --> hooks/protocol
 |         |            --> hooks/builtins/log_tool_calls
 |         |            --> tools/builtins/spawn_sub_agent
 |         +--> runtime/executor --> comms/bus
 |
 +--> memory/engine --> memory/storage --> core/models
                    --> memory/index   --> core/models
```

No module imports upward. `core/` has no runtime dependencies. `memory/` depends only on `core/`. `tools/` depends only on `core/`. `hooks/` depends only on `core/`. `cli/` orchestrates everything.

### Tool Execution Architecture

The agentic loop is the core of Phase 4a. It enables agents to call tools iteratively until the task is complete.

**AgenticRunner loop:**

1. Caller provides messages, tool schemas, and iteration limit.
2. Runner calls AILayerProtocol.complete() with the messages and tool schemas.
3. If the AI response contains `tool_calls`, the runner executes each via ToolExecutor and appends the results as tool-role messages.
4. Steps 2-3 repeat until the AI returns a final text response (no tool calls) or the iteration limit is reached.
5. Runner returns a RunnerResult with the final content, iteration count, and whether it was truncated.

**ToolRegistry** maps tool names to their implementations (objects satisfying ToolProtocol). It produces LiteLLM-format tool schemas (function name, description, parameters as JSON Schema) for passing to the AI layer.

**ToolExecutor** is a callable protocol (`async (str, dict) -> ToolResult`). In production, bootstrap wires it to call through the registry. In tests, it can be replaced with a simple mock.

**FileSystemTool** is the first built-in tool. It supports read, write, and list operations scoped to the instance workspace directory. Reads are size-capped to prevent token budget exhaustion.

**Two-tier iteration limits:** A global ceiling is defined in configuration (hard upper bound). Each agent can also specify a per-agent limit via ToolConfig.max_iterations. The runner enforces whichever is lower.

### Hook Pipeline

HookExecutor wraps the inner ToolExecutor with a before/after lifecycle. Bootstrap wires the pipeline as: inner executor (registry call) -> HookExecutor -> AgenticRunner.

**Before hooks** run before the tool executes. Each hook's `before_tool_call` returns `None` to allow the call or a `ToolResult` with an error to block it. If any before hook blocks, the tool is not executed and the blocking result is returned immediately.

**After hooks** run after the tool executes (or after a block). Every registered hook's `after_tool_call` fires, including on blocked calls -- it receives a `blocked` flag so hooks can distinguish blocked from executed calls.

**Fail-open policy:** If a hook raises an exception during either phase, the error is logged and the hook is skipped. The tool call proceeds. This is documented for future configurability (fail-closed mode).

**HookRegistry** manages the active hook set. Hooks are registered by name and looked up from the profile's `hooks.active` list. This makes hooks instance-wide and profile-configurable.

**LogToolCallsHook** is the first built-in hook. It writes JSONL entries for every tool call, including tool name, arguments, result, timing (duration), and blocked status.

### Sub-Agent Spawning

`spawn_sub_agent` is a tool call, not a new mechanism. A micro-agent with `can_spawn_subs` enabled gets the SpawnSubAgentTool registered in its tool set. When invoked, the tool creates an ephemeral sub-agent with a spawn-execute-return-destroy lifecycle.

**Ephemeral lifecycle:** The parent agent calls `spawn_sub_agent` with a task and optional sub-agent name. The tool creates a sub-agent, runs it to completion via the runner factory, collects the result, and destroys the sub-agent. The parent receives the result as a normal tool output.

**Tool inheritance:** Sub-agents inherit all of the parent's tools minus `spawn_sub_agent` itself. This prevents recursive spawning -- sub-agents cannot spawn further sub-agents.

**Per-agent executor:** Bootstrap creates a per-agent executor for each spawning agent. The per-agent executor intercepts `spawn_sub_agent` calls and routes them to SpawnSubAgentTool. Regular tool calls pass through to the shared executor (including hooks). This keeps the hook pipeline intact for all non-spawn tool calls.

**Fully hooked sub-agent tool calls:** Sub-agent tool calls go through the same hook pipeline as parent tool calls. The shared executor (with hooks) is passed to the sub-agent's runner, so before/after hooks fire on every sub-agent tool invocation.

### Multi-Agent Architecture

PrimeAgent receives user messages via the bus, makes an LLM routing call, dispatches to the matched micro-agent or handles directly if no match. MessageBus enforces talks_to permissions -- an agent can only send to agents listed in its talks_to set, preventing accidental cross-agent coupling. AgentHost tracks registered agents and their status, providing a lookup table for routing decisions.

### Memory Architecture

The memory system uses three layers:

- **MemoryStorage** -- Reads/writes Memory objects as markdown files with YAML frontmatter. Each memory is one file. Path routing: shared memories go to `shared/`, prime memories to `prime/{type}/`, micro-agent memories to `micro/{agent}/{type}/`. Writes are atomic via temp file + `os.replace()`.
- **MemoryIndex** -- Async SQLite index storing metadata only (never content). Tags stored as JSON, queried via `json_each()`. Search results are scored in Python: tag overlap (40%) + recency (30%) + access frequency (20%) + confidence (10%).
- **MemoryEngine** -- Orchestrates storage and index. Provides the public API: `create_memory()`, `store()`, `search()`, `inspect()`, `delete()`, `rebuild_index()`. File-first-then-index write ordering for crash safety.

---

## Key Design Principles

### Async Everywhere

All I/O is `async`/`await` on a single `asyncio` event loop. Threads are not used. This ensures LLM calls, file I/O, and agent communication never block each other. CLI commands that are async use a synchronous bridge (`asyncio.run`) as the Typer entry point.

### Dependency Injection via Protocol

The executor does not import `AILayer` directly. It depends on `AILayerProtocol`, a structural `typing.Protocol` defined in `core/protocols`. Any object that satisfies the protocol can be injected -- including mocks in tests. This keeps the runtime layer decoupled from the AI provider. The same principle applies to `RunnerProtocol` (used by MicroAgent) and `ToolExecutor` (used by AgenticRunner).

### Error Boundaries per Agent

Every agent execution is wrapped in a try/except. Exceptions are caught, logged, and converted to a structured error result. An unhandled exception inside an agent must never propagate up and crash the runtime process. This invariant holds even in Phase 1 with a single agent.

### Event-Driven Internals

Phase 3 introduced the in-process MessageBus. Agents communicate via typed messages; they do not call each other directly. This keeps coupling low and makes the execution graph inspectable. Phase 4b added a hook pipeline that wraps tool execution with before/after lifecycle events, extending the event-driven model to tool calls. Phase 4c added sub-agent spawning as a tool call, keeping delegation within the existing tool execution model.

### State Machines for Lifecycles

Agent and task status transitions are modeled as enums with validated transitions. An agent cannot jump from `IDLE` to `COMPLETE` without passing through `RUNNING`. Invalid transitions raise `InstanceError`. This prevents silent state corruption.

### Pydantic for All Data Boundaries

Every external data structure -- configs, profiles, AI responses, task payloads -- is a Pydantic model with `extra="forbid"`. Unknown fields are rejected at parse time. This catches YAML typos, API changes, and incorrect test fixtures before they cause hard-to-trace bugs.
