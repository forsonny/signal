# Phase 5: Prompt Construction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Phase 2 memory engine into agent prompts via a pure-function builder that assembles token-budgeted system prompts.

**Architecture:** A `prompts/` package with two modules: `tokens.py` (LiteLLM wrapper for token counting) and `builder.py` (pure function that assembles identity + memories into a system prompt within a token budget). Agents retrieve memories via `MemoryReaderProtocol` from `core/protocols.py`, pass them to the builder, and feed the result to their runner. Bootstrap injects the concrete `MemoryEngine` as the protocol implementation.

**Tech Stack:** Python 3.11+, Pydantic v2, LiteLLM (token counting + model info), pytest + pytest-asyncio

---

## File Structure

```
src/signalagent/
  prompts/
    __init__.py           -- NEW (empty package init)
    tokens.py             -- NEW: count_tokens(), get_context_window()
    builder.py            -- NEW: build_system_prompt(), DEFAULT_MEMORY_LIMIT

  core/
    protocols.py          -- MODIFIED: add MemoryReaderProtocol

  agents/
    micro.py              -- MODIFIED: add memory_reader + model params, rename _build_system_prompt -> _build_identity, memory retrieval + builder call
    prime.py              -- MODIFIED: add memory_reader + model params, memory retrieval + builder call in _handle_directly

  runtime/
    bootstrap.py          -- MODIFIED: inject memory engine + model name into agents

tests/
  unit/
    prompts/
      __init__.py         -- NEW (empty)
      test_tokens.py      -- NEW: token utility tests
      test_builder.py     -- NEW: builder tests
    agents/
      test_micro.py       -- MODIFIED: add memory injection tests
      test_prime.py       -- MODIFIED: add memory injection tests
    core/
      test_protocols.py   -- MODIFIED: add MemoryReaderProtocol test
    runtime/
      test_bootstrap.py   -- MODIFIED: verify memory engine injection
```

---

### Task 1: MemoryReaderProtocol

**Files:**
- Modify: `src/signalagent/core/protocols.py:1-48`
- Modify: `tests/unit/core/test_protocols.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/core/test_protocols.py`:

```python
from signalagent.core.protocols import MemoryReaderProtocol


class TestMemoryReaderProtocol:
    def test_memory_engine_satisfies_protocol(self):
        """MemoryEngine must satisfy MemoryReaderProtocol at import time."""
        from signalagent.memory.engine import MemoryEngine
        assert issubclass(MemoryEngine, MemoryReaderProtocol)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/core/test_protocols.py::TestMemoryReaderProtocol -v`
Expected: FAIL with `ImportError: cannot import name 'MemoryReaderProtocol'`

- [ ] **Step 3: Add MemoryReaderProtocol to core/protocols.py**

Add after the `ToolExecutor` protocol at the end of `src/signalagent/core/protocols.py`:

```python
@runtime_checkable
class MemoryReaderProtocol(Protocol):
    """Protocol for memory retrieval so agents don't depend on concrete engine.
    Same pattern as AILayerProtocol -- agents import this, bootstrap injects
    the concrete MemoryEngine."""

    async def search(
        self,
        tags: list[str] | None = None,
        agent: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
        touch: bool = False,
    ) -> list[Any]: ...
```

**Important:** The parameter names and defaults must match `MemoryEngine.search()` at `src/signalagent/memory/engine.py:80-86` exactly. The current signature is:

```python
async def search(
    self,
    tags: list[str] | None = None,
    agent: str | None = None,
    memory_type: str | None = None,
    limit: int = 10,
    touch: bool = False,
) -> list[Memory]:
```

The protocol uses `list[Any]` return type (not `list[Memory]`) to avoid importing `Memory` into `core/protocols.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/core/test_protocols.py::TestMemoryReaderProtocol -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (257 existing + 1 new = 258 total)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/core/protocols.py tests/unit/core/test_protocols.py
git commit -m "feat: add MemoryReaderProtocol to core/protocols.py"
```

---

### Task 2: Token Utilities

**Files:**
- Create: `src/signalagent/prompts/__init__.py`
- Create: `src/signalagent/prompts/tokens.py`
- Create: `tests/unit/prompts/__init__.py`
- Create: `tests/unit/prompts/test_tokens.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/prompts/__init__.py` (empty file).

Create `tests/unit/prompts/test_tokens.py`:

```python
"""Unit tests for token counting utilities."""
import pytest
from unittest.mock import patch, MagicMock

from signalagent.prompts.tokens import count_tokens, get_context_window


class TestCountTokens:
    def test_returns_token_count(self):
        """count_tokens delegates to litellm.token_counter."""
        with patch("signalagent.prompts.tokens.litellm") as mock_litellm:
            mock_litellm.token_counter.return_value = 42
            result = count_tokens("hello world", "anthropic/claude-sonnet-4-20250514")
            assert result == 42
            mock_litellm.token_counter.assert_called_once_with(
                model="anthropic/claude-sonnet-4-20250514", text="hello world",
            )

    def test_empty_string_returns_zero_or_low(self):
        """Empty string should return 0 or very low token count."""
        with patch("signalagent.prompts.tokens.litellm") as mock_litellm:
            mock_litellm.token_counter.return_value = 0
            result = count_tokens("", "test-model")
            assert result == 0


class TestGetContextWindow:
    def test_returns_max_input_tokens(self):
        """get_context_window returns the model's max_input_tokens."""
        with patch("signalagent.prompts.tokens.litellm") as mock_litellm:
            mock_litellm.get_model_info.return_value = {
                "max_input_tokens": 200000,
                "max_output_tokens": 4096,
            }
            result = get_context_window("anthropic/claude-sonnet-4-20250514")
            assert result == 200000
            mock_litellm.get_model_info.assert_called_once_with(
                "anthropic/claude-sonnet-4-20250514",
            )

    def test_raises_on_unknown_model(self):
        """Unknown model should propagate the LiteLLM error."""
        with patch("signalagent.prompts.tokens.litellm") as mock_litellm:
            mock_litellm.get_model_info.side_effect = Exception("Unknown model")
            with pytest.raises(Exception, match="Unknown model"):
                get_context_window("nonexistent/model")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/prompts/test_tokens.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalagent.prompts'`

- [ ] **Step 3: Create the prompts package and tokens module**

Create `src/signalagent/prompts/__init__.py` (empty file).

Create `src/signalagent/prompts/tokens.py`:

```python
"""Token counting utilities -- thin wrapper around LiteLLM.

Isolates LiteLLM's token API so callers don't depend on it directly.
If LiteLLM's interface changes, only this file needs updating.
"""

from __future__ import annotations

import litellm


def count_tokens(text: str, model: str) -> int:
    """Count tokens for text using the model's tokenizer."""
    return litellm.token_counter(model=model, text=text)


def get_context_window(model: str) -> int:
    """Get the model's max input token limit.

    Uses max_input_tokens (the input context window), NOT
    get_max_tokens() which returns max output tokens.
    """
    info = litellm.get_model_info(model)
    return info["max_input_tokens"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/prompts/test_tokens.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (258 existing + 4 new = 262 total)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/prompts/__init__.py src/signalagent/prompts/tokens.py tests/unit/prompts/__init__.py tests/unit/prompts/test_tokens.py
git commit -m "feat: add token counting utilities (prompts/tokens.py)"
```

---

### Task 3: PromptBuilder

**Files:**
- Create: `src/signalagent/prompts/builder.py`
- Create: `tests/unit/prompts/test_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/prompts/test_builder.py`:

```python
"""Unit tests for build_system_prompt -- pure function, no mocking needed."""
from datetime import datetime, timezone
from unittest.mock import patch

from signalagent.core.models import Memory
from signalagent.core.types import MemoryType
from signalagent.prompts.builder import build_system_prompt, DEFAULT_MEMORY_LIMIT


def _make_memory(
    content: str = "Test memory content",
    memory_type: MemoryType = MemoryType.LEARNING,
    tags: list[str] | None = None,
) -> Memory:
    now = datetime.now(timezone.utc)
    return Memory(
        id="mem_test0001",
        agent="test-agent",
        type=memory_type,
        tags=tags or ["test"],
        content=content,
        confidence=0.8,
        version=1,
        created=now,
        updated=now,
        accessed=now,
        access_count=0,
    )


def _stub_count_tokens(text: str, model: str) -> int:
    """Approximate: 1 token per 4 characters."""
    return len(text) // 4


def _stub_context_window(model: str) -> int:
    """Return a small context window for testing."""
    return 1000


class TestBuildSystemPrompt:
    def test_identity_only_when_no_memories(self):
        """No memories -> returns identity unchanged."""
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=1000):
            result = build_system_prompt("You are a test agent.", [], "test-model")
        assert result == "You are a test agent."
        assert "## Context" not in result

    def test_includes_memories_with_context_header(self):
        """Memories get included under a ## Context header."""
        mem = _make_memory(content="Important fact", tags=["python"])
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=1000):
            result = build_system_prompt("You are a test agent.", [mem], "test-model")
        assert "## Context" in result
        assert "Important fact" in result
        assert "You are a test agent." in result

    def test_memory_format_with_tags(self):
        """Memory heading includes type and first tag."""
        mem = _make_memory(content="Some content", memory_type=MemoryType.PATTERN, tags=["refactoring", "python"])
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=1000):
            result = build_system_prompt("Identity.", [mem], "test-model")
        assert "### pattern: refactoring" in result
        assert "Some content" in result

    def test_memory_format_without_tags(self):
        """Memory with empty tags uses type only as heading."""
        mem = _make_memory(content="No tag content", tags=[])
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=1000):
            result = build_system_prompt("Identity.", [mem], "test-model")
        assert "### learning" in result
        assert ": " not in result.split("### learning")[1].split("\n")[0]

    def test_budget_truncation_drops_excess_memories(self):
        """Memories that exceed budget are dropped (whole-memory truncation)."""
        small_mem = _make_memory(content="short")
        big_mem = _make_memory(content="x" * 2000)  # ~500 tokens, won't fit
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=200):
            result = build_system_prompt("Id.", [small_mem, big_mem], "test-model",
                                         response_reserve=50)
        assert "short" in result
        assert "x" * 2000 not in result

    def test_no_budget_returns_identity_only(self):
        """When response_reserve exceeds context window, return identity only."""
        mem = _make_memory(content="Should not appear")
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=100):
            result = build_system_prompt("A" * 400, [mem], "test-model",
                                         response_reserve=100)
        assert result == "A" * 400
        assert "Should not appear" not in result

    def test_identity_comes_first(self):
        """Identity text appears before context section."""
        mem = _make_memory(content="Memory text")
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=1000):
            result = build_system_prompt("Identity first.", [mem], "test-model")
        identity_pos = result.index("Identity first.")
        context_pos = result.index("## Context")
        assert identity_pos < context_pos

    def test_multiple_memories_in_order(self):
        """Memories are included in the order provided (score order from engine)."""
        mem1 = _make_memory(content="First memory", tags=["a"])
        mem2 = _make_memory(content="Second memory", tags=["b"])
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=2000):
            result = build_system_prompt("Id.", [mem1, mem2], "test-model")
        pos1 = result.index("First memory")
        pos2 = result.index("Second memory")
        assert pos1 < pos2

    def test_default_memory_limit_is_defined(self):
        """DEFAULT_MEMORY_LIMIT exists and is a positive integer."""
        assert isinstance(DEFAULT_MEMORY_LIMIT, int)
        assert DEFAULT_MEMORY_LIMIT > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/prompts/test_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalagent.prompts.builder'`

- [ ] **Step 3: Implement the builder**

Create `src/signalagent/prompts/builder.py`:

```python
"""Prompt builder -- pure function for token-budgeted system prompt assembly.

Takes an identity string and pre-retrieved memories, assembles them into
a system prompt that fits within the model's context window. No I/O,
no engine dependency, no state.
"""

from __future__ import annotations

from signalagent.core.models import Memory
from signalagent.prompts.tokens import count_tokens, get_context_window

DEFAULT_MEMORY_LIMIT = 20


def _format_memory(memory: Memory) -> str:
    """Format a single memory as a prompt block."""
    if memory.tags:
        heading = f"### {memory.type.value}: {memory.tags[0]}"
    else:
        heading = f"### {memory.type.value}"
    return f"{heading}\n{memory.content}"


def build_system_prompt(
    identity: str,
    memories: list[Memory],
    model: str,
    response_reserve: int = 1500,
) -> str:
    """Assemble a token-budgeted system prompt from identity + memories.

    Args:
        identity: The agent's static identity string (name, skill, instructions).
        memories: Pre-retrieved memories, sorted by relevance score (from engine).
        model: LiteLLM model string for token counting.
        response_reserve: Tokens reserved for user message + LLM response.

    Returns:
        Assembled system prompt: identity first, then context section with
        memories that fit within budget. If no memories fit, returns identity
        unchanged.
    """
    if not memories:
        return identity

    context_window = get_context_window(model)
    identity_tokens = count_tokens(identity, model)
    budget = context_window - identity_tokens - response_reserve

    if budget <= 0:
        return identity

    included: list[str] = []
    for memory in memories:
        block = _format_memory(memory)
        block_tokens = count_tokens(block, model)
        if block_tokens > budget:
            continue
        included.append(block)
        budget -= block_tokens

    if not included:
        return identity

    context_section = "\n\n## Context\n\n" + "\n\n".join(included)
    return identity + context_section
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/prompts/test_builder.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (262 existing + 9 new = 271 total)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/prompts/builder.py tests/unit/prompts/test_builder.py
git commit -m "feat: add prompt builder with token-budgeted memory assembly"
```

---

### Task 4: MicroAgent Memory Integration

**Files:**
- Modify: `src/signalagent/agents/micro.py:1-45`
- Modify: `tests/unit/agents/test_micro.py:1-72`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/agents/test_micro.py`. First, update the imports at the top of the file to include the new dependencies:

```python
"""Unit tests for MicroAgent -- mock runner only."""
import pytest
from unittest.mock import AsyncMock

from signalagent.agents.micro import MicroAgent
from signalagent.core.models import MicroAgentConfig, Memory, Message
from signalagent.core.types import AgentType, MemoryType, MessageType
from signalagent.runtime.runner import RunnerResult

from datetime import datetime, timezone
```

Add a helper to create test memories:

```python
def _make_memory(content="Relevant context", tags=None):
    now = datetime.now(timezone.utc)
    return Memory(
        id="mem_test0001", agent="code-review", type=MemoryType.LEARNING,
        tags=tags or ["code"], content=content, confidence=0.8, version=1,
        created=now, updated=now, accessed=now, access_count=0,
    )
```

Add the new test class:

```python
class TestMicroAgentMemoryIntegration:
    @pytest.mark.asyncio
    async def test_retrieves_memories_and_enriches_prompt(self):
        """When memory_reader is provided, system prompt includes memories."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(return_value=[_make_memory()])

        agent = MicroAgent(
            config=_make_config(), runner=mock_runner,
            memory_reader=mock_reader, model="test-model",
        )
        await agent._handle(_make_task_message())

        mock_reader.search.assert_called_once()
        call_kwargs = mock_reader.search.call_args.kwargs
        assert call_kwargs["agent"] == "code-review"

        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "Relevant context" in system_prompt
        assert "## Context" in system_prompt

    @pytest.mark.asyncio
    async def test_no_memory_reader_uses_identity_only(self):
        """Without memory_reader, prompt is the static identity string."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())

        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        await agent._handle(_make_task_message())

        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "code-review" in system_prompt
        assert "## Context" not in system_prompt

    @pytest.mark.asyncio
    async def test_memory_search_failure_proceeds_without_context(self):
        """If memory search fails, agent proceeds with identity-only prompt."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(side_effect=Exception("DB error"))

        agent = MicroAgent(
            config=_make_config(), runner=mock_runner,
            memory_reader=mock_reader, model="test-model",
        )
        result = await agent._handle(_make_task_message())

        assert result is not None
        assert result.content == "Review complete."
        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "## Context" not in system_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/agents/test_micro.py::TestMicroAgentMemoryIntegration -v`
Expected: FAIL with `TypeError: MicroAgent.__init__() got an unexpected keyword argument 'memory_reader'`

- [ ] **Step 3: Update MicroAgent**

Replace the full content of `src/signalagent/agents/micro.py`:

```python
"""MicroAgent -- skill-based specialist agent."""
from __future__ import annotations

import logging

from signalagent.agents.base import BaseAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.protocols import MemoryReaderProtocol, RunnerProtocol
from signalagent.core.types import AgentType, MessageType
from signalagent.prompts.builder import build_system_prompt, DEFAULT_MEMORY_LIMIT

logger = logging.getLogger(__name__)


class MicroAgent(BaseAgent):
    """Specialist agent that handles tasks using a skill-based system prompt.
    Delegates all LLM interaction to an injected RunnerProtocol."""

    def __init__(
        self,
        config: MicroAgentConfig,
        runner: RunnerProtocol,
        memory_reader: MemoryReaderProtocol | None = None,
        model: str = "",
    ) -> None:
        super().__init__(name=config.name, agent_type=AgentType.MICRO)
        self._config = config
        self._runner = runner
        self._memory_reader = memory_reader
        self._model = model

    @property
    def skill(self) -> str:
        return self._config.skill

    def _build_identity(self) -> str:
        return (
            f"You are {self._config.name}, a specialist micro-agent "
            f"in the Signal system.\n\n"
            f"Your skill: {self._config.skill}\n\n"
            "You receive tasks from the Prime agent. "
            "Complete the task and return your results."
        )

    async def _handle(self, message: Message) -> Message | None:
        memories = []
        if self._memory_reader:
            try:
                memories = await self._memory_reader.search(
                    agent=self._config.name, limit=DEFAULT_MEMORY_LIMIT,
                )
            except Exception:
                logger.warning("Memory retrieval failed, proceeding without context")

        if memories and self._model:
            system_prompt = build_system_prompt(
                identity=self._build_identity(),
                memories=memories,
                model=self._model,
            )
        else:
            system_prompt = self._build_identity()

        result = await self._runner.run(
            system_prompt=system_prompt,
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

- [ ] **Step 4: Fix existing tests that reference _system_prompt**

The existing `test_system_prompt_contains_name_and_skill` test in `TestMicroAgentConstruction` accesses `agent._system_prompt` which no longer exists. Update it to test `_build_identity()` instead:

In `tests/unit/agents/test_micro.py`, replace the test method `test_system_prompt_contains_name_and_skill`:

```python
    def test_identity_contains_name_and_skill(self):
        agent = MicroAgent(config=_make_config(name="code-review", skill="Code quality"), runner=AsyncMock())
        identity = agent._build_identity()
        assert "code-review" in identity
        assert "Code quality" in identity
        assert "specialist micro-agent" in identity
```

- [ ] **Step 5: Run all micro agent tests**

Run: `pytest tests/unit/agents/test_micro.py -v`
Expected: PASS (3 existing + 3 new = 6 tests)

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (271 existing + 3 new = 274, minus any renaming adjustments)

- [ ] **Step 7: Commit**

```bash
git add src/signalagent/agents/micro.py tests/unit/agents/test_micro.py
git commit -m "feat: add memory injection to MicroAgent via MemoryReaderProtocol"
```

---

### Task 5: PrimeAgent Memory Integration

**Files:**
- Modify: `src/signalagent/agents/prime.py:1-126`
- Modify: `tests/unit/agents/test_prime.py:1-253`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/agents/test_prime.py`. First, update the imports at the top of the file:

```python
"""Unit tests for PrimeAgent -- mock AILayer, real bus, stub micro-agents."""

import pytest
from unittest.mock import AsyncMock

from signalagent.agents.base import BaseAgent
from signalagent.agents.host import AgentHost
from signalagent.agents.prime import PrimeAgent
from signalagent.ai.layer import AIResponse
from signalagent.comms.bus import MessageBus
from signalagent.core.models import Memory, Message
from signalagent.core.types import (
    AgentType,
    MemoryType,
    MessageType,
    PRIME_AGENT,
    USER_SENDER,
)

from datetime import datetime, timezone
```

Add a memory helper and update `_register_prime` to accept `memory_reader` and `model`:

```python
def _make_memory(content="Prime context", tags=None):
    now = datetime.now(timezone.utc)
    return Memory(
        id="mem_test0001", agent="prime", type=MemoryType.LEARNING,
        tags=tags or ["general"], content=content, confidence=0.8, version=1,
        created=now, updated=now, accessed=now, access_count=0,
    )


def _register_prime(
    host: AgentHost,
    bus: MessageBus,
    mock_ai: AsyncMock,
    identity: str = "You are a test prime.",
    memory_reader=None,
    model: str = "",
) -> PrimeAgent:
    prime = PrimeAgent(
        identity=identity, ai=mock_ai, host=host, bus=bus,
        memory_reader=memory_reader, model=model,
    )
    host.register(prime, talks_to=None)
    return prime
```

Add the new test class:

```python
class TestMemoryIntegration:
    @pytest.mark.asyncio
    async def test_handle_directly_enriches_prompt_with_memories(self, host, bus):
        """When memory_reader is provided, direct handling includes memories."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("response"))
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(return_value=[_make_memory()])

        _register_prime(host, bus, mock_ai, memory_reader=mock_reader, model="test-model")

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="hello",
        )
        await bus.send(msg)

        mock_reader.search.assert_called_once()
        call_kwargs = mock_reader.search.call_args.kwargs
        assert call_kwargs["agent"] == "prime"

        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        system_content = call_messages[0]["content"]
        assert "## Context" in system_content
        assert "Prime context" in system_content

    @pytest.mark.asyncio
    async def test_routing_does_not_use_memories(self, host, bus):
        """Routing prompt should NOT include memories."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("code-review"),
        )
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(return_value=[_make_memory()])

        _register_prime(host, bus, mock_ai, memory_reader=mock_reader, model="test-model")
        _register_stub_micro(host, "code-review")

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="review code",
        )
        await bus.send(msg)

        # Routing succeeded (AI returned "code-review"), so Prime dispatched
        # to the micro-agent and never entered _handle_directly() where
        # memory search happens. assert_not_called() is valid because this
        # test verifies routing doesn't trigger memory retrieval -- NOT that
        # Prime never uses memories (see test_handle_directly_enriches_prompt).
        mock_reader.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_memory_reader_uses_identity_only(self, host, bus):
        """Without memory_reader, direct handling uses raw identity."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("response"))

        _register_prime(host, bus, mock_ai)

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="hello",
        )
        await bus.send(msg)

        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        system_content = call_messages[0]["content"]
        assert system_content == "You are a test prime."
        assert "## Context" not in system_content

    @pytest.mark.asyncio
    async def test_memory_search_failure_proceeds_without_context(self, host, bus):
        """If memory search fails, Prime proceeds with identity-only prompt."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("response"))
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(side_effect=Exception("DB error"))

        _register_prime(host, bus, mock_ai, memory_reader=mock_reader, model="test-model")

        msg = Message(
            type=MessageType.TASK, sender=USER_SENDER,
            recipient=PRIME_AGENT, content="hello",
        )
        result = await bus.send(msg)

        assert result is not None
        assert result.content == "response"
        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        system_content = call_messages[0]["content"]
        assert "## Context" not in system_content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/agents/test_prime.py::TestMemoryIntegration -v`
Expected: FAIL with `TypeError: PrimeAgent.__init__() got an unexpected keyword argument 'memory_reader'`

- [ ] **Step 3: Update PrimeAgent**

Replace the full content of `src/signalagent/agents/prime.py`:

```python
"""PrimeAgent -- LLM-based routing with direct handling fallback."""

from __future__ import annotations

import logging

from signalagent.agents.base import BaseAgent
from signalagent.agents.host import AgentHost
from signalagent.comms.bus import MessageBus
from signalagent.core.models import Message
from signalagent.core.types import (
    AgentType,
    MessageType,
    PRIME_AGENT,
    USER_SENDER,
)
from signalagent.core.protocols import AILayerProtocol, MemoryReaderProtocol
from signalagent.prompts.builder import build_system_prompt, DEFAULT_MEMORY_LIMIT

logger = logging.getLogger(__name__)


class PrimeAgent(BaseAgent):
    """Prime agent: routes tasks to micro-agents or handles directly.

    Routing uses an LLM call to decide which micro-agent should handle
    the user's message. If no match, if the LLM returns garbage, or if
    the routing call itself fails, Prime handles the request directly
    using its own identity prompt.
    """

    def __init__(
        self,
        identity: str,
        ai: AILayerProtocol,
        host: AgentHost,
        bus: MessageBus,
        memory_reader: MemoryReaderProtocol | None = None,
        model: str = "",
    ) -> None:
        super().__init__(name=PRIME_AGENT, agent_type=AgentType.PRIME)
        self._identity = identity
        self._ai = ai
        self._host = host
        self._bus = bus
        self._memory_reader = memory_reader
        self._model = model

    async def _handle(self, message: Message) -> Message | None:
        """Route to micro-agent or handle directly."""
        micro_agents = self._host.list_micro_agents()

        if not micro_agents:
            content = await self._handle_directly(message.content)
        else:
            target = await self._route(message.content, micro_agents)
            if target is not None:
                # Dispatch to micro-agent via bus
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
                content = await self._handle_directly(message.content)

        return Message(
            type=MessageType.RESULT,
            sender=PRIME_AGENT,
            recipient=message.sender,
            content=content,
            parent_id=message.id,
        )

    async def _route(
        self,
        user_content: str,
        micro_agents: list[BaseAgent],
    ) -> str | None:
        """LLM routing call. Returns micro-agent name or None.

        If the routing call fails, catches the exception and returns None.
        Routing failure must never crash Prime.
        No memory injection -- routing is classification, not knowledge.
        """
        agent_list = "\n".join(
            f"- {a.name}: {a.skill}"
            for a in micro_agents
        )
        n = len(micro_agents)
        routing_prompt = (
            "You are a routing agent. Given the user's message and the "
            "available specialist agents below, decide which agent should "
            "handle this task.\n\n"
            f"Available agents ({n}):\n"
            f"{agent_list}\n\n"
            "If none of the agents are a good fit, respond with: NONE\n\n"
            "Otherwise respond with exactly the agent name, nothing else.\n\n"
            f"User message: {user_content}"
        )

        try:
            response = await self._ai.complete(
                messages=[{"role": "user", "content": routing_prompt}],
            )
        except Exception:
            logger.warning("Routing LLM call failed, falling back to direct handling")
            return None

        choice = response.content.strip().lower()

        if choice == "none" or not choice:
            return None

        # Case-insensitive match against registered micro-agent names
        name_map = {a.name.lower(): a.name for a in micro_agents}
        return name_map.get(choice)

    async def _handle_directly(self, user_content: str) -> str:
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
        else:
            system_prompt = self._identity

        response = await self._ai.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        return response.content
```

- [ ] **Step 4: Run all prime agent tests**

Run: `pytest tests/unit/agents/test_prime.py -v`
Expected: PASS (all existing tests still pass + 4 new memory tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (274 existing + 4 new = 278 total, approximately)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/agents/prime.py tests/unit/agents/test_prime.py
git commit -m "feat: add memory injection to PrimeAgent via MemoryReaderProtocol"
```

---

### Task 6: Bootstrap Wiring + Integration Tests

**Files:**
- Modify: `src/signalagent/runtime/bootstrap.py:1-133`
- Modify: `tests/unit/runtime/test_bootstrap.py:1-230`

- [ ] **Step 1: Write the failing integration test**

Add to `tests/unit/runtime/test_bootstrap.py`. First, update the imports at the top of the file:

```python
"""Unit tests for bootstrap -- all real objects, only AILayer mocked."""
import pytest
from unittest.mock import AsyncMock, patch

from signalagent.ai.layer import AIResponse
from signalagent.core.config import SignalConfig
from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
    PluginsConfig,
    HooksConfig,
    ToolCallRequest,
)
from signalagent.core.types import PRIME_AGENT
from signalagent.runtime.bootstrap import bootstrap
```

Add a new fixture and test class:

```python
@pytest.fixture
def profile_with_memory():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        micro_agents=[
            MicroAgentConfig(
                name="researcher", skill="Research",
                talks_to=["prime"],
            ),
        ],
    )


class TestMemoryInjection:
    @pytest.mark.asyncio
    async def test_agents_receive_memory_engine(self, tmp_path, config, profile_with_memory, monkeypatch):
        """Bootstrap injects memory engine into Prime and micro-agents."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("Done"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_memory)

        # Verify Prime has memory reader
        # NOTE: host.get() returns BaseAgent. Accessing _memory_reader is a
        # private attribute on PrimeAgent/MicroAgent. Use type: ignore to
        # suppress linter warnings -- this is test code verifying bootstrap wiring.
        prime = host.get(PRIME_AGENT)
        assert prime._memory_reader is not None  # type: ignore[union-attr]

        # Verify micro-agent has memory reader
        researcher = host.get("researcher")
        assert researcher._memory_reader is not None  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_agents_receive_model_name(self, tmp_path, config, profile_with_memory, monkeypatch):
        """Bootstrap passes model name to agents."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("Done"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_memory)

        # Same type: ignore as above -- host.get() returns BaseAgent,
        # _model is on the concrete agent types.
        prime = host.get(PRIME_AGENT)
        assert prime._model == config.ai.default_model  # type: ignore[union-attr]

        researcher = host.get("researcher")
        assert researcher._model == config.ai.default_model  # type: ignore[union-attr]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/runtime/test_bootstrap.py::TestMemoryInjection -v`
Expected: FAIL (PrimeAgent/MicroAgent don't receive memory_reader from bootstrap yet)

- [ ] **Step 3: Update bootstrap.py**

Modify `src/signalagent/runtime/bootstrap.py` to inject memory engine and model name. The full updated file:

```python
"""Bootstrap -- single wiring point for the multi-agent runtime."""
from __future__ import annotations
from pathlib import Path

from signalagent.agents.host import AgentHost
from signalagent.agents.micro import MicroAgent
from signalagent.agents.prime import PrimeAgent
from signalagent.ai.layer import AILayer
from signalagent.comms.bus import MessageBus
from signalagent.core.config import SignalConfig
from signalagent.core.models import Profile, ToolResult
from signalagent.hooks.builtins import load_builtin_hook
from signalagent.hooks.executor import HookExecutor
from signalagent.hooks.registry import HookRegistry
from signalagent.memory.engine import MemoryEngine
from signalagent.runtime.executor import Executor
from signalagent.runtime.runner import AgenticRunner
from signalagent.tools.builtins import load_builtin_tool
from signalagent.tools.builtins.spawn_sub_agent import SpawnSubAgentTool
from signalagent.tools.registry import ToolRegistry


async def bootstrap(
    instance_dir: Path,
    config: SignalConfig,
    profile: Profile,
) -> tuple[Executor, MessageBus, AgentHost]:
    """Wire up the full multi-agent runtime."""
    ai = AILayer(config)
    bus = MessageBus()
    host = AgentHost(bus)

    # Memory engine
    engine = MemoryEngine(instance_dir)
    await engine.initialize()

    model_name = config.ai.default_model

    # Tool registry
    registry = ToolRegistry()
    for tool_name in profile.plugins.available:
        tool = load_builtin_tool(tool_name, instance_dir)
        if tool is not None:
            registry.register(tool)

    # Inner tool executor -- registry lookup + error handling
    async def inner_executor(tool_name: str, arguments: dict) -> ToolResult:
        tool = registry.get(tool_name)
        if tool is None:
            return ToolResult(output="", error=f"Unknown tool: {tool_name}")
        try:
            return await tool.execute(**arguments)
        except Exception as e:
            return ToolResult(output="", error=str(e))

    # Hook registry
    hook_registry = HookRegistry()
    for hook_name in profile.hooks.active:
        hook = load_builtin_hook(hook_name, instance_dir)
        if hook is not None:
            hook_registry.register(hook)

    # Wrap inner executor with hooks
    tool_executor = HookExecutor(inner=inner_executor, registry=hook_registry)

    global_max = config.tools.max_iterations

    # Prime agent -- no agentic tool loop. If Prime gains tools in a
    # future phase, apply global_max cap here too.
    prime = PrimeAgent(
        identity=profile.prime.identity, ai=ai, host=host, bus=bus,
        memory_reader=engine, model=model_name,
    )
    host.register(prime, talks_to=None)

    # Micro-agents with runners
    for micro_config in profile.micro_agents:
        agent_max = min(micro_config.max_iterations, global_max)
        tool_schemas = registry.get_schemas(micro_config.plugins)

        if micro_config.can_spawn_subs:
            # Sub-agent runner factory: uses parent's tools (no spawn)
            async def run_sub(
                system_prompt: str, task: str,
                _schemas=tool_schemas, _max=agent_max,
            ) -> str:
                sub_runner = AgenticRunner(
                    ai=ai, tool_executor=tool_executor,
                    tool_schemas=_schemas, max_iterations=_max,
                )
                result = await sub_runner.run(
                    system_prompt=system_prompt, user_content=task,
                )
                return result.content

            # Create spawn tool
            spawn_tool = SpawnSubAgentTool(
                run_sub=run_sub, parent_name=micro_config.name,
            )

            # Per-agent executor: intercepts spawn, delegates rest to shared
            async def agent_inner(
                tool_name: str, arguments: dict,
                _spawn=spawn_tool, _shared=inner_executor,
            ) -> ToolResult:
                if tool_name == _spawn.name:
                    return await _spawn.execute(**arguments)
                return await _shared(tool_name, arguments)

            # Wrap with hooks
            agent_executor = HookExecutor(
                inner=agent_inner, registry=hook_registry,
            )

            # Append spawn schema to full list
            full_schemas = list(tool_schemas)
            full_schemas.append({
                "type": "function",
                "function": {
                    "name": spawn_tool.name,
                    "description": spawn_tool.description,
                    "parameters": spawn_tool.parameters,
                },
            })

            runner = AgenticRunner(
                ai=ai, tool_executor=agent_executor,
                tool_schemas=full_schemas, max_iterations=agent_max,
            )
        else:
            # No spawn capability -- use shared executor
            runner = AgenticRunner(
                ai=ai, tool_executor=tool_executor,
                tool_schemas=tool_schemas, max_iterations=agent_max,
            )

        agent = MicroAgent(
            config=micro_config, runner=runner,
            memory_reader=engine, model=model_name,
        )
        talks_to = set(micro_config.talks_to)
        host.register(agent, talks_to=talks_to)

    executor = Executor(bus=bus)
    return executor, bus, host
```

The changes from the previous version:
- Added `from signalagent.memory.engine import MemoryEngine`
- Added `engine = MemoryEngine(instance_dir)` and `await engine.initialize()`
- Added `model_name = config.ai.default_model`
- Added `memory_reader=engine, model=model_name` to `PrimeAgent()`
- Added `memory_reader=engine, model=model_name` to `MicroAgent()`

- [ ] **Step 4: Run bootstrap tests**

Run: `pytest tests/unit/runtime/test_bootstrap.py -v`
Expected: PASS (all existing tests + 2 new memory injection tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (278 existing + 2 new = 280 total, approximately)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/runtime/bootstrap.py tests/unit/runtime/test_bootstrap.py
git commit -m "feat: bootstrap injects memory engine and model name into agents"
```

---

### Task 7: Version Bump + Docs Update

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/dev/roadmap.md`

- [ ] **Step 1: Bump version to 0.7.0**

In `pyproject.toml`, update the version field:

```toml
version = "0.7.0"
```

- [ ] **Step 2: Update roadmap**

In `docs/dev/roadmap.md`, mark Phase 5 as complete and note the deliverables:
- `prompts/tokens.py` -- LiteLLM token counting wrapper
- `prompts/builder.py` -- pure-function system prompt assembly with token budgeting
- `MemoryReaderProtocol` in `core/protocols.py`
- Memory injection in `MicroAgent` and `PrimeAgent`
- Bootstrap wires memory engine into all agents

- [ ] **Step 3: Run full test suite one final time**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml docs/dev/roadmap.md
git commit -m "chore: bump to v0.7.0, update roadmap for Phase 5"
```
