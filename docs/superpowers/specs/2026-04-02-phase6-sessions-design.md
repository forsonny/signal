# Phase 6: Sessions + Conversation -- Design Spec

## Goal

Add multi-turn conversation persistence and an interactive REPL. `signal talk` stays one-shot (no breaking change). `signal chat` starts a multi-turn session. Sessions persist to JSONL files so conversations can be resumed across process restarts.

## Architecture

Phase 6 adds one new package, one new CLI command, and modifies four existing modules:

**New:**
- `sessions/manager.py` -- `SessionManager` for session file I/O (create, load, append, list)
- `cli/chat_cmd.py` -- `signal chat` interactive REPL command
- `cli/sessions_cmd.py` -- `signal sessions list` subcommand

**Modified:**
- `core/models.py` -- `Turn`, `SessionSummary` models; `history` field on `Message`
- `core/protocols.py` -- `RunnerProtocol` gains optional `history` parameter
- `runtime/runner.py` -- `AgenticRunner.run()` gains optional `history` parameter
- `runtime/executor.py` -- `Executor` gains `SessionManager`, `run()` gains `session_id`
- `agents/prime.py` -- `_handle_directly()` gains `history` parameter
- `runtime/bootstrap.py` -- create `SessionManager`, inject into `Executor`

### Flow

```
signal chat [--session <id>]
  |
  _async_chat() -- async bridge, REPL loop inside
  |
  Bootstrap runtime (same as signal talk)
  |
  SessionManager.create() or SessionManager.load(session_id)
  |
  Loop:
    user_input = console.input("you> ")
    |
    Executor.run(user_input, session_id=sid)
      |
      SessionManager.load(session_id) -> list[Turn]
      |
      Convert turns to history dicts: [{"role": t.role, "content": t.content}]
      |
      Message(type=TASK, sender=user, recipient=prime, content=user_input,
              history=history_dicts)
      |
      MessageBus.send(message)
      |
      PrimeAgent._handle(message)
        |
        history = message.history
        |
        _route() -- history NOT passed (classification, not knowledge)
        |
        _handle_directly(user_content, history)
          |
          messages = [system] + history + [user]
          |
          ai.complete(messages=messages)
      |
      Response returned to Executor
      |
      SessionManager.append(session_id, user_turn)
      SessionManager.append(session_id, assistant_turn)
      |
      ExecutorResult returned to REPL
    |
    Print response
```

When Prime routes to a micro-agent, history is NOT forwarded. The micro-agent gets a plain `Message(type=TASK, content=...)` with empty history. Micro-agents are stateless task executors -- the user's conversation history is with Prime, not with individual agents.

### Dependency Graph

```
sessions/manager.py    --> core/models (Turn, SessionSummary)
cli/chat_cmd.py        --> runtime/bootstrap, sessions/manager
cli/sessions_cmd.py    --> sessions/manager
runtime/executor.py    --> sessions/manager, comms/bus
agents/prime.py        --> core/protocols (unchanged deps)
runtime/runner.py      --> ai/layer (unchanged deps)
```

---

## Components

### 1. Turn and SessionSummary Models (core/models.py)

```python
class Turn(BaseModel):
    """A single conversational turn at the Prime level.

    Captures what the user said and what Prime responded. Internal agent
    execution (tool calls, micro-agent delegation) is invisible at this
    level -- it's contained within a single assistant turn. If a future
    phase needs to replay internal tool chains, Turn would need extending.
    """
    model_config = ConfigDict(extra="forbid")

    role: str       # "user" or "assistant"
    content: str
    timestamp: datetime


class SessionSummary(BaseModel):
    """Lightweight session listing entry."""
    model_config = ConfigDict(extra="forbid")

    id: str
    created: datetime
    preview: str      # First user message, truncated
    turn_count: int
```

### 2. Message.history Field (core/models.py)

```python
class Message(BaseModel):
    # ... existing fields ...
    history: list[dict[str, Any]] = Field(default_factory=list)
```

An explicit typed field, not metadata. Anyone reading the code sees that messages can carry conversation history. The bus passes it through without knowing or caring what it contains. Default empty list means all existing code works unchanged.

### 3. SessionManager (sessions/manager.py)

```python
class SessionManager:
    def __init__(self, sessions_dir: Path) -> None:
        self._sessions_dir = sessions_dir

    def create(self) -> str:
        """Create a new session. Returns session ID (ses_ + 8 hex chars)."""

    def append(self, session_id: str, turn: Turn) -> None:
        """Append a turn to the session's JSONL file."""

    def load(self, session_id: str) -> list[Turn]:
        """Load all turns from a session. Returns empty list if not found."""

    def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        """List recent sessions sorted by modification time."""

    def exists(self, session_id: str) -> bool:
        """Check if a session file exists."""
```

**File layout:** `data/sessions/{session_id}.jsonl` -- one JSON line per Turn.

**ID generation:** `ses_` + 8 hex chars via `secrets.token_hex(4)`. Same pattern as memory IDs (`mem_`).

**Sync I/O:** SessionManager is synchronous. File I/O is fast, no async needed. JSONL append is one `open(..., "a")` + `json.dumps()` + newline. Load is `readlines()` + `json.loads()` per line.

**list_sessions():** Scans `sessions_dir` for `.jsonl` files, reads first line for preview, counts lines for turn_count, uses file mtime for sorting. Returns most recent first, capped by `limit`.

### 4. Runner Changes (runtime/runner.py)

```python
class AgenticRunner:
    async def run(
        self,
        system_prompt: str,
        user_content: str,
        history: list[dict] | None = None,
    ) -> RunnerResult:
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        # ... rest of agentic loop unchanged ...
```

History entries are plain dicts in OpenAI message format: `{"role": "user", "content": "..."}` and `{"role": "assistant", "content": "..."}`. The runner doesn't know about `Turn` -- it receives pre-formatted dicts.

**RunnerProtocol** in `core/protocols.py` also gains the optional `history` parameter:

```python
@runtime_checkable
class RunnerProtocol(Protocol):
    async def run(
        self,
        system_prompt: str,
        user_content: str,
        history: list[dict] | None = None,
    ) -> Any: ...
```

### 5. PrimeAgent Changes (agents/prime.py)

**`_handle()`** extracts history from message and passes to `_handle_directly()`:

```python
async def _handle(self, message: Message) -> Message | None:
    history = message.history or None
    # ... routing logic unchanged ...
    # Direct handling:
    content = await self._handle_directly(message.content, history)
```

**`_handle_directly()`** gains `history` parameter:

```python
async def _handle_directly(self, user_content: str, history: list[dict] | None = None) -> str:
    # ... memory retrieval, build_system_prompt (Phase 5) ...
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    response = await self._ai.complete(messages=messages)
    return response.content
```

**Routing** does NOT receive history. Routing is classification -- it needs the current message to pick an agent, not the full conversation.

**Micro-agents** do NOT receive history. When Prime routes to a micro-agent, it sends `Message(type=TASK, content=message.content)` with default empty history. Micro-agents are stateless task executors.

### 6. Executor Changes (runtime/executor.py)

```python
class Executor:
    def __init__(
        self,
        bus: MessageBus,
        session_manager: SessionManager | None = None,
    ) -> None:

    async def run(
        self,
        user_message: str,
        session_id: str | None = None,
    ) -> ExecutorResult:
```

**When `session_id` is provided:**

1. Load turns: `turns = self._session_manager.load(session_id)`
2. Convert to history: `[{"role": t.role, "content": t.content} for t in turns]`
3. Create message with history: `Message(..., history=history)`
4. Send via bus, get response
5. On success: append `Turn(role="user", ...)` and `Turn(role="assistant", ...)` to session
6. Return result

**When `session_id` is None:** Identical to current behavior. No history, no persistence. One-shot path unchanged.

### 7. Bootstrap Changes (runtime/bootstrap.py)

```python
session_manager = SessionManager(instance_dir / "data" / "sessions")
executor = Executor(bus=bus, session_manager=session_manager)
return executor, bus, host  # Return type unchanged
```

Bootstrap creates SessionManager internally and injects it into Executor. The return type stays `tuple[Executor, MessageBus, AgentHost]` -- no existing call sites break. CLI commands that need SessionManager create their own instances pointing at the same directory. SessionManager is stateless file I/O, so multiple instances on the same directory is safe.

### 8. CLI: signal chat (cli/chat_cmd.py)

```python
@app.command()
def chat(session: str | None = typer.Option(None, help="Resume a session by ID")) -> None:
    """Start an interactive multi-turn conversation."""
    asyncio.run(_async_chat(session))


async def _async_chat(session_id: str | None) -> None:
    # Bootstrap runtime
    instance_dir = find_instance(Path.cwd())
    config = load_config(instance_dir / "config.yaml")
    profile = load_profile(config.profile_name)
    executor, bus, host = await bootstrap(instance_dir, config, profile)

    # Create or resume session -- CLI creates its own SessionManager
    # (same directory, stateless file I/O, safe to have multiple instances)
    sm = SessionManager(instance_dir / "data" / "sessions")
    if session_id and sm.exists(session_id):
        console.print(f"Resuming session {session_id}")
    else:
        session_id = sm.create()
        console.print(f"New session: {session_id}")

    # REPL loop
    try:
        while True:
            user_input = console.input("[bold]you>[/bold] ")
            if user_input.strip().startswith("/"):
                if user_input.strip() in ("/quit", "/exit"):
                    break
                elif user_input.strip() == "/history":
                    # Print conversation so far
                    for turn in sm.load(session_id):
                        role_label = "you" if turn.role == "user" else "agent"
                        console.print(f"[dim]{role_label}:[/dim] {turn.content}")
                    continue
                elif user_input.strip() == "/session":
                    console.print(f"Session: {session_id}")
                    continue
            result = await executor.run(user_input, session_id=session_id)
            if result.error:
                console.print(f"[red]Error: {result.error}[/red]")
            else:
                console.print(result.content)
    except KeyboardInterrupt:
        pass

    console.print(f"\nSession: {session_id}")
```

**Key:** The entire REPL loop lives inside `_async_chat()`. Typer's sync `chat()` just calls `asyncio.run()`. This is the same bridge pattern as `talk_cmd.py`.

### 9. CLI: signal sessions list (cli/sessions_cmd.py)

```python
@sessions_app.command("list")
def list_sessions() -> None:
    """List recent conversation sessions."""
    instance_dir = find_instance(Path.cwd())
    sm = SessionManager(instance_dir / "data" / "sessions")
    sessions = sm.list_sessions()
    # Rich table with ID, created, preview, turn count
```

---

## Error Handling

- **Session file missing on resume:** `SessionManager.load()` returns empty list. The session starts fresh but keeps the same ID. No error -- graceful degradation.
- **Session file corrupt (bad JSON line):** `load()` skips corrupt lines with a warning log. Partial history is better than no history.
- **Executor.run() fails mid-session:** Turns are only appended on success. If the LLM call fails, the session file is not modified -- the failed turn is lost, which is correct (no partial state).
- **Ctrl+C during REPL:** KeyboardInterrupt caught, session ID printed, clean exit. The session file has all completed turns.
- **SessionManager not provided (signal talk path):** `session_id=None` means no session ops. Executor's error boundary handles the case where session_manager is None and session_id is provided -- returns error.

---

## File Layout

```
src/signalagent/
  sessions/
    __init__.py            -- NEW (empty)
    manager.py             -- NEW: SessionManager

  core/
    models.py              -- MODIFIED: add Turn, SessionSummary, Message.history

  core/
    protocols.py           -- MODIFIED: RunnerProtocol gains history param

  runtime/
    runner.py              -- MODIFIED: AgenticRunner.run() gains history param
    executor.py            -- MODIFIED: gains SessionManager, run() gains session_id
    bootstrap.py           -- MODIFIED: create SessionManager, inject into Executor

  agents/
    prime.py               -- MODIFIED: _handle_directly() gains history param

  cli/
    chat_cmd.py            -- NEW: signal chat command
    sessions_cmd.py        -- NEW: signal sessions list command

tests/
  unit/
    sessions/
      test_manager.py      -- NEW: SessionManager tests
    runtime/
      test_runner.py       -- MODIFIED: history injection tests
      test_executor.py     -- MODIFIED: session-aware run tests
      test_bootstrap.py    -- MODIFIED: verify SessionManager injection
    agents/
      test_prime.py        -- MODIFIED: history passing tests
    core/
      test_protocols.py    -- MODIFIED: RunnerProtocol with history
```

---

## Done-When Criteria

**(a)** `SessionManager` with `create()`, `append()`, `load()`, `list_sessions()`, `exists()` -- JSONL file per session at `data/sessions/{session_id}.jsonl`

**(b)** `Turn` model with `role` (user/assistant), `content`, `timestamp` -- captures Prime-level conversation, not internal agent execution (documented)

**(c)** `SessionSummary` model with `id`, `created`, `preview`, `turn_count`

**(d)** `Message` gains `history: list[dict[str, Any]] = Field(default_factory=list)` -- explicit typed field, not metadata

**(e)** `AgenticRunner.run()` gains optional `history: list[dict] | None = None` -- injected between system prompt and user message

**(f)** `RunnerProtocol` updated to include `history` parameter

**(g)** `PrimeAgent._handle_directly()` gains `history` parameter, passes to AI call

**(h)** PrimeAgent routing does NOT receive history -- classification doesn't need conversation context

**(i)** Micro-agents do NOT receive history -- stateless task executors

**(j)** `Executor.run()` gains optional `session_id` parameter -- loads history, appends turns on success

**(k)** `signal talk` is unchanged -- no session, no persistence, one-shot

**(l)** `signal chat` starts interactive REPL with Rich `console.input`, auto-generated session ID, `/quit` to exit

**(m)** `signal chat --session <id>` resumes an existing session

**(n)** `signal sessions list` shows recent sessions with Rich table

**(o)** Session ID printed at start and on exit so users can resume

**(p)** Ctrl+C (KeyboardInterrupt) handled gracefully -- prints session ID, clean exit

**(q)** `_async_chat()` bridge pattern -- REPL loop inside async function, Typer calls `asyncio.run()`
