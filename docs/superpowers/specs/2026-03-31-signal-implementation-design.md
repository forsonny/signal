# Signal Implementation Design

**Date:** 2026-03-31
**Status:** Approved
**Scope:** Full build of Signal AI agent runtime framework in Python

---

## 1. Overview

Signal is a reusable AI agent runtime framework. It provides a fixed architecture -- Prime Agent, Micro-Agents, Memory System, Heartbeat Daemon -- and lets the user define what the instance becomes through a profile at setup time. One install can be a developer tool, a writing assistant, or a business automation platform.

This spec covers the full implementation: project structure, build order, data models, and architecture patterns.

## 2. Language & Tooling

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python | LiteLLM native, fastest AI ecosystem, asyncio for concurrency |
| Package name | `signalagent` | Avoids shadowing Python stdlib `signal` module. CLI binary is still `signal`. |
| Package manager | uv | Fastest resolver, modern lockfile, handles venvs |
| Deployment | Local + Docker | Works as a Python process for dev, containerized for production |
| Heartbeat daemon | Python first | Rewrite to Rust/Go later if reliability/footprint demands it |

## 3. Project Structure

```
signalagent/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── src/
│   └── signalagent/
│       ├── __init__.py
│       ├── core/               # Data models, config, types, constants
│       ├── cli/                # Typer CLI, all command groups
│       ├── runtime/            # Agent host, task executor, concurrency
│       ├── agents/             # Prime, micro-agent framework, sub-agents
│       ├── memory/             # Storage, index, retrieval, keeper
│       ├── ai/                 # LiteLLM, model routing, cost tracking
│       ├── comms/              # Message bus, routing, permissions
│       ├── heartbeat/          # Trigger engine, scheduling, guards
│       ├── tools/              # Tool registry, execution pipeline, hooks
│       ├── plugins/            # Plugin framework + built-in plugins
│       │   ├── file_system/
│       │   ├── git/
│       │   ├── bash/
│       │   └── web_search/
│       ├── sessions/           # Session lifecycle, persistence
│       ├── conversation/       # Threads, reference resolution, intent
│       ├── worktrees/          # Git worktree management
│       ├── forks/              # Fork management
│       ├── prompt/             # Prompt construction, token budgeting
│       └── safety/             # Policy engine, security, privacy, logging
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── profiles/
│   ├── devtools.yaml
│   ├── writer.yaml
│   ├── business.yaml
│   └── blank.yaml
└── docs/
```

## 4. Dependencies

| Concern | Library | Phase |
|---------|---------|-------|
| Data models | Pydantic v2 | 1 |
| Async runtime | asyncio | 1 |
| LLM access | LiteLLM | 1 |
| CLI | Typer + Rich | 1 |
| Database | aiosqlite | 1 |
| HTTP | httpx | 1 |
| MCP | mcp SDK | 4 |
| File watching | watchdog | 7 |
| Testing | pytest + pytest-asyncio | 1 |
| Embeddings | fastembed or API-based (optional) | 9 |

## 5. Build Order (Approach B: Minimal Loop, Then Expand)

Each phase produces a working, testable result. Each gets its own spec, plan, and implementation cycle.

### Phase Dependency Graph

```
Phase 1 (Skeleton)
    |
Phase 2 (Memory)
    |
Phase 3 (Multi-Agent)
   / \
  /   \
Phase 4    Phase 5
(Tools +   (Prompt
 Hooks)    Construction)
  \       /
   \     /
  Phase 6
  (Sessions +
   Conversation)
   /       \
  /         \
Phase 7    Phase 8
(Heartbeat) (Worktrees
             + Forks)
  \         /
   \       /
  Phase 9
  (Memory Advanced)
      |
  Phase 10
  (Safety + Docker
   + Full CLI)
```

### Phase 1: Skeleton

**Delivers:** `signal init --profile blank` + `signal talk "hello"` works.

**Modules:** `core` (config, models), `ai` (LiteLLM minimal), `cli` (init + talk), `runtime` (single-agent executor)

**Done when:**
- `signal init` creates an instance directory with config
- `signal talk "hello"` sends to LLM, returns response
- Config loads from YAML profile
- Pydantic models validate all data boundaries

### Phase 2: Memory Foundation

**Delivers:** Agent remembers things between tasks.

**Modules:** `memory` (atomic file storage, SQLite index, basic tag-match retrieval)

**Done when:**
- Memories written as atomic markdown files with frontmatter
- SQLite index stores metadata for fast lookup
- Basic retrieval by tags + recency scoring
- `signal memory search` and `signal memory inspect` work
- Memories survive restarts

### Phase 3: Multi-Agent

**Delivers:** Prime routes tasks to micro-agents.

**Modules:** `agents` (Prime, micro framework), `comms` (message bus, routing), `runtime` (multi-agent host)

**Done when:**
- Agent host manages multiple agents as stateful objects
- Message bus routes messages with `talks_to` enforcement
- Prime receives user input, delegates to appropriate micro-agent
- Profile loading creates the right agent roster
- Results flow back through Prime to user

### Phase 4: Tool Execution + Hooks

**Delivers:** Agents use tools, plugins intercept and guard actions.

**Modules:** `tools` (registry, execution, hooks), `plugins` (framework + file_system, git, bash), `agents` (sub-agents)

**Done when:**
- Full agentic loop: prompt -> LLM -> tool_call -> execute -> loop
- Plugin framework loads and sandboxes plugins
- Built-in plugins: file_system, git, bash
- MCP server integration via mcp SDK
- Sub-agent spawning and lifecycle
- `before_tool_call` / `after_tool_call` hooks intercept every tool execution
- Hook system supports block, modify, and log actions

### Phase 5: Prompt Construction

**Delivers:** Smart context assembly with token budgeting.

**Modules:** `prompt` (construction pipeline, budget management)

**Done when:**
- Token budget calculation per model context window
- 5-section prompt assembly (system, agent context, memory, active, input)
- Three-stage memory retrieval funnel (index scan -> relevance score -> budget-aware load)
- Priority-based overflow trimming
- Memory formatted with type tags and confidence scores

### Phase 6: Sessions + Conversation

**Delivers:** Stateful multi-turn interaction.

**Modules:** `sessions`, `conversation`, `cli` (interactive mode)

**Done when:**
- Session lifecycle: create, active, paused, resumed, completed, expired
- `signal talk` opens interactive session with streaming
- `signal talk --continue` resumes last session with context
- Conversation threads track multiple topics
- Intent classification routes messages correctly
- Reference resolution handles pronouns and implicit references
- Sliding window + running summary for long conversations
- Session persistence to disk (history.jsonl, session.yaml)

### Phase 7: Heartbeat Daemon

**Delivers:** Autonomous agent triggers without user present.

**Modules:** `heartbeat`

**Done when:**
- Clock triggers (cron expressions)
- Event triggers (file watch via watchdog, webhook endpoint, API polling)
- Condition triggers (threshold monitors)
- Dynamic trigger registration from agents at runtime
- Priority queue for trigger dispatch
- Safety guards: cooldown, debounce, dedup, rate limit, circuit breaker
- Trigger persistence across restarts
- `signal heartbeat status`, `signal heartbeat triggers`, `signal heartbeat history`

### Phase 8: Worktrees + Forks

**Delivers:** Isolated agent workspaces and speculative execution.

**Modules:** `worktrees`, `forks`

**Done when:**
- Git worktree creation for agent file changes
- Copy-based fallback for non-git workspaces
- Worktree lifecycle: create, active, review, merge, discard, cleanup
- Task forks: same task, multiple approaches in parallel
- Conversation forks: branch conversation direction
- Agent forks: clone agent + memory for experimentation
- Fork comparison and resolution (pick, combine, discard)
- `signal worktree list/diff/merge/discard`
- `signal fork create/compare/merge/discard`

### Phase 9: Memory Advanced

**Delivers:** Self-maintaining memory system.

**Modules:** `memory` (keeper agent, anti-corruption, lifecycle, embeddings)

**Done when:**
- Memory Keeper runs as a real micro-agent with its own memory
- Anti-corruption pipeline: detect contradictions, resolve (confirm/update/supersede/coexist/reject)
- Consolidation merges similar memories into stronger ones
- Decay scoring with configurable half-lives per memory type
- Garbage collection archives stale memories
- Vector embeddings (optional dep: fastembed or API) for semantic retrieval
- Escalation to Prime for unresolvable conflicts
- `signal memory gc`, `signal memory stats`

### Phase 10: Safety + Docker + Full CLI

**Delivers:** Production-ready system.

**Modules:** `safety`, `cli` (complete), Docker

**Done when:**
- Policy engine evaluates all actions (allow/deny/allow-with-conditions)
- Security rules enforce plugin permissions, network boundaries, command sandboxing
- Privacy filters control what data reaches LLM providers
- Data classifier tags sensitive content
- Immutable audit trail logs every decision
- Structured logging with JSON formatter
- Docker image + docker-compose (instance per container, volume-backed data)
- All remaining CLI commands (~50+ total across all command groups)
- Built-in profiles (devtools, writer, business, blank) fully functional
- Provider management CLI commands

## 6. Core Data Models

Ten first-class Pydantic types shared across all modules:

### Agent
```
Agent(id, name, type, status, skill, talks_to, plugins,
      mcp_servers, scripts, memory_path, task_queue, config)
```
Represents Prime, micro-agents, Memory Keeper, and sub-agents. Status is an enum with validated transitions (created, active, idle, busy, waiting, killed, archived).

### Task
```
Task(id, agent, status, priority, source, from_agent,
     session_id, instruction, context, execution, limits, result)
```
Flows through the system from creation to archival. Priority enum: CRITICAL, HIGH, NORMAL, LOW, IDLE.

### Message
```
Message(id, from_agent, to_agent, type, priority,
        payload, timestamp, conversation_id, blocking)
```
Standard format for all inter-agent communication. Types: task, result, request, response, escalation, spawn, report, trigger, memory_write.

### Memory
```
Memory(id, agent, type, tags, content, confidence, version,
       created, updated, accessed, access_count,
       changelog, supersedes, superseded_by, consolidated_from)
```
Atomic unit of knowledge. Types: identity, learning, pattern, outcome, context, shared.

### SignalConfig
```
SignalConfig(profile, runtime, ai, sessions, conversation,
            heartbeat, worktrees, forks, safety)
```
Top-level configuration loaded from YAML. Nested Pydantic models for each subsystem.

### Profile
```
Profile(name, description, version, author, prime,
        micro_agents, plugins, heartbeat)
```
YAML manifest defining what an instance becomes. Immutable after init (runtime changes persist separately).

### Session
```
Session(id, type, status, created, last_active,
        conversation, agents_involved, artifacts, pending,
        parent_session, child_sessions)
```
Bounded interaction period. Types: interactive, background, task.

### Trigger
```
Trigger(id, type, target, context, priority, config,
        cooldown, debounce, rate_limit, circuit_breaker,
        is_dynamic, one_shot)
```
Heartbeat trigger definition. Types: clock, event (file_watch, webhook, api_poll, email_poll, internal), condition.

### ToolCall
```
ToolCall(id, tool_name, source, agent, task_id, arguments,
         status, result, error, duration_ms, trace_id, span_id)
```
First-class type for every tool invocation. Flows through the execution pipeline, hooks intercept it, audit logs record it, cost tracking counts it.

### ConversationThread
```
ConversationThread(id, session_id, topic, status, agents,
                   thread_context, messages, artifacts)
```
Tracks a topic within a session. Supports cross-thread references and thread-aware routing.

## 7. Architecture Patterns

### Async Everywhere
The runtime is a single `asyncio` event loop. Agent task execution, LLM calls, tool execution, message passing, and heartbeat dispatch are all coroutines. The worker pool is an `asyncio.Semaphore`-bounded set of tasks, not OS threads.

### Dependency Injection
Runtime components are instantiated at startup and injected:
```
Runtime(
    config: SignalConfig,
    ai: AILayer,
    memory: MemoryEngine,
    bus: MessageBus,
    tools: ToolExecutor,
    agents: AgentHost,
    heartbeat: HeartbeatDaemon,
)
```
No global singletons. Any component can be swapped for a mock in tests.

### Event-Driven Internals
The message bus is the backbone. Agent-to-agent communication, task delegation, memory writes, and trigger dispatch all flow as `Message` objects through the bus. The bus enforces `talks_to` permissions and handles async delivery.

### State Machines for Lifecycles
`Agent`, `Task`, `Session`, and `Trigger` all have explicit status enums with validated transitions. Invalid transitions raise errors. No ad-hoc string states.

### Repository Pattern for Persistence
SQLite access goes through thin repository classes (`TaskRepo`, `SessionRepo`, `MemoryIndex`). Async via `aiosqlite`. Business logic never touches raw SQL.

### Plugin Isolation
Plugins are loaded dynamically, declare capabilities and permissions, and execute in sandboxed contexts. An agent's tool set is assembled at task time from its assigned plugins + MCP servers + scripts + built-ins.

### Error Boundaries Per Agent
Each agent task runs in its own try/except scope. One agent's failure never crashes the runtime or poisons another agent's execution. The task executor catches, logs, and routes errors to the error policy. The event loop and other agents keep running unconditionally.

### Hook Pipeline
Every tool call passes through `before_tool_call` and `after_tool_call` hooks. Hooks can block, modify, or log actions. This provides safety guardrails from the moment agents start acting on the world (Phase 4).

## 8. Design Reference

The full design docs live in `docs/` (moved from the current top-level directory structure). These serve as the living spec that each phase implements against:

- `overview/architecture.md` -- system diagram, component summary, design principles
- `runtime/runtime.md` -- execution engine, concurrency, task lifecycle
- `prime-agent/prime-agent.md` -- routing, synthesis, user identity
- `micro-agents/micro-agents.md` -- specialists, communication, improvement
- `memory-system/` -- storage, index, retrieval, anti-corruption, lifecycle, keeper
- `heartbeat-daemon/heartbeat-daemon.md` -- triggers, scheduling, safety
- `cli/cli.md` -- full command reference
- `profile-system/profile-system.md` -- YAML manifests, example profiles
- `communication/communication.md` -- message bus, routing, permissions
- `ai-layer/ai-layer.md` -- providers, routing, cost tracking
- `plugin-system/plugin-system.md` -- sandboxed integrations
- `tool-system/` -- registry, execution, hooks, MCP, scripts
- `sessions/sessions.md` -- lifecycle, persistence, resumption
- `conversation/conversation.md` -- threads, intent, reference resolution
- `worktrees/worktrees.md` -- isolated workspaces
- `forks/forks.md` -- speculative execution
- `prompt-construction/` -- token budgeting, assembly pipeline
- `safety/` -- security, privacy, observability, error policy
