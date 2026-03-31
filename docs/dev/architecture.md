# Architecture

## System Overview

Signal is a multi-agent runtime. A user communicates with a **Prime Agent**, which routes tasks to specialist **micro-agents**. Each agent has persistent memory scoped to its domain. A **heartbeat daemon** triggers agents autonomously based on schedules, events, or conditions, without requiring a user prompt.

This is the target architecture. The current implementation covers Phase 1 only (see below).

---

## Phase 1 Architecture (What Exists Now)

Phase 1 is a single-agent skeleton: one executor, one AI layer, one CLI, one config system.

There is no multi-agent routing, no persistent memory, and no heartbeat daemon. These are Phase 2+ concerns.

**Components built:**

- `cli/` -- Typer-based CLI with `signal init` and `signal talk` commands
- `core/config` -- YAML-backed config, instance management, profile loading
- `core/models` -- Pydantic models for all data structures
- `ai/layer` -- LiteLLM wrapper, async completion, response normalization
- `runtime/executor` -- Single-turn executor with error boundary

**Module dependency diagram:**

```
cli/ --> core/config --> core/models
 |                         |
 +--> runtime/executor --> ai/layer --> LiteLLM
```

No module imports upward. `core/` has no runtime dependencies. `ai/` depends only on `core/`. `runtime/` depends on `core/` and `ai/` via Protocol. `cli/` orchestrates everything.

---

## Key Design Principles

### Async Everywhere

All I/O is `async`/`await` on a single `asyncio` event loop. Threads are not used. This ensures LLM calls, file I/O, and agent communication never block each other. CLI commands that are async use a synchronous bridge (`asyncio.run`) as the Typer entry point.

### Dependency Injection via Protocol

The executor does not import `AILayer` directly. It depends on `AILayerProtocol`, a structural `typing.Protocol`. Any object that satisfies the protocol can be injected -- including mocks in tests. This keeps the runtime layer decoupled from the AI provider.

### Error Boundaries per Agent

Every agent execution is wrapped in a try/except. Exceptions are caught, logged, and converted to a structured error result. An unhandled exception inside an agent must never propagate up and crash the runtime process. This invariant holds even in Phase 1 with a single agent.

### Event-Driven Internals (Phase 3+)

From Phase 3, inter-agent communication will use an internal message bus. Agents publish and subscribe to typed messages; they do not call each other directly. This keeps coupling low and makes the execution graph inspectable. Phase 1 has no bus -- the executor calls the AI layer directly.

### State Machines for Lifecycles

Agent and task status transitions are modeled as enums with validated transitions. An agent cannot jump from `IDLE` to `COMPLETE` without passing through `RUNNING`. Invalid transitions raise `InstanceError`. This prevents silent state corruption.

### Pydantic for All Data Boundaries

Every external data structure -- configs, profiles, AI responses, task payloads -- is a Pydantic model with `extra="forbid"`. Unknown fields are rejected at parse time. This catches YAML typos, API changes, and incorrect test fixtures before they cause hard-to-trace bugs.
