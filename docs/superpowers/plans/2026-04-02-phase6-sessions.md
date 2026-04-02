# Phase 6: Sessions + Conversation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-turn conversation persistence via JSONL sessions and an interactive REPL (`signal chat`), while keeping `signal talk` one-shot and unchanged.

**Architecture:** A `sessions/` package with `SessionManager` for file I/O (create, load, append, list). Executor gains an optional `session_id` on `run()` to load history and persist turns. PrimeAgent passes history to its AI call for multi-turn context. `signal chat` is a Rich-based REPL loop with the async bridge pattern. Bootstrap return type is unchanged -- CLI creates its own SessionManager.

**Tech Stack:** Python 3.11+, Pydantic v2, Rich (console.input for REPL), Typer, JSONL for session storage

---

## File Structure

```
src/signalagent/
  sessions/
    __init__.py            -- NEW (empty)
    manager.py             -- NEW: SessionManager (create, load, append, list_sessions, exists)

  core/
    models.py              -- MODIFIED: add Turn, SessionSummary; add history field to Message
    protocols.py           -- MODIFIED: RunnerProtocol gains history param

  runtime/
    runner.py              -- MODIFIED: AgenticRunner.run() gains history param
    executor.py            -- MODIFIED: gains SessionManager, run() gains session_id
    bootstrap.py           -- MODIFIED: create SessionManager, inject into Executor

  agents/
    prime.py               -- MODIFIED: _handle passes history, _handle_directly gains history param

  cli/
    chat_cmd.py            -- NEW: signal chat interactive REPL
    sessions_cmd.py        -- NEW: signal sessions list
    app.py                 -- MODIFIED: register chat + sessions commands

tests/
  unit/
    sessions/
      __init__.py          -- NEW (empty)
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

### Task 1: Turn, SessionSummary, and Message.history Models

**Files:**
- Modify: `src/signalagent/core/models.py:94-107`
- Test: `tests/unit/core/test_models.py` (if exists, otherwise inline verification)

- [ ] **Step 1: Write the failing test**

Create or update `tests/unit/core/test_models.py` (add the following):

```python
"""Tests for Phase 6 models: Turn, SessionSummary, Message.history."""
from datetime import datetime, timezone

from signalagent.core.models import Turn, SessionSummary, Message
from signalagent.core.types import MessageType


class TestTurnModel:
    def test_turn_creation(self):
        now = datetime.now(timezone.utc)
        turn = Turn(role="user", content="hello", timestamp=now)
        assert turn.role == "user"
        assert turn.content == "hello"
        assert turn.timestamp == now

    def test_turn_forbids_extra_fields(self):
        import pytest
        with pytest.raises(Exception):
            Turn(role="user", content="hi", timestamp=datetime.now(timezone.utc), extra="bad")


class TestSessionSummaryModel:
    def test_session_summary_creation(self):
        now = datetime.now(timezone.utc)
        summary = SessionSummary(id="ses_abc12345", created=now, preview="hello world", turn_count=5)
        assert summary.id == "ses_abc12345"
        assert summary.turn_count == 5


class TestMessageHistory:
    def test_message_history_defaults_to_empty_list(self):
        msg = Message(type=MessageType.TASK, sender="user", recipient="prime", content="hi")
        assert msg.history == []

    def test_message_with_history(self):
        history = [{"role": "user", "content": "prior"}, {"role": "assistant", "content": "reply"}]
        msg = Message(type=MessageType.TASK, sender="user", recipient="prime", content="new", history=history)
        assert len(msg.history) == 2
        assert msg.history[0]["role"] == "user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/core/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Turn'`

- [ ] **Step 3: Add models to core/models.py**

Add `Turn` and `SessionSummary` after the `Message` class (around line 107), and add `history` field to `Message`:

In `Message`, add the `history` field after `metadata`:

```python
class Message(BaseModel):
    """Typed message passed between agents via the MessageBus."""
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    type: MessageType = Field(...)
    sender: str
    recipient: str
    content: str
    created: datetime | None = None
    parent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)
```

Add after `Message`:

```python
class Turn(BaseModel):
    """A single conversational turn at the Prime level.

    Captures what the user said and what Prime responded. Internal agent
    execution (tool calls, micro-agent delegation) is invisible at this
    level -- it's contained within a single assistant turn. If a future
    phase needs to replay internal tool chains, Turn would need extending.
    """
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    timestamp: datetime


class SessionSummary(BaseModel):
    """Lightweight session listing entry."""
    model_config = ConfigDict(extra="forbid")

    id: str
    created: datetime
    preview: str
    turn_count: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/core/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
Expected: All 281 existing tests pass + new model tests

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/core/models.py tests/unit/core/test_models.py
git commit -m "feat: add Turn, SessionSummary models and Message.history field"
```

---

### Task 2: SessionManager

**Files:**
- Create: `src/signalagent/sessions/__init__.py`
- Create: `src/signalagent/sessions/manager.py`
- Create: `tests/unit/sessions/__init__.py`
- Create: `tests/unit/sessions/test_manager.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/sessions/__init__.py` (empty file).

Create `tests/unit/sessions/test_manager.py`:

```python
"""Unit tests for SessionManager -- file-based session persistence."""
import json
import pytest
from datetime import datetime, timezone

from signalagent.core.models import Turn
from signalagent.sessions.manager import SessionManager


class TestSessionCreate:
    def test_create_returns_session_id(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        assert sid.startswith("ses_")
        assert len(sid) == 12  # ses_ + 8 hex chars

    def test_create_creates_empty_file(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        path = tmp_path / f"{sid}.jsonl"
        assert path.exists()
        assert path.read_text() == ""

    def test_create_generates_unique_ids(self, tmp_path):
        sm = SessionManager(tmp_path)
        ids = {sm.create() for _ in range(10)}
        assert len(ids) == 10


class TestSessionAppendAndLoad:
    def test_append_and_load_single_turn(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        turn = Turn(role="user", content="hello", timestamp=datetime.now(timezone.utc))
        sm.append(sid, turn)
        turns = sm.load(sid)
        assert len(turns) == 1
        assert turns[0].role == "user"
        assert turns[0].content == "hello"

    def test_append_multiple_turns_preserves_order(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="first", timestamp=now))
        sm.append(sid, Turn(role="assistant", content="second", timestamp=now))
        sm.append(sid, Turn(role="user", content="third", timestamp=now))
        turns = sm.load(sid)
        assert len(turns) == 3
        assert [t.content for t in turns] == ["first", "second", "third"]

    def test_load_nonexistent_returns_empty(self, tmp_path):
        sm = SessionManager(tmp_path)
        turns = sm.load("ses_nonexist")
        assert turns == []

    def test_load_skips_corrupt_lines(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="good", timestamp=now))
        # Manually corrupt the file by appending bad JSON
        path = tmp_path / f"{sid}.jsonl"
        with open(path, "a") as f:
            f.write("NOT VALID JSON\n")
        sm.append(sid, Turn(role="assistant", content="also good", timestamp=now))
        turns = sm.load(sid)
        assert len(turns) == 2
        assert turns[0].content == "good"
        assert turns[1].content == "also good"


class TestSessionExists:
    def test_exists_true_for_created_session(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        assert sm.exists(sid) is True

    def test_exists_false_for_missing_session(self, tmp_path):
        sm = SessionManager(tmp_path)
        assert sm.exists("ses_nonexist") is False


class TestSessionList:
    def test_list_sessions_returns_summaries(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="hello world", timestamp=now))
        sm.append(sid, Turn(role="assistant", content="hi there", timestamp=now))
        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].id == sid
        assert sessions[0].turn_count == 2
        assert "hello world" in sessions[0].preview

    def test_list_sessions_empty_dir(self, tmp_path):
        sm = SessionManager(tmp_path)
        sessions = sm.list_sessions()
        assert sessions == []

    def test_list_sessions_respects_limit(self, tmp_path):
        sm = SessionManager(tmp_path)
        now = datetime.now(timezone.utc)
        for _ in range(5):
            sid = sm.create()
            sm.append(sid, Turn(role="user", content="msg", timestamp=now))
        sessions = sm.list_sessions(limit=3)
        assert len(sessions) == 3

    def test_list_sessions_sorted_by_recency(self, tmp_path):
        sm = SessionManager(tmp_path)
        now = datetime.now(timezone.utc)
        sid1 = sm.create()
        sm.append(sid1, Turn(role="user", content="older", timestamp=now))
        sid2 = sm.create()
        sm.append(sid2, Turn(role="user", content="newer", timestamp=now))
        sessions = sm.list_sessions()
        # Most recent first
        assert sessions[0].id == sid2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/sessions/test_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalagent.sessions'`

- [ ] **Step 3: Implement SessionManager**

Create `src/signalagent/sessions/__init__.py` (empty file).

Create `src/signalagent/sessions/manager.py`:

```python
"""SessionManager -- JSONL-based conversation session persistence."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

from signalagent.core.models import Turn, SessionSummary

logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    """Generate a unique session ID: ses_ + 8 hex chars."""
    return f"ses_{secrets.token_hex(4)}"


class SessionManager:
    """Manages session files in JSONL format.

    Each session is a single file: {sessions_dir}/{session_id}.jsonl
    One JSON line per Turn. Append-only writes, sequential reads.
    Sync I/O -- file operations are fast, no async needed.
    """

    def __init__(self, sessions_dir: Path) -> None:
        self._sessions_dir = sessions_dir
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def create(self) -> str:
        """Create a new empty session. Returns the session ID."""
        session_id = generate_session_id()
        path = self._sessions_dir / f"{session_id}.jsonl"
        path.touch()
        return session_id

    def append(self, session_id: str, turn: Turn) -> None:
        """Append a turn to the session's JSONL file."""
        path = self._sessions_dir / f"{session_id}.jsonl"
        line = turn.model_dump_json()
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load(self, session_id: str) -> list[Turn]:
        """Load all turns from a session. Returns empty list if not found."""
        path = self._sessions_dir / f"{session_id}.jsonl"
        if not path.exists():
            return []
        turns: list[Turn] = []
        for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                turns.append(Turn.model_validate_json(line))
            except Exception:
                logger.warning("Corrupt line %d in session %s, skipping", line_num, session_id)
        return turns

    def exists(self, session_id: str) -> bool:
        """Check if a session file exists."""
        return (self._sessions_dir / f"{session_id}.jsonl").exists()

    def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        """List recent sessions sorted by modification time (newest first)."""
        files = sorted(
            self._sessions_dir.glob("ses_*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        summaries: list[SessionSummary] = []
        for f in files:
            session_id = f.stem
            lines = f.read_text(encoding="utf-8").splitlines()
            valid_lines = [l for l in lines if l.strip()]
            turn_count = len(valid_lines)
            preview = ""
            created = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if valid_lines:
                try:
                    first_turn = Turn.model_validate_json(valid_lines[0])
                    preview = first_turn.content[:80]
                    created = first_turn.timestamp
                except Exception:
                    preview = "(corrupt)"
            summaries.append(SessionSummary(
                id=session_id,
                created=created,
                preview=preview,
                turn_count=turn_count,
            ))
        return summaries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/sessions/test_manager.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Run full test suite**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/sessions/__init__.py src/signalagent/sessions/manager.py tests/unit/sessions/__init__.py tests/unit/sessions/test_manager.py
git commit -m "feat: add SessionManager with JSONL-based session persistence"
```

---

### Task 3: RunnerProtocol + AgenticRunner History Injection

**Files:**
- Modify: `src/signalagent/core/protocols.py:26-34`
- Modify: `src/signalagent/runtime/runner.py:36-40`
- Modify: `tests/unit/core/test_protocols.py`
- Modify: `tests/unit/runtime/test_runner.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/runtime/test_runner.py`:

```python
class TestRunnerHistory:
    @pytest.mark.asyncio
    async def test_history_injected_between_system_and_user(self):
        """History messages appear between system prompt and user message."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_text_response("done"))
        mock_executor = AsyncMock()
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[], max_iterations=10)
        history = [
            {"role": "user", "content": "prior question"},
            {"role": "assistant", "content": "prior answer"},
        ]
        await runner.run(system_prompt="You are helpful.", user_content="new question",
                         history=history)
        messages = mock_ai.complete.call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "prior question"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "prior answer"
        assert messages[3]["role"] == "user"
        assert messages[3]["content"] == "new question"

    @pytest.mark.asyncio
    async def test_none_history_behaves_like_no_history(self):
        """history=None produces same messages as no history."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_text_response("done"))
        mock_executor = AsyncMock()
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[], max_iterations=10)
        await runner.run(system_prompt="sys", user_content="hi", history=None)
        messages = mock_ai.complete.call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
```

Add to `tests/unit/core/test_protocols.py`:

```python
class TestRunnerProtocolHistory:
    def test_runner_with_history_satisfies_protocol(self):
        """A runner with history parameter satisfies RunnerProtocol."""
        from signalagent.runtime.runner import AgenticRunner
        # AgenticRunner already satisfies it -- just verify the protocol
        # allows the history parameter by checking issubclass still holds.
        from signalagent.core.protocols import RunnerProtocol
        assert issubclass(AgenticRunner, RunnerProtocol)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/runtime/test_runner.py::TestRunnerHistory -v`
Expected: FAIL with `TypeError: run() got an unexpected keyword argument 'history'`

- [ ] **Step 3: Update RunnerProtocol**

In `src/signalagent/core/protocols.py`, update `RunnerProtocol`:

```python
@runtime_checkable
class RunnerProtocol(Protocol):
    """Protocol for the agentic loop runner.
    Agents depend on this protocol, not the concrete AgenticRunner."""
    async def run(
        self,
        system_prompt: str,
        user_content: str,
        history: list[dict] | None = None,
    ) -> Any: ...
```

- [ ] **Step 4: Update AgenticRunner.run()**

In `src/signalagent/runtime/runner.py`, update the `run` method (lines 36-40):

```python
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
        tools = self._tool_schemas if self._tool_schemas else None
```

The rest of the method (agentic loop) is unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/runtime/test_runner.py tests/unit/core/test_protocols.py -v`
Expected: PASS (all existing + 3 new)

- [ ] **Step 6: Run full test suite**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/signalagent/core/protocols.py src/signalagent/runtime/runner.py tests/unit/runtime/test_runner.py tests/unit/core/test_protocols.py
git commit -m "feat: add history injection to AgenticRunner and RunnerProtocol"
```

---

### Task 4: PrimeAgent History

**Files:**
- Modify: `src/signalagent/agents/prime.py:49-69,123-152`
- Modify: `tests/unit/agents/test_prime.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/agents/test_prime.py` a new test class:

```python
class TestHistoryPassing:
    @pytest.mark.asyncio
    async def test_handle_directly_includes_history_in_ai_call(self, host, bus):
        """History from message is passed to the AI call."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("response"))
        _register_prime(host, bus, mock_ai)

        history = [
            {"role": "user", "content": "prior question"},
            {"role": "assistant", "content": "prior answer"},
        ]
        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="new question",
            history=history,
        )
        await bus.send(msg)

        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        # system + 2 history entries + user = 4 messages
        assert len(call_messages) == 4
        assert call_messages[0]["role"] == "system"
        assert call_messages[1]["role"] == "user"
        assert call_messages[1]["content"] == "prior question"
        assert call_messages[2]["role"] == "assistant"
        assert call_messages[3]["role"] == "user"
        assert call_messages[3]["content"] == "new question"

    @pytest.mark.asyncio
    async def test_routing_does_not_receive_history(self, host, bus):
        """When routing to micro-agent, the task message has no history."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("code-review"),
        )
        _register_prime(host, bus, mock_ai)
        _register_stub_micro(host, "code-review")

        history = [{"role": "user", "content": "prior"}]
        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="review code",
            history=history,
        )
        result = await bus.send(msg)

        # Routing call is the first ai.complete call -- doesn't use history
        routing_call = mock_ai.complete.call_args_list[0]
        routing_messages = routing_call.kwargs["messages"]
        # Routing prompt is a single user message
        assert len(routing_messages) == 1
        assert routing_messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_micro_agent_task_has_empty_history(self, host, bus):
        """When Prime routes to a micro-agent, the task message has empty history."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("code-review"),
        )
        _register_prime(host, bus, mock_ai)
        _register_stub_micro(host, "code-review")

        history = [{"role": "user", "content": "prior context"}]
        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="review code",
            history=history,
        )
        await bus.send(msg)

        # The StubMicro received a task message -- verify it has no history.
        # bus.log contains all messages: user->prime, prime->micro, micro->prime, prime->user
        task_to_micro = [m for m in bus.log if m.recipient == "code-review"]
        assert len(task_to_micro) == 1
        assert task_to_micro[0].history == []

    @pytest.mark.asyncio
    async def test_empty_history_works_like_before(self, host, bus):
        """Empty history (default) produces the same behavior as pre-Phase 6."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("response"))
        _register_prime(host, bus, mock_ai)

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="hello",
        )
        await bus.send(msg)

        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        assert len(call_messages) == 2  # system + user only
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/agents/test_prime.py::TestHistoryPassing -v`
Expected: FAIL (history not used in _handle_directly yet)

- [ ] **Step 3: Update PrimeAgent**

In `src/signalagent/agents/prime.py`, update `_handle()` to extract and pass history:

```python
    async def _handle(self, message: Message) -> Message | None:
        """Route to micro-agent or handle directly."""
        history = message.history or None
        micro_agents = self._host.list_micro_agents()

        if not micro_agents:
            content = await self._handle_directly(message.content, history)
        else:
            target = await self._route(message.content, micro_agents)
            if target is not None:
                # Dispatch to micro-agent via bus -- no history forwarded.
                # Micro-agents are stateless task executors.
                task_msg = Message(
                    type=MessageType.TASK,
                    sender=PRIME_AGENT,
                    recipient=target,
                    content=message.content,
                    parent_id=message.id,
                )
                micro_response = await self._bus.send(task_msg)
                content = micro_response.content if micro_response else ""
            else:
                content = await self._handle_directly(message.content, history)

        return Message(
            type=MessageType.RESULT,
            sender=PRIME_AGENT,
            recipient=message.sender,
            content=content,
            parent_id=message.id,
        )
```

Update `_handle_directly()` to accept and use history:

```python
    async def _handle_directly(
        self, user_content: str, history: list[dict] | None = None,
    ) -> str:
        """Execute using Prime's own identity prompt. Fallback path."""
        memories = []
        if self._memory_reader:
            try:
                memories = await self._memory_reader.search(
                    agent="prime", limit=DEFAULT_MEMORY_LIMIT,
                )
            except Exception:
                logger.warning("Memory retrieval failed, proceeding without context")

        if memories and self._model:
            system_prompt = build_system_prompt(
                identity=self._identity,
                memories=memories,
                model=self._model,
            )
        elif memories:
            logger.warning("Memories retrieved but no model set; skipping context injection")
            system_prompt = self._identity
        else:
            system_prompt = self._identity

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})

        response = await self._ai.complete(messages=messages)
        return response.content
```

- [ ] **Step 4: Run all prime agent tests**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/agents/test_prime.py -v`
Expected: PASS (all existing + 3 new)

- [ ] **Step 5: Run full test suite**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/agents/prime.py tests/unit/agents/test_prime.py
git commit -m "feat: add conversation history to PrimeAgent direct handling"
```

---

### Task 5: Session-Aware Executor

**Files:**
- Modify: `src/signalagent/runtime/executor.py:35-76`
- Modify: `tests/unit/runtime/test_executor.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/runtime/test_executor.py`. First update imports:

```python
"""Unit tests for Executor -- bus-based, mock bus."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from signalagent.core.models import Message, Turn
from signalagent.core.types import MessageType, USER_SENDER, PRIME_AGENT
from signalagent.runtime.executor import Executor, ExecutorResult
```

Add test class:

```python
class TestSessionAwareExecutor:
    @pytest.mark.asyncio
    async def test_run_with_session_loads_history(self):
        """Session ID causes history to be loaded and passed in message."""
        response_msg = Message(
            type=MessageType.RESULT, sender=PRIME_AGENT,
            recipient=USER_SENDER, content="reply",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        mock_sm = MagicMock()
        now = datetime.now(timezone.utc)
        mock_sm.load.return_value = [
            Turn(role="user", content="prior", timestamp=now),
            Turn(role="assistant", content="prior reply", timestamp=now),
        ]

        executor = Executor(bus=mock_bus, session_manager=mock_sm)
        result = await executor.run("new message", session_id="ses_test0001")

        assert result.content == "reply"
        # Verify history was set on the message sent to bus
        sent_msg = mock_bus.send.call_args[0][0]
        assert len(sent_msg.history) == 2
        assert sent_msg.history[0]["role"] == "user"
        assert sent_msg.history[0]["content"] == "prior"

    @pytest.mark.asyncio
    async def test_run_with_session_appends_turns(self):
        """Successful run appends user and assistant turns to session."""
        response_msg = Message(
            type=MessageType.RESULT, sender=PRIME_AGENT,
            recipient=USER_SENDER, content="agent reply",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        mock_sm = MagicMock()
        mock_sm.load.return_value = []

        executor = Executor(bus=mock_bus, session_manager=mock_sm)
        await executor.run("hello", session_id="ses_test0001")

        assert mock_sm.append.call_count == 2
        user_turn = mock_sm.append.call_args_list[0][0][1]
        assert user_turn.role == "user"
        assert user_turn.content == "hello"
        assistant_turn = mock_sm.append.call_args_list[1][0][1]
        assert assistant_turn.role == "assistant"
        assert assistant_turn.content == "agent reply"

    @pytest.mark.asyncio
    async def test_run_without_session_no_persistence(self):
        """No session_id means no history loaded, no turns appended."""
        response_msg = Message(
            type=MessageType.RESULT, sender=PRIME_AGENT,
            recipient=USER_SENDER, content="reply",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        mock_sm = MagicMock()
        executor = Executor(bus=mock_bus, session_manager=mock_sm)
        result = await executor.run("hello")

        assert result.content == "reply"
        mock_sm.load.assert_not_called()
        mock_sm.append.assert_not_called()
        # Message should have empty history
        sent_msg = mock_bus.send.call_args[0][0]
        assert sent_msg.history == []

    @pytest.mark.asyncio
    async def test_run_error_does_not_persist_turns(self):
        """If the bus call fails, no turns are appended to session."""
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(side_effect=Exception("bus error"))

        mock_sm = MagicMock()
        mock_sm.load.return_value = []

        executor = Executor(bus=mock_bus, session_manager=mock_sm)
        result = await executor.run("hello", session_id="ses_test0001")

        assert result.error is not None
        mock_sm.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_backward_compatible_no_session_manager(self):
        """Executor without session_manager works exactly as before."""
        response_msg = Message(
            type=MessageType.RESULT, sender=PRIME_AGENT,
            recipient=USER_SENDER, content="reply",
        )
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=response_msg)

        executor = Executor(bus=mock_bus)
        result = await executor.run("hello")

        assert result.content == "reply"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/runtime/test_executor.py::TestSessionAwareExecutor -v`
Expected: FAIL with `TypeError: Executor.__init__() got an unexpected keyword argument 'session_manager'`

- [ ] **Step 3: Update Executor**

Replace the full content of `src/signalagent/runtime/executor.py`:

```python
"""Executor -- sends user messages to Prime via the MessageBus."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from signalagent.comms.bus import MessageBus
    from signalagent.sessions.manager import SessionManager

from signalagent.core.models import Message, Turn
from signalagent.core.protocols import AILayerProtocol
from signalagent.core.types import MessageType, USER_SENDER, PRIME_AGENT

logger = logging.getLogger(__name__)

# Re-export so existing `from signalagent.runtime.executor import AILayerProtocol`
# imports continue to work without modification.
__all__ = ["AILayerProtocol", "ExecutorResult", "Executor"]


@dataclass
class ExecutorResult:
    """Result of an executor run."""

    content: str
    error: Optional[str] = None
    error_type: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class Executor:
    """Sends user messages to Prime via the MessageBus.

    Error boundary: exceptions from the bus/agent chain are caught,
    logged, and returned as an ExecutorResult with error set.
    """

    def __init__(
        self,
        bus: MessageBus,
        session_manager: SessionManager | None = None,
    ) -> None:
        self._bus = bus
        self._session_manager = session_manager

    async def run(
        self,
        user_message: str,
        session_id: str | None = None,
    ) -> ExecutorResult:
        """Send user message to Prime via bus, return result.

        Args:
            user_message: The user's input text.
            session_id: Optional session ID for multi-turn persistence.
                If provided, loads conversation history and appends
                turns on success.

        Returns:
            ExecutorResult with content or error. Never raises.
        """
        # Load history if session is active
        history: list[dict[str, Any]] = []
        if session_id and self._session_manager:
            turns = self._session_manager.load(session_id)
            history = [{"role": t.role, "content": t.content} for t in turns]

        message = Message(
            type=MessageType.TASK,
            sender=USER_SENDER,
            recipient=PRIME_AGENT,
            content=user_message,
            history=history,
        )

        try:
            response = await self._bus.send(message)
            if response is None:
                return ExecutorResult(
                    content="",
                    error="No response from agent",
                )

            # Persist turns on success
            if session_id and self._session_manager:
                now = datetime.now(timezone.utc)
                self._session_manager.append(
                    session_id, Turn(role="user", content=user_message, timestamp=now),
                )
                self._session_manager.append(
                    session_id, Turn(role="assistant", content=response.content, timestamp=now),
                )

            return ExecutorResult(content=response.content)
        except Exception as e:
            logger.error("Executor error: %s", e, exc_info=True)
            return ExecutorResult(
                content="",
                error=str(e),
                error_type=type(e).__name__,
            )
```

- [ ] **Step 4: Run all executor tests**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/runtime/test_executor.py -v`
Expected: PASS (3 existing + 5 new)

- [ ] **Step 5: Run full test suite**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/runtime/executor.py tests/unit/runtime/test_executor.py
git commit -m "feat: add session-aware Executor with history loading and turn persistence"
```

---

### Task 6: Bootstrap Wiring

**Files:**
- Modify: `src/signalagent/runtime/bootstrap.py:1-133`
- Modify: `tests/unit/runtime/test_bootstrap.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/runtime/test_bootstrap.py`:

```python
class TestSessionManagerInjection:
    @pytest.mark.asyncio
    async def test_executor_has_session_manager(self, tmp_path, config, profile_no_micros, monkeypatch):
        """Bootstrap injects SessionManager into Executor."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_no_micros)

        # Executor should have a session manager
        assert executor._session_manager is not None  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_sessions_directory_exists(self, tmp_path, config, profile_no_micros, monkeypatch):
        """Bootstrap ensures data/sessions directory exists."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        await bootstrap(tmp_path, config, profile_no_micros)

        assert (tmp_path / "data" / "sessions").is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/runtime/test_bootstrap.py::TestSessionManagerInjection -v`
Expected: FAIL (executor doesn't have session_manager yet)

- [ ] **Step 3: Update bootstrap.py**

Add import at the top of `src/signalagent/runtime/bootstrap.py`:

```python
from signalagent.sessions.manager import SessionManager
```

Before the `executor = Executor(bus=bus)` line at the end of the function, add SessionManager creation and inject it:

```python
    # Session manager
    session_manager = SessionManager(instance_dir / "data" / "sessions")

    executor = Executor(bus=bus, session_manager=session_manager)
    return executor, bus, host
```

- [ ] **Step 4: Run bootstrap tests**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/runtime/test_bootstrap.py -v`
Expected: PASS (all existing + 2 new)

- [ ] **Step 5: Run full test suite**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/runtime/bootstrap.py tests/unit/runtime/test_bootstrap.py
git commit -m "feat: bootstrap injects SessionManager into Executor"
```

---

### Task 7: signal chat REPL Command

**Files:**
- Create: `src/signalagent/cli/chat_cmd.py`
- Modify: `src/signalagent/cli/app.py`

- [ ] **Step 1: Create chat_cmd.py**

Create `src/signalagent/cli/chat_cmd.py`:

```python
"""signal chat -- interactive multi-turn conversation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from signalagent.cli.app import app
from signalagent.core.errors import InstanceError

console = Console()


async def _async_chat(session_id: str | None, instance_dir: Path) -> None:
    """Async REPL loop for interactive conversation.

    Imports are deferred to avoid pulling in heavyweight modules
    at CLI startup -- same pattern as talk_cmd.py.
    """
    from signalagent.core.config import load_config, load_profile
    from signalagent.runtime.bootstrap import bootstrap
    from signalagent.sessions.manager import SessionManager

    config = load_config(instance_dir / "config.yaml")
    profile = load_profile(config.profile_name)
    executor, _bus, _host = await bootstrap(instance_dir, config, profile)

    # CLI creates its own SessionManager (same directory, stateless file I/O)
    sm = SessionManager(instance_dir / "data" / "sessions")

    if session_id and sm.exists(session_id):
        console.print(f"Resuming session [bold]{session_id}[/bold]")
        # Show recent history
        turns = sm.load(session_id)
        for turn in turns[-6:]:  # Last 3 exchanges
            label = "[dim]you:[/dim]" if turn.role == "user" else "[dim]agent:[/dim]"
            console.print(f"  {label} {turn.content[:120]}")
        if turns:
            console.print()
    else:
        session_id = sm.create()
        console.print(f"New session: [bold]{session_id}[/bold]")

    console.print("[dim]Type /quit to exit, /history to show conversation, /session to show ID[/dim]\n")

    try:
        while True:
            try:
                user_input = console.input("[bold]you>[/bold] ")
            except EOFError:
                break

            stripped = user_input.strip()
            if not stripped:
                continue

            if stripped.startswith("/"):
                if stripped in ("/quit", "/exit"):
                    break
                elif stripped == "/history":
                    for turn in sm.load(session_id):
                        label = "you" if turn.role == "user" else "agent"
                        console.print(f"[dim]{label}:[/dim] {turn.content}")
                    continue
                elif stripped == "/session":
                    console.print(f"Session: {session_id}")
                    continue
                else:
                    console.print(f"[dim]Unknown command: {stripped}[/dim]")
                    continue

            result = await executor.run(user_input, session_id=session_id)
            if result.error:
                console.print(f"[red]Error: {result.error}[/red]")
            else:
                console.print(result.content)
            console.print()
    except KeyboardInterrupt:
        pass

    console.print(f"\nSession: [bold]{session_id}[/bold]")


@app.command()
def chat(
    session: str | None = typer.Option(None, "--session", "-s", help="Resume a session by ID"),
) -> None:
    """Start an interactive multi-turn conversation."""
    try:
        from signalagent.core.config import find_instance
        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)

    asyncio.run(_async_chat(session, instance_dir))
```

- [ ] **Step 2: Register chat command in app.py**

In `src/signalagent/cli/app.py`, add to `_register_commands()`:

```python
def _register_commands() -> None:
    """Import command modules so their @app.command() decorators execute."""
    import signalagent.cli.init_cmd  # noqa: F401
    import signalagent.cli.talk_cmd  # noqa: F401
    import signalagent.cli.chat_cmd  # noqa: F401
    from signalagent.cli.memory_cmd import memory_app

    app.add_typer(memory_app, name="memory")
```

- [ ] **Step 3: Verify signal --help shows chat command**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m signalagent.cli.app --help`
Expected: Shows `chat` command alongside `init`, `talk`, `memory`

- [ ] **Step 4: Commit**

```bash
git add src/signalagent/cli/chat_cmd.py src/signalagent/cli/app.py
git commit -m "feat: add signal chat interactive REPL command"
```

---

### Task 8: signal sessions list Command

**Files:**
- Create: `src/signalagent/cli/sessions_cmd.py`
- Modify: `src/signalagent/cli/app.py`

- [ ] **Step 1: Create sessions_cmd.py**

Create `src/signalagent/cli/sessions_cmd.py`:

```python
"""signal sessions -- session management commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from signalagent.core.errors import InstanceError

sessions_app = typer.Typer(
    name="sessions",
    help="Manage conversation sessions.",
    no_args_is_help=True,
)

console = Console()


@sessions_app.command("list")
def list_sessions(
    limit: int = typer.Option(20, "--limit", "-n", help="Max sessions to show"),
) -> None:
    """List recent conversation sessions."""
    try:
        from signalagent.core.config import find_instance
        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)

    from signalagent.sessions.manager import SessionManager

    sm = SessionManager(instance_dir / "data" / "sessions")
    sessions = sm.list_sessions(limit=limit)

    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Recent Sessions")
    table.add_column("ID", style="bold")
    table.add_column("Created")
    table.add_column("Preview")
    table.add_column("Turns", justify="right")

    for s in sessions:
        table.add_row(
            s.id,
            s.created.strftime("%Y-%m-%d %H:%M"),
            s.preview[:60] + ("..." if len(s.preview) > 60 else ""),
            str(s.turn_count),
        )

    console.print(table)
```

- [ ] **Step 2: Register sessions subcommand in app.py**

In `src/signalagent/cli/app.py`, update `_register_commands()`:

```python
def _register_commands() -> None:
    """Import command modules so their @app.command() decorators execute."""
    import signalagent.cli.init_cmd  # noqa: F401
    import signalagent.cli.talk_cmd  # noqa: F401
    import signalagent.cli.chat_cmd  # noqa: F401
    from signalagent.cli.memory_cmd import memory_app
    from signalagent.cli.sessions_cmd import sessions_app

    app.add_typer(memory_app, name="memory")
    app.add_typer(sessions_app, name="sessions")
```

- [ ] **Step 3: Verify signal sessions --help works**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m signalagent.cli.app sessions --help`
Expected: Shows `list` subcommand

- [ ] **Step 4: Commit**

```bash
git add src/signalagent/cli/sessions_cmd.py src/signalagent/cli/app.py
git commit -m "feat: add signal sessions list command"
```

---

### Task 9: CLI Integration Tests

**Files:**
- Create: `tests/unit/cli/test_chat_cmd.py`
- Create: `tests/unit/cli/test_sessions_cmd.py`
- Create: `tests/unit/cli/__init__.py` (if not exists)

- [ ] **Step 1: Write CLI tests**

Create `tests/unit/cli/__init__.py` (empty file if it doesn't exist).

Create `tests/unit/cli/test_sessions_cmd.py`:

```python
"""Integration tests for signal sessions CLI commands."""
import pytest
from datetime import datetime, timezone

from typer.testing import CliRunner

from signalagent.cli.app import app
from signalagent.core.models import Turn
from signalagent.sessions.manager import SessionManager


runner = CliRunner()


class TestSessionsList:
    def test_sessions_list_no_instance(self, tmp_path, monkeypatch):
        """signal sessions list exits 1 when no instance found."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sessions", "list"])
        assert result.exit_code == 1

    def test_sessions_list_empty(self, tmp_path, monkeypatch):
        """signal sessions list shows message when no sessions exist."""
        # Create minimal instance structure
        instance_dir = tmp_path / ".signal"
        instance_dir.mkdir()
        (instance_dir / "config.yaml").write_text("profile_name: blank\n")
        (instance_dir / "data" / "sessions").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["sessions", "list"])
        assert result.exit_code == 0
        assert "No sessions" in result.output

    def test_sessions_list_shows_sessions(self, tmp_path, monkeypatch):
        """signal sessions list displays session table."""
        instance_dir = tmp_path / ".signal"
        instance_dir.mkdir()
        (instance_dir / "config.yaml").write_text("profile_name: blank\n")
        sessions_dir = instance_dir / "data" / "sessions"
        sessions_dir.mkdir(parents=True)

        sm = SessionManager(sessions_dir)
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="hello world", timestamp=now))
        sm.append(sid, Turn(role="assistant", content="hi there", timestamp=now))

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sessions", "list"])
        assert result.exit_code == 0
        assert sid in result.output
        assert "hello world" in result.output
```

Create `tests/unit/cli/test_chat_cmd.py`:

```python
"""Integration tests for signal chat CLI command."""
import pytest

from typer.testing import CliRunner

from signalagent.cli.app import app


runner = CliRunner()


class TestChatCommand:
    def test_chat_no_instance_exits_1(self, tmp_path, monkeypatch):
        """signal chat exits 1 when no instance found."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["chat"])
        assert result.exit_code == 1

    def test_chat_accepts_session_option(self):
        """signal chat --session is a recognized option."""
        # Just verify the CLI accepts the flag (it will fail finding instance)
        result = runner.invoke(app, ["chat", "--session", "ses_test0001"])
        # Will fail because no instance, but should NOT fail with "no such option"
        assert "No such option" not in (result.output or "")
```

- [ ] **Step 2: Run CLI tests**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/unit/cli/ -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/unit/cli/
git commit -m "test: add CLI integration tests for chat and sessions commands"
```

---

### Task 10: Version Bump + Docs

**Files:**
- Modify: `src/signalagent/__init__.py`
- Modify: `VERSION`
- Modify: `CHANGELOG.md`
- Modify: `docs/dev/roadmap.md`

- [ ] **Step 1: Bump version to 0.8.0**

In `src/signalagent/__init__.py`:
```python
__version__ = "0.8.0"
```

In `VERSION`:
```
0.8.0
```

- [ ] **Step 2: Update CHANGELOG**

Add to `CHANGELOG.md` before the `[0.7.0]` entry:

```markdown
## [0.8.0] - 2026-04-02

### Added
- SessionManager for JSONL-based conversation persistence (create, load, append, list)
- Turn and SessionSummary models for session data
- Message.history field for explicit conversation history transport
- Conversation history injection in AgenticRunner and PrimeAgent
- `signal chat` interactive REPL with session create/resume
- `signal sessions list` command for browsing recent sessions
- Session ID printed on start and exit for resumability

### Changed
- RunnerProtocol gains optional history parameter
- PrimeAgent._handle_directly() accepts conversation history
- Executor gains optional session_id for multi-turn persistence
- Bootstrap injects SessionManager into Executor
```

- [ ] **Step 3: Update roadmap**

In `docs/dev/roadmap.md`, change Phase 6 status:

```markdown
| 6 | Sessions + Conversation | Complete | JSONL session persistence, interactive REPL, conversation history injection |
```

- [ ] **Step 4: Run full test suite**

Run: `C:/Users/Sonny/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/__init__.py VERSION CHANGELOG.md docs/dev/roadmap.md
git commit -m "chore: bump to v0.8.0, update roadmap and changelog for Phase 6"
```
