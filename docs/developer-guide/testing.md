# Testing

## What you'll learn

- How tests are organized and how to run them
- Patterns for testing each major subsystem (models, AI mocking, executors, CLI)
- Available fixtures and how to build mocks
- How to test async code with pytest-asyncio

---

## Test organization

### Directory layout

```
tests/
    conftest.py                  -- Shared fixtures
    unit/                        -- Unit tests (mirrors src/signalagent/)
        agents/
        ai/
        cli/
        comms/
        core/
        heartbeat/
        hooks/
        memory/
        prompts/
        runtime/
        security/
        sessions/
        tools/
        worktrees/
    integration/                 -- CLI integration tests
        test_cli.py
        test_memory_cli.py
```

Unit tests mirror the source tree: `src/signalagent/agents/prime.py` is
tested in `tests/unit/agents/test_prime.py`.

Integration tests exercise the CLI commands end-to-end using Typer's
`CliRunner`.

### Running tests

```bash
# Full suite
uv run pytest

# Single package
uv run pytest tests/unit/runtime/

# Single file
uv run pytest tests/unit/hooks/test_executor.py

# Single test
uv run pytest tests/unit/runtime/test_runner.py::TestRunnerWithTools::test_single_tool_call_then_final

# By keyword
uv run pytest -k "policy"
```

All tests use `asyncio_mode = "auto"` from `pyproject.toml`, so you do
not need to add `@pytest.mark.asyncio` manually (though it is harmless
to include it).

---

## Shared fixtures

The root `conftest.py` provides:

### `mock_ai_response`

Creates a `MagicMock` shaped like a LiteLLM response object:

```python
@pytest.fixture
def mock_ai_response():
    response = MagicMock()
    response.choices = [
        MagicMock(message=MagicMock(content="I'm Signal, ready to help!"))
    ]
    response.usage = MagicMock(prompt_tokens=20, completion_tokens=30)
    response.model = "anthropic/claude-sonnet-4-20250514"
    return response
```

This fixture is useful for tests that patch `litellm.acompletion`
directly. For higher-level tests, prefer building `AIResponse` objects
instead (see AI layer mocking below).

---

## Patterns by module

### Pydantic model tests

Test models by constructing them with valid and invalid data. Verify
that `extra="forbid"` rejects unknown fields:

```python
from pydantic import ValidationError
from signalagent.core.models import MicroAgentConfig

def test_micro_agent_config_valid():
    config = MicroAgentConfig(name="coder", skill="Write Python code")
    assert config.name == "coder"
    assert config.max_iterations == 10  # default

def test_micro_agent_config_rejects_extra_fields():
    with pytest.raises(ValidationError):
        MicroAgentConfig(name="coder", skill="code", unknown_field="bad")
```

### AI layer mocking

The most common pattern: create an `AsyncMock` that returns `AIResponse`
objects. Use `side_effect` for multi-turn conversations:

```python
from unittest.mock import AsyncMock
from signalagent.ai.layer import AIResponse
from signalagent.core.models import ToolCallRequest

def _make_text_response(content: str) -> AIResponse:
    return AIResponse(
        content=content, model="test", provider="test",
        input_tokens=10, output_tokens=20, tool_calls=[],
    )

def _make_tool_response(tool_calls: list[ToolCallRequest]) -> AIResponse:
    return AIResponse(
        content="", model="test", provider="test",
        input_tokens=10, output_tokens=20, tool_calls=tool_calls,
    )

class TestMyAgent:
    @pytest.mark.asyncio
    async def test_single_turn(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_text_response("hello")
        )
        # ... use mock_ai as the AILayerProtocol
```

For multi-step agentic loops, use `side_effect` to sequence tool-call
and text responses:

```python
mock_ai.complete = AsyncMock(side_effect=[
    _make_tool_response([
        ToolCallRequest(id="call_1", name="file_system",
                        arguments={"operation": "read", "path": "f.txt"}),
    ]),
    _make_text_response("File read successfully"),
])
```

### AgenticRunner tests

The runner takes an `AILayerProtocol` and a `ToolExecutor`. Both are
`AsyncMock` objects:

```python
from signalagent.runtime.runner import AgenticRunner
from signalagent.core.models import ToolResult

mock_executor = AsyncMock(return_value=ToolResult(output="ok"))
runner = AgenticRunner(
    ai=mock_ai, tool_executor=mock_executor,
    tool_schemas=[...], max_iterations=10,
)
result = await runner.run(system_prompt="sys", user_content="go")
assert result.iterations == 2
assert result.tool_calls_made == 1
```

Test error handling by making the executor return errors or raise:

```python
# Tool returns error
mock_executor = AsyncMock(
    return_value=ToolResult(output="", error="file not found")
)

# Tool raises exception
mock_executor = AsyncMock(side_effect=RuntimeError("crash"))
```

The runner catches both and feeds the error back to the LLM.

### Executor error boundary tests

The `Executor` wraps everything in a try/except. Test that exceptions
become `ExecutorResult.error`:

```python
from signalagent.runtime.executor import Executor

bus = MessageBus()
executor = Executor(bus=bus)
result = await executor.run("hello")
# If no agent is registered, bus.send raises RoutingError
assert result.error is not None
```

### HookExecutor tests

Test the before/after lifecycle with mock hooks:

```python
from signalagent.hooks.executor import HookExecutor
from signalagent.hooks.registry import HookRegistry

class BlockingHook:
    name = "blocker"
    async def before_tool_call(self, tool_name, arguments, agent=""):
        return ToolResult(output="", error="Blocked by policy")
    async def after_tool_call(self, tool_name, arguments, result, blocked, agent=""):
        pass

registry = HookRegistry()
registry.register(BlockingHook())
inner = AsyncMock(return_value=ToolResult(output="ok"))
executor = HookExecutor(inner=inner, registry=registry)

result = await executor("file_system", {"operation": "read", "path": "x"})
assert result.error == "Blocked by policy"
inner.assert_not_called()  # inner never runs when blocked
```

### CLI tests with CliRunner

CLI commands are tested with Typer's `CliRunner` and `patch` for
external dependencies:

```python
from typer.testing import CliRunner
from unittest.mock import patch
from signalagent.cli.app import app

runner = CliRunner()

def test_init_creates_instance(tmp_path):
    with patch("signalagent.cli.init_cmd.create_instance") as mock_create:
        result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
        assert result.exit_code == 0
```

### Multi-agent side_effect patterns

When testing Prime routing to micro-agents, mock the bus or use
`side_effect` to simulate the routing LLM call followed by the
micro-agent response:

```python
# Prime routing: LLM returns agent name
mock_ai.complete = AsyncMock(side_effect=[
    _make_text_response("coder"),           # routing decision
    _make_text_response("Task completed"),   # micro-agent response
])
```

### Tool and hook tests

Tools are tested by calling `execute()` directly:

```python
from signalagent.tools.builtins.file_system import FileSystemTool

tool = FileSystemTool(root=tmp_path)
result = await tool.execute(operation="write", path="test.txt", content="hello")
assert result.output == "Written: test.txt"

result = await tool.execute(operation="read", path="test.txt")
assert result.output == "hello"
```

Hooks are tested by calling `before_tool_call()` and `after_tool_call()`
directly, verifying return values and side effects (log files, audit
entries).

---

## Testing async code

All async test methods work automatically with `asyncio_mode = "auto"`.
Use `AsyncMock` from `unittest.mock` for async callables:

```python
from unittest.mock import AsyncMock

mock_fn = AsyncMock(return_value="result")
result = await mock_fn("arg1", "arg2")
mock_fn.assert_called_once_with("arg1", "arg2")
```

For `side_effect` sequences:

```python
mock_fn = AsyncMock(side_effect=[
    "first call",
    "second call",
    RuntimeError("third call fails"),
])
```

### Temporary directories

Use `tmp_path` (pytest built-in) for tests that need filesystem access:

```python
async def test_memory_engine(tmp_path):
    engine = MemoryEngine(tmp_path)
    await engine.initialize()
    memory = engine.create_memory(
        agent="test", memory_type=MemoryType.LEARNING,
        tags=["python"], content="Signal uses asyncio",
    )
    await engine.store(memory)
    results = await engine.search(tags=["python"])
    assert len(results) == 1
```

---

## Next steps

- [Contributing](contributing.md) -- development setup and workflow
- [Error Handling](error-handling.md) -- exception hierarchy reference
- [Project Structure](project-structure.md) -- where to find things
