# Architecture

## System Overview

Signal is a multi-agent runtime. A user communicates with a **Prime Agent**, which routes tasks to specialist **micro-agents**. Each agent has persistent memory scoped to its domain. A **heartbeat daemon** triggers agents autonomously based on schedules, events, or conditions, without requiring a user prompt.

This is the target architecture. The current implementation covers Phase 3 (see below).

---

## Current Architecture (Phase 4a)

Phase 4a adds tool execution and an agentic loop to the Phase 3 multi-agent foundation. Agents can now call tools iteratively -- the runner calls AI, executes tool calls, feeds results back, and repeats until the AI returns a final text response or the iteration limit is reached.

**Components built:**

- `cli/` -- Typer-based CLI with `signal init`, `signal talk`, and `signal memory` commands
- `core/config` -- YAML-backed config, instance management, profile loading
- `core/models` -- Pydantic models: Profile, Memory, ToolCallRequest, ToolResult, ToolConfig, and supporting types
- `core/types` -- Enums: AgentType, AgentStatus, TaskStatus, TaskPriority, MessageType, MemoryType
- `core/protocols` -- Protocol definitions: AILayerProtocol, RunnerProtocol, ToolExecutor
- `ai/layer` -- LiteLLM wrapper, async completion with optional tools parameter, response normalization
- `runtime/executor` -- Single-turn executor with error boundary
- `runtime/runner` -- AgenticRunner: agentic loop with tool calling and two-tier iteration limits
- `runtime/bootstrap` -- Single wiring point connecting all components (including tool pipeline)
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
 |         +--> runtime/executor --> comms/bus
 |
 +--> memory/engine --> memory/storage --> core/models
                    --> memory/index   --> core/models
```

No module imports upward. `core/` has no runtime dependencies. `memory/` depends only on `core/`. `tools/` depends only on `core/`. `cli/` orchestrates everything.

### Tool Execution Architecture

The agentic loop is the core of Phase 4a. It enables agents to call tools iteratively until the task is complete.

**AgenticRunner loop:**

1. Caller provides messages, tool schemas, and iteration limit.
2. Runner calls AILayerProtocol.complete() with the messages and tool schemas.
3. If the AI response contains `tool_calls`, the runner executes each via ToolExecutor and appends the results as tool-role messages.
4. Steps 2-3 repeat until the AI returns a final text response (no tool calls) or the iteration limit is reached.
5. Runner returns a RunnerResult with the final content, iteration count, and whether it was truncated.

**ToolRegistry** maps tool names to their implementations (objects satisfying ToolProtocol). It produces LiteLLM-format tool schemas (function name, description, parameters as JSON Schema) for passing to the AI layer.

**ToolExecutor** is a callable protocol (`async (str, dict) -> ToolResult`). In production, bootstrap wires it to call through the registry. In tests, it can be replaced with a simple mock. This is the hook point for Phase 4b, where pre/post-execution hooks will wrap this callable.

**FileSystemTool** is the first built-in tool. It supports read, write, and list operations scoped to the instance workspace directory. Reads are size-capped to prevent token budget exhaustion.

**Two-tier iteration limits:** A global ceiling is defined in configuration (hard upper bound). Each agent can also specify a per-agent limit via ToolConfig.max_iterations. The runner enforces whichever is lower.

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

Phase 3 introduced the in-process MessageBus. Agents communicate via typed messages; they do not call each other directly. This keeps coupling low and makes the execution graph inspectable. Phase 4b will add hooks and plugins on top of the bus and tool execution infrastructure.

### State Machines for Lifecycles

Agent and task status transitions are modeled as enums with validated transitions. An agent cannot jump from `IDLE` to `COMPLETE` without passing through `RUNNING`. Invalid transitions raise `InstanceError`. This prevents silent state corruption.

### Pydantic for All Data Boundaries

Every external data structure -- configs, profiles, AI responses, task payloads -- is a Pydantic model with `extra="forbid"`. Unknown fields are rejected at parse time. This catches YAML typos, API changes, and incorrect test fixtures before they cause hard-to-trace bugs.
