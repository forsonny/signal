# Architecture

## What you'll learn

- How Signal's modules connect and depend on each other
- The request lifecycle from user input through Prime routing to agent execution
- Design principles that govern the codebase (async-first, protocol DI, error boundaries)
- How tool execution, hooks, memory, security, and worktrees fit together
- The heartbeat scheduler and session persistence model

---

## System overview

Signal is an async-first, multi-agent AI runtime. A single `bootstrap()` call
wires every subsystem together and returns three entry points: `Executor`,
`MessageBus`, and `AgentHost`.

```
User input
    |
    v
Executor          -- error boundary, session persistence
    |
    v
MessageBus        -- typed message delivery, talks_to enforcement
    |
    v
PrimeAgent        -- LLM routing or direct handling
    |
    v (routed task)
MicroAgent        -- skill prompt + agentic runner loop
    |
    v
AgenticRunner     -- LLM call -> tool call -> result -> repeat
    |
    v
WorktreeProxy     -- file-write isolation (PASSTHROUGH/ISOLATED state machine)
    |
    v
HookExecutor      -- before/after lifecycle around every tool call
    |
    v
ToolRegistry      -- name lookup, schema generation
    |
    v
Tool.execute()    -- FileSystemTool, SpawnSubAgentTool, etc.
```

---

## Module dependency diagram

The import graph is layered. `core/` depends on nothing.
Everything else can depend on `core/`. Higher layers compose lower ones;
no circular imports exist.

```
                        cli/
                         |
                    runtime/bootstrap
                   /    |    \      \
              runtime/  |   worktrees/  heartbeat/
             executor   |     proxy       scheduler
              runner    |     manager
                  \     |     manifest
                   \    |     fork
                    \   |   /
                  agents/        security/
                 prime micro       engine
                 host  base        audit
                 keeper            policy_hook
                    \     |       memory_filter
                     \    |      /
                   hooks/    memory/
                  executor    engine
                  protocol    index
                  registry    storage
                  builtins/   scoring
                     |        similarity
                     |        keeper
                     |        prompts
                   tools/       |
                  protocol    prompts/
                  registry     builder
                  builtins/    tokens
                        \     /
                        ai/
                       layer
                      embedding
                         |
                       core/
                      models
                     protocols
                      types
                      errors
                      config
                    constants
```

---

## Design principles

### Async everywhere

Every I/O operation is `async`. The bus delivers messages with `await`,
agents handle with `async def _handle`, the runner awaits each LLM call
and tool execution. The heartbeat scheduler runs as an `asyncio.Task`.

Sync operations exist only where justified: `SessionManager` (fast
file I/O), `MemoryStorage` (single-file reads), and `WorktreeManager`
(subprocess calls that block briefly).

### Protocol-based dependency injection

Agents never import concrete implementations. Six `@runtime_checkable`
protocols in `core/protocols.py` define the contracts:

| Protocol | Purpose | Concrete implementation |
|---|---|---|
| `AILayerProtocol` | LLM completion | `AILayer` |
| `RunnerProtocol` | Agentic loop | `AgenticRunner` |
| `ToolExecutor` | Tool invocation | `HookExecutor` (wraps registry lookup) |
| `MemoryReaderProtocol` | Memory search | `MemoryEngine` or `PolicyMemoryReader` |
| `EmbeddingProtocol` | Text embedding | `LiteLLMEmbedding` |
| `WorktreeProxyProtocol` | Worktree isolation | `WorktreeProxy` |

Bootstrap wires concrete instances into agents. Tests inject mocks
directly -- no monkey-patching required.

### Error boundaries

Each layer catches exceptions rather than letting them propagate:

- **Executor**: wraps the entire bus send in `try/except`, returns
  `ExecutorResult` with `error` set. Never raises to CLI.
- **AgenticRunner**: catches tool executor exceptions, converts to
  `ToolResult(error=...)`, feeds the error back to the LLM so it can
  recover.
- **HookExecutor**: catches hook crashes. Fail-open hooks are logged
  and skipped; fail-closed hooks block the call.
- **MicroAgent**: catches runner exceptions and returns error content
  via the bus. Worktree state is still checked even on failure.
- **PrimeAgent**: catches routing LLM failures and falls back to
  direct handling.
- **HeartbeatScheduler**: catches trigger evaluation and dispatch
  errors. Disables triggers after `error_threshold` consecutive failures.

### Event-driven via MessageBus

All inter-agent communication goes through the `MessageBus`. There are
no direct method calls between agents. The bus enforces `talks_to`
permission sets and maintains a chronological message log.

### State machines

The `WorktreeProxy` uses a `PASSTHROUGH -> ISOLATED` state machine.
On the first `file_system` write, it creates a worktree and redirects
all subsequent file operations there. `take_result()` harvests the
changes and resets to `PASSTHROUGH`.

Agent status follows a lifecycle: `CREATED -> ACTIVE -> BUSY/IDLE`.
`BaseAgent.handle()` manages BUSY/IDLE transitions automatically via
the template method pattern.

### Pydantic at boundaries

All cross-boundary data structures are Pydantic v2 `BaseModel` subclasses
with `extra="forbid"`. This includes `Profile`, `Message`, `Memory`,
`ToolResult`, `Turn`, `SessionSummary`, `AIResponse`, and all config
models. Strict schema enforcement catches malformed data at construction
time rather than at use time.

---

## Request lifecycle

### 1. Executor receives user input

`Executor.run(user_message, session_id?)` builds a `Message` with
`type=TASK, sender=USER_SENDER, recipient=PRIME_AGENT`. If a
`session_id` is provided, conversation history is loaded from the
`SessionManager` and attached to the message's `history` field.

### 2. MessageBus delivers to Prime

The bus auto-fills `message.id` and `message.created`, validates the
sender (virtual senders like `user` and `heartbeat` bypass registration
checks), validates the recipient is registered, checks `talks_to`
permissions, logs the message, and invokes the recipient's handler.

### 3. Prime routes or handles directly

`PrimeAgent._handle()` checks if any micro-agents are registered:

- **No micro-agents**: handles directly using its identity prompt.
- **With micro-agents**: makes an LLM routing call. The prompt lists
  each micro-agent's `name: skill` and asks the LLM to pick one or
  respond `NONE`. Routing failure (LLM error, unrecognized response)
  falls back to direct handling.
- **Routed**: sends a new `Message(type=TASK)` to the chosen
  micro-agent via the bus.

Memory context is injected into direct-handling prompts via
`build_system_prompt()`.

### 4. MicroAgent executes the task

`MicroAgent._handle()` acquires the worktree proxy lock (if present),
retrieves memories, builds a token-budgeted system prompt, and calls
`runner.run()`.

### 5. AgenticRunner loop

The runner enters a loop bounded by `max_iterations`:

1. Send accumulated messages to LLM via `AILayer.complete()`.
2. If the response has no tool calls, return `RunnerResult`.
3. Append the assistant message (with tool calls) to history.
4. Execute each tool call via the `ToolExecutor` callable.
5. Append tool results to history.
6. Loop to step 1.

If `max_iterations` is reached, the runner returns with `truncated=True`.

### 6. Response flows back

The micro-agent wraps the runner result in a `Message(type=RESULT)` and
returns it through the bus. Prime wraps that in its own result message.
The executor extracts the content and (if session-based) appends user
and assistant turns to the session file.

---

## Tool execution architecture

### Two-tier iteration limits

Each micro-agent has a `max_iterations` value from its profile config.
Bootstrap caps this at the global `config.tools.max_iterations`:

```python
agent_max = min(micro_config.max_iterations, global_max)
```

The per-agent limit allows different agents to have different loop
budgets. The global limit is a safety net.

### Executor chain

Tool calls pass through multiple layers:

```
AgenticRunner
    -> WorktreeProxy       (file-write isolation)
        -> HookExecutor    (before/after hooks)
            -> inner_executor (registry lookup + error handling)
                -> Tool.execute()
```

The `inner_executor` is a closure created at bootstrap. It looks up
the tool by name in the `ToolRegistry` and calls `tool.execute(**arguments)`.
Unknown tools return a `ToolResult(error="Unknown tool: ...")`.

### Tool protocol

Every tool implements four properties and one method:

```python
class Tool(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters(self) -> dict: ...
    async def execute(self, **kwargs) -> ToolResult: ...
```

The `ToolRegistry.get_schemas()` method generates LiteLLM-format
function definitions from these properties.

---

## Hook pipeline

### Lifecycle

The `HookExecutor` wraps any `ToolExecutor` with a before/after lifecycle:

1. **Before hooks** run in registration order. If any returns a
   `ToolResult`, the call is blocked -- no further before hooks run
   and the tool is not executed.
2. **Inner execution** runs only if no hook blocked the call.
3. **After hooks** always run, in registration order. They receive a
   `blocked` flag indicating whether a before hook intercepted.

### Fail-open vs fail-closed

- **Fail-open (default)**: if a hook's `before_tool_call` or
  `after_tool_call` raises an exception, it is logged and skipped.
- **Fail-closed**: if the hook has a `fail_closed` property that returns
  `True`, a crash in `before_tool_call` blocks the tool call with the
  error. The `PolicyHook` uses this mode.

Detection is via `getattr(hook, 'fail_closed', False)`.

### Built-in hooks

- `log_tool_calls`: JSONL logging of every tool call with timing.
- `policy` (PolicyHook): fail-closed tool access enforcement with
  audit trail. Registered automatically when security policies exist.

---

## Sub-agent spawning

Sub-agents are spawned through a tool (`spawn_sub_agent`), not through
a special API. This means hooks, policies, and logging all apply to
spawn operations transparently.

### Inheritance minus spawn

A sub-agent inherits its parent's tool schemas and tool executor chain
but does **not** get the `spawn_sub_agent` tool. This prevents infinite
recursive spawning.

The spawn mechanism works as follows:

1. Bootstrap creates a `run_sub` closure that instantiates a fresh
   `AgenticRunner` with the parent's tool schemas and executor.
2. A `SpawnSubAgentTool` wraps this closure.
3. A per-agent inner executor intercepts `spawn_sub_agent` calls and
   routes them to the spawn tool, while delegating everything else to
   the shared inner executor.
4. The spawn tool generates a system prompt from the `skill` parameter
   and calls `run_sub(system_prompt, task)`.

Sub-agents are ephemeral: they exist only for the duration of the tool
call and have no bus registration or memory access.

---

## Multi-agent architecture

### Prime routing

Prime uses an LLM call to classify which micro-agent should handle a
request. The routing prompt lists all registered micro-agents with their
`name` and `skill` fields. The LLM responds with exactly one agent
name or `NONE`.

Routing is case-insensitive. Unrecognized responses are treated as
`NONE` (direct handling fallback). Routing failure (exception) is also
a fallback to direct handling.

### Bus enforcement

The `MessageBus` enforces a directed permission graph:

- Each agent registers with a `talks_to` set: the names of agents it
  is allowed to message. `None` means unrestricted.
- `USER_SENDER` and `HEARTBEAT_SENDER` are virtual senders that bypass
  registration and permission checks.
- Unauthorized sends raise `RoutingError`.

### AgentHost

The `AgentHost` is a registry layer over the bus. It tracks agent
instances, handles status transitions (`ACTIVE` on register, `ARCHIVED`
on unregister), and provides `list_micro_agents()` for Prime's routing
decisions.

---

## Memory architecture

### Three layers

| Layer | Implementation | Purpose |
|---|---|---|
| Storage | `MemoryStorage` | Markdown files with YAML frontmatter on disk |
| Index | `MemoryIndex` | SQLite (aiosqlite) for fast search and metadata queries |
| Engine | `MemoryEngine` | Public API that orchestrates storage + index + embeddings |

File-first safety: `store()` writes the file before upserting the index.
If the index corrupts, `rebuild_index()` recovers from disk files.

### Scoring

Memory search ranks results using a composite score:

```
score = relevance * W_r + frequency * W_f + confidence * W_c - decay
```

Where decay is `days_since_access / decay_half_life_days`. The same
`compute_score()` function from `memory.scoring` is used by both the
tag-based index search and the semantic two-phase retrieval.

### Semantic search

When an embedder is configured (`profile.memory.embedding_model`):

1. The query text is embedded into a vector.
2. All stored embeddings are retrieved and ranked by cosine similarity.
3. Top candidates (3x limit) are re-scored using the composite formula.
4. Final results are returned sorted by score.

Embeddings are generated at `store()` time and can be backfilled via
`rebuild_embeddings()`.

### Memory lifecycle

Memories are versioned and append-only:

- **Create**: `create_memory()` generates a `Memory` with a unique ID,
  timestamps, and a v1 changelog entry.
- **Store**: writes to disk, upserts index, embeds content.
- **Archive**: sets `is_archived` in the index, appends a changelog
  entry. The file stays on disk. Reversible.
- **Consolidate**: creates a new memory with `consolidated_from` set,
  then archives each source with `superseded_by` set.
- **Delete**: removes from both disk and index. Permanent.

### MemoryKeeper agent

A purpose-built agent (not a `MicroAgent`) that runs on a heartbeat
schedule. It:

1. Finds groups of related memories by tag overlap (union-find).
2. Classifies each group via LLM: archive contradictions, consolidate
   duplicates, or skip.
3. Detects stale memories (old + low effective confidence) and archives
   them.

---

## Prompt construction

`build_system_prompt()` in `prompts/builder.py` is a pure function:

1. Counts tokens in the identity string using `count_tokens()`.
2. Calculates remaining budget: `context_window - identity_tokens - response_reserve`.
3. Iterates over pre-scored memories, adding each that fits within budget
   (greedy bin-packing).
4. Returns `identity + "## Context\n\n" + formatted memories`.

Token counting and context window lookup use `prompts/tokens.py`, which
wraps LiteLLM's token utilities.

---

## Session persistence

`SessionManager` stores conversations as JSONL files:

- One file per session: `{sessions_dir}/{session_id}.jsonl`.
- Each line is a serialized `Turn` (role + content + timestamp).
- Append-only writes, sequential reads.
- Corrupt lines are logged and skipped during load.

The `Executor` loads history before sending to Prime and appends
user + assistant turns on successful responses.

---

## Heartbeat scheduling

`HeartbeatScheduler` runs as a background `asyncio.Task`, ticking every
second. It evaluates two kinds of triggers:

### Clock triggers

Cron expressions matched against the current UTC minute. Each minute
is evaluated at most once (deduplication via `last_matched_minute`).

### File event triggers

Polling-based: a `FileChangeDetector` checks for file modifications at a
configurable interval. Changed file paths are injected into the trigger's
payload via `{changed_files}` substitution.

### Guards

Both trigger types support guards:

- `max_fires`: disable after N firings.
- `cooldown_seconds`: minimum time between firings.
- `error_threshold`: disable after N consecutive dispatch failures.

---

## Worktree isolation and fork execution

### WorktreeProxy

Each micro-agent gets a `WorktreeProxy` that wraps its tool executor.
The proxy operates as a state machine:

- **PASSTHROUGH**: all tool calls (including `file_system` reads) go
  through the normal executor chain.
- **ISOLATED**: on the first `file_system` write, a worktree is created
  (git branch or directory copy). All subsequent `file_system` calls are
  routed to a worktree-scoped `FileSystemTool`.

After the task completes, `take_result()` returns a `WorktreeResult`
with changed files and a diff, then resets to PASSTHROUGH.

### WorktreeManager

Handles the filesystem mechanics:

- **Git mode**: `git worktree add -b signal/worktree/<name>`.
- **Non-git mode**: full directory copy (respecting `IGNORE_DIRS`).
- Diff, changed-files, merge, and cleanup operations for both modes.

### Fork execution

The `ForkRunner` runs multiple tasks concurrently, each through the
`Executor`. Parallelism is bounded by an `asyncio.Semaphore` (default 2).
Worktree IDs are extracted from agent response text and associated with
changed files for the fork comparison UI.

---

## Security

### Policy engine

`PolicyEngine` evaluates declarative rules from the profile's `security`
section. Pure logic, no I/O:

- `check_tool_access(agent, tool_name)` returns a `PolicyDecision`
  (allowed + matching rule).
- `filter_memory_agents(agent)` returns the set of agent names an agent
  can read memories from, or `None` for unrestricted.

Agents without a policy entry get unrestricted access.

### PolicyHook

A fail-closed hook registered automatically when policies exist.
Blocks denied tool calls and logs `policy_denial` audit events.
Also logs every tool call (allowed or blocked) as a `tool_call` event.

### PolicyMemoryReader

Wraps the `MemoryEngine` (or any `MemoryReaderProtocol`) with
post-retrieval filtering. Memories from unauthorized agents are
silently removed and logged as `policy_denial` events.

The keyword `"shared"` in `allow_memory_read` matches memories with
`type=MemoryType.SHARED`.

### Audit logger

`AuditLogger` appends structured JSONL events to `{instance_dir}/logs/audit.jsonl`.
Each event has a timestamp, event type, agent name, and detail payload.

---

## Next steps

- [Project Structure](project-structure.md) -- full source tree with module descriptions
- [Error Handling](error-handling.md) -- exception hierarchy and boundary details
- [Extending Agents](extending-agents.md) -- adding custom micro-agents
- [Extending Tools](extending-tools.md) -- implementing custom tools
- [Extending Hooks](extending-hooks.md) -- writing custom hooks
