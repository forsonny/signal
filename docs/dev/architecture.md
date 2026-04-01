# Architecture

## System Overview

Signal is a multi-agent runtime. A user communicates with a **Prime Agent**, which routes tasks to specialist **micro-agents**. Each agent has persistent memory scoped to its domain. A **heartbeat daemon** triggers agents autonomously based on schedules, events, or conditions, without requiring a user prompt.

This is the target architecture. The current implementation covers Phase 3 (see below).

---

## Current Architecture (Phase 3)

Phase 3 adds multi-agent routing to the Phase 2 memory foundation. User messages flow through Prime, get LLM-routed to micro-agents, and return results via the message bus.

**Components built:**

- `cli/` -- Typer-based CLI with `signal init`, `signal talk`, and `signal memory` commands
- `core/config` -- YAML-backed config, instance management, profile loading
- `core/models` -- Pydantic models: Profile, Memory, and supporting types
- `core/types` -- Enums: AgentType, AgentStatus, TaskStatus, TaskPriority, MessageType, MemoryType
- `ai/layer` -- LiteLLM wrapper, async completion, response normalization
- `runtime/executor` -- Single-turn executor with error boundary
- `memory/storage` -- Atomic markdown file I/O with YAML frontmatter
- `memory/index` -- Async SQLite metadata index with tag+recency scoring
- `memory/engine` -- Orchestrator tying storage and index together
- `agents/base` -- BaseAgent with template method for status management (BUSY/IDLE)
- `agents/host` -- AgentHost registry, wires agents to the message bus
- `agents/prime` -- PrimeAgent with LLM-based routing and direct handling fallback
- `agents/micro` -- MicroAgent with skill-based system prompt template
- `comms/bus` -- In-process MessageBus with talks_to enforcement and message logging
- `runtime/bootstrap` -- Single wiring point connecting all components

**Module dependency diagram:**

```
cli/ --> core/config --> core/models --> core/types
 |                         |
 +--> runtime/bootstrap --> agents/prime --> ai/layer --> LiteLLM
 |         |            --> agents/micro --> ai/layer
 |         |            --> agents/host  --> comms/bus
 |         +--> runtime/executor --> comms/bus
 |
 +--> memory/engine --> memory/storage --> core/models
                    --> memory/index   --> core/models
```

No module imports upward. `core/` has no runtime dependencies. `memory/` depends only on `core/`. `cli/` orchestrates everything.

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

The executor does not import `AILayer` directly. It depends on `AILayerProtocol`, a structural `typing.Protocol`. Any object that satisfies the protocol can be injected -- including mocks in tests. This keeps the runtime layer decoupled from the AI provider.

### Error Boundaries per Agent

Every agent execution is wrapped in a try/except. Exceptions are caught, logged, and converted to a structured error result. An unhandled exception inside an agent must never propagate up and crash the runtime process. This invariant holds even in Phase 1 with a single agent.

### Event-Driven Internals

Phase 3 introduced the in-process MessageBus. Agents communicate via typed messages; they do not call each other directly. This keeps coupling low and makes the execution graph inspectable. Phase 4 adds hooks and plugins on top of the bus infrastructure already in place.

### State Machines for Lifecycles

Agent and task status transitions are modeled as enums with validated transitions. An agent cannot jump from `IDLE` to `COMPLETE` without passing through `RUNNING`. Invalid transitions raise `InstanceError`. This prevents silent state corruption.

### Pydantic for All Data Boundaries

Every external data structure -- configs, profiles, AI responses, task payloads -- is a Pydantic model with `extra="forbid"`. Unknown fields are rejected at parse time. This catches YAML typos, API changes, and incorrect test fixtures before they cause hard-to-trace bugs.
