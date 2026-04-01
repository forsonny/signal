# Phase 5: Prompt Construction -- Design Spec

## Goal

Wire the Phase 2 memory engine into agent prompts. Agents retrieve relevant memories, a pure-function builder assembles them into token-budgeted system prompts, and the LLM receives enriched context. Single-turn only -- no conversation history management.

## Architecture

Phase 5 adds one new package and modifies three existing modules:

**New:**
- `prompts/tokens.py` -- thin wrapper around LiteLLM token counting
- `prompts/builder.py` -- pure function `build_system_prompt()` for context assembly

**Modified:**
- `core/protocols.py` -- `MemoryReaderProtocol` (agents depend on abstraction, not concrete engine)
- `agents/prime.py` -- memory retrieval + builder call in `_handle_directly()`
- `agents/micro.py` -- memory retrieval + builder call in `_handle()`, rename `_build_system_prompt()` to `_build_identity()`
- `runtime/bootstrap.py` -- inject memory engine and model name into agents

### Flow

```
MicroAgent._handle(message)
  |
  memory_reader.search(agent=self.name, limit=DEFAULT_MEMORY_LIMIT)
  |
  build_system_prompt(identity, memories, model)
  |
  runner.run(system_prompt, user_content)  # interface unchanged
  |
  AgenticRunner -> AILayer -> LLM (receives enriched system prompt)
```

Prime follows the same pattern in `_handle_directly()`. Prime's `_route()` does NOT get memory injection -- routing is a classification task, not a knowledge task.

Sub-agents (Phase 4c) get `memory_reader=None` -- they are ephemeral and stateless by design.

### Dependency Graph

```
prompts/tokens.py   --> litellm (only LiteLLM dependency for token ops)
prompts/builder.py  --> prompts/tokens, core/models (Memory type only)
agents/prime.py     --> core/protocols (MemoryReaderProtocol), prompts/builder
agents/micro.py     --> core/protocols (MemoryReaderProtocol), prompts/builder
runtime/bootstrap.py --> memory/engine, agents (injects engine as MemoryReaderProtocol)
```

`agents/` never imports `memory/`. The protocol in `core/protocols.py` maintains the dependency boundary.

---

## Components

### 1. Token Utilities (prompts/tokens.py)

Thin wrapper isolating LiteLLM's token counting API:

```python
def count_tokens(text: str, model: str) -> int:
    """Count tokens for text using the model's tokenizer."""
    return litellm.token_counter(model=model, text=text)

def get_context_window(model: str) -> int:
    """Get the model's max input token limit."""
    info = litellm.get_model_info(model)
    return info["max_input_tokens"]
```

**Why a wrapper:** LiteLLM's API has changed across versions. One file to update instead of every call site. Tests for the builder stub these two functions instead of mocking LiteLLM internals.

**Important:** `get_context_window()` uses `max_input_tokens` (the input context window, typically 128-200K), NOT `get_max_tokens()` which returns max output tokens (typically 4-8K). Getting this wrong would make the budget calculation think the model has ~4K total context, and almost no memories would ever fit.

### 2. PromptBuilder (prompts/builder.py)

Pure function -- no state, no I/O, no engine dependency:

```python
DEFAULT_MEMORY_LIMIT = 20

def build_system_prompt(
    identity: str,
    memories: list[Memory],
    model: str,
    response_reserve: int = 1500,
) -> str:
```

**Algorithm:**

1. Count tokens for `identity` via `count_tokens(identity, model)`
2. Get context window via `get_context_window(model)`
3. Compute available budget: `context_window - identity_tokens - response_reserve`
4. If budget <= 0: return `identity` unchanged (no room for memories)
5. Iterate through `memories` (pre-sorted by score from engine):
   - Format memory as a block (see format below)
   - Count its tokens
   - If adding it would exceed budget: stop
   - Otherwise: append to context list, subtract tokens from budget
6. If no memories fit: return `identity` unchanged
7. Return: `identity + "\n\n## Context\n\n" + formatted_memories`

**Memory formatting:**

Each memory becomes:

```
### {memory.type.value}: {first_tag}
{memory.content}
```

When `memory.tags` is empty:

```
### {memory.type.value}
{memory.content}
```

Minimal metadata -- enough for the LLM to understand what kind of context it's reading without wasting tokens on fields it won't use.

**Edge cases:**
- Empty memories list: returns `identity`
- Budget exhausted by identity alone: returns `identity`
- All memories too large to fit: returns `identity`
- Single memory fits: includes it with the `## Context` header

### 3. MemoryReaderProtocol (core/protocols.py)

```python
@runtime_checkable
class MemoryReaderProtocol(Protocol):
    async def search(
        self,
        tags: list[str] | None = None,
        agent: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
        touch: bool = False,
    ) -> list[Any]: ...
```

Same pattern as `AILayerProtocol` and `RunnerProtocol` -- agents depend on the protocol, bootstrap injects the concrete `MemoryEngine`.

**Implementation note:** The protocol's parameter names must match `MemoryEngine.search()` exactly. Python's protocol checking validates signatures. Verify at implementation time that Phase 2's `MemoryEngine.search()` signature agrees -- particularly the `memory_type` parameter name.

### 4. Agent Changes

**MicroAgent (agents/micro.py):**

- `_build_system_prompt()` renamed to `_build_identity()` -- returns the static identity string (name, skill, instructions)
- Constructor gains `memory_reader: MemoryReaderProtocol | None = None` and `model: str = ""`
- In `_handle()`: retrieves memories with error handling, passes to `build_system_prompt()`, feeds result to runner:

```python
memories = []
if self._memory_reader:
    try:
        memories = await self._memory_reader.search(
            agent=self._config.name, limit=DEFAULT_MEMORY_LIMIT,
        )
    except Exception:
        logger.warning("Memory retrieval failed, proceeding without context")

system_prompt = build_system_prompt(
    identity=self._build_identity(),
    memories=memories,
    model=self._model,
)
```

**PrimeAgent (agents/prime.py):**

- Constructor gains `memory_reader: MemoryReaderProtocol | None = None` and `model: str = ""`
- In `_handle_directly()`: same try/except pattern around `memory_reader.search(agent="prime", limit=DEFAULT_MEMORY_LIMIT)`, passes to `build_system_prompt()`, uses result as system message
- `_route()` is unchanged -- no memory injection for routing decisions

**Both agents:** When `memory_reader is None`, behavior is identical to pre-Phase 5 (static prompts, no memory retrieval). This keeps sub-agents and tests working without memory infrastructure.

### 5. Bootstrap Wiring (runtime/bootstrap.py)

```python
# Already exists from Phase 2
engine = await MemoryEngine.create(instance_dir / "memory")

model_name = config.ai.default_model

# Prime
prime = PrimeAgent(
    identity=profile.prime.identity, ai=ai, host=host, bus=bus,
    memory_reader=engine, model=model_name,
)

# Micro-agents
agent = MicroAgent(
    config=micro_config, runner=runner,
    memory_reader=engine, model=model_name,
)
```

`MemoryEngine` already satisfies `MemoryReaderProtocol` (it has `search()` with the right signature). No adapter needed.

Sub-agents from Phase 4c get `memory_reader=None` -- ephemeral, no context injection. The `run_sub` closure in bootstrap does not pass memory to sub-agent runners.

---

## Error Handling

- **LiteLLM token counting fails:** `count_tokens()` or `get_context_window()` raises. The builder lets this propagate -- the agent's error handling (or runner's) catches it. No silent fallback to avoid serving prompts with wrong budgets. Rationale: a wrong budget is worse than a visible error.
- **Memory engine search fails:** Agent catches the exception and proceeds with empty memories. The builder receives an empty list and returns identity unchanged. Degraded but functional. Rationale: missing context is recoverable (agent still works, just less informed), unlike a wrong token budget.
- **Model not in LiteLLM's registry:** `get_model_info()` raises. Same as token counting failure -- propagates up. This is a configuration error, not a runtime condition.

---

## File Layout

```
src/signalagent/
  prompts/
    __init__.py           -- NEW (empty)
    tokens.py             -- NEW: count_tokens, get_context_window
    builder.py            -- NEW: build_system_prompt, DEFAULT_MEMORY_LIMIT

  core/
    protocols.py          -- MODIFIED: add MemoryReaderProtocol

  agents/
    prime.py              -- MODIFIED: memory retrieval + builder in _handle_directly()
    micro.py              -- MODIFIED: memory retrieval + builder in _handle(), rename to _build_identity()

  runtime/
    bootstrap.py          -- MODIFIED: inject memory engine + model name into agents

tests/
  unit/
    prompts/
      test_tokens.py      -- NEW: token counting wrapper tests
      test_builder.py     -- NEW: build_system_prompt tests
    agents/
      test_prime.py        -- MODIFIED: add memory injection tests
      test_micro.py        -- MODIFIED: add memory injection tests
    runtime/
      test_bootstrap.py    -- MODIFIED: verify memory engine injection
```

---

## Done-When Criteria

**(a)** `build_system_prompt()` is a pure function: takes identity string, list of memories, model string, response reserve int -- returns assembled system prompt string

**(b)** Token counting uses LiteLLM via `prompts/tokens.py` wrapper -- `count_tokens()` and `get_context_window()` isolate LiteLLM's API

**(c)** Budget auto-derived from model's input context window (`max_input_tokens`), not max output tokens

**(d)** Memories included whole, in score order, until budget full -- no partial inclusion, no summarization

**(e)** Memory formatting: `### {type}: {first_tag}` with tags, `### {type}` without -- each followed by content

**(f)** Zero memories or zero budget: builder returns identity unchanged

**(g)** `MemoryReaderProtocol` in `core/protocols.py` -- agents depend on protocol, bootstrap injects concrete `MemoryEngine`

**(h)** Protocol signature matches `MemoryEngine.search()` -- verified at implementation time

**(i)** `MicroAgent` retrieves its own memories via `memory_reader.search(agent=self.name)`, passes to builder

**(j)** `PrimeAgent._handle_directly()` retrieves memories via `memory_reader.search(agent="prime")`, passes to builder

**(k)** `PrimeAgent._route()` does NOT get memory injection -- routing is classification, not knowledge

**(l)** `DEFAULT_MEMORY_LIMIT` named constant in `prompts/builder.py`, no magic numbers in agent code

**(m)** Sub-agents get `memory_reader=None` -- ephemeral, no context injection

**(n)** `MicroAgent._build_system_prompt()` renamed to `_build_identity()` -- returns static identity string only

**(o)** `signal talk` works end-to-end: agent retrieves memories, builder assembles prompt with context, LLM receives enriched system prompt
