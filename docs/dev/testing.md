# Testing

## Running Tests

```bash
# Full suite
uv run pytest

# Verbose: shows each test name and status
uv run pytest -v

# Quiet: dots only, summary at end
uv run pytest -q

# Stop on first failure
uv run pytest -x

# Run a specific directory
uv run pytest tests/unit/core/

# Run tests matching a keyword pattern
uv run pytest -k "executor"

# Combine flags
uv run pytest -v -x tests/unit/ai/
```

Current test count: **257 tests, all passing**.

---

## Test Organization

```
tests/
  conftest.py          -- shared fixtures used across all test modules
  unit/
    core/              -- tests for types.py, models.py, config.py, errors.py, protocols.py
    ai/                -- tests for ai/layer.py (LiteLLM mocked)
    runtime/           -- tests for executor.py (bus-based), bootstrap.py (wiring), runner.py (agentic loop)
    memory/            -- tests for memory/storage.py, index.py, engine.py
    agents/            -- tests for agents/base.py, host.py, prime.py, micro.py
    comms/             -- tests for comms/bus.py (MessageBus)
    tools/             -- tests for tools/protocol.py, registry.py, builtins/file_system.py
    hooks/             -- tests for hooks/registry.py, executor.py
      builtins/        -- tests for hooks/builtins/log_tool_calls.py
  integration/         -- CLI end-to-end tests
```

The `unit/` tree mirrors `src/signalagent/`. If you add `src/signalagent/core/foo.py`, its tests go in `tests/unit/core/test_foo.py`.

**Memory test layer isolation:**
- `test_storage.py` -- filesystem only, uses `tmp_path`, no SQLite
- `test_index.py` -- in-memory SQLite only (`:memory:`), no filesystem
- `test_engine.py` -- both layers together via `tmp_path`

Integration tests exercise the CLI commands using `typer.testing.CliRunner`. They do not call real LLM APIs.

---

## Test Patterns

### Pydantic Model Tests

Construct the model with valid data, assert fields are correct. Test YAML round-trips by serializing to dict and reloading. Test that invalid or extra fields raise `ValidationError`.

```python
def test_profile_round_trip():
    data = {"name": "blank", "description": "Empty profile", "system_prompt": ""}
    profile = Profile.model_validate(data)
    assert profile.name == "blank"
    reloaded = Profile.model_validate(profile.model_dump())
    assert reloaded == profile

def test_profile_rejects_unknown_field():
    with pytest.raises(ValidationError):
        Profile.model_validate({"name": "x", "unknown_field": True})
```

### AI Layer Tests

Patch `litellm.acompletion` with an `AsyncMock` that returns a structured fake response. Verify that `AILayer` maps the response correctly to `AIResponse`.

```python
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_ai_layer_maps_response(monkeypatch):
    fake_choice = MagicMock()
    fake_choice.message.content = "hello"
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_response.model = "gpt-4o-mini"
    fake_response.usage.total_tokens = 10

    mock_completion = AsyncMock(return_value=fake_response)
    monkeypatch.setattr("litellm.acompletion", mock_completion)

    layer = AILayer(model="gpt-4o-mini", api_key="test")
    result = await layer.complete("say hello")

    assert result.content == "hello"
    assert result.model == "gpt-4o-mini"
```

### Executor Tests

Inject a mock AI layer that satisfies `AILayerProtocol`. Test that the executor returns a structured `ExecutorResult`. Test the error boundary: if the AI layer raises, the executor returns an error result instead of propagating.

```python
@pytest.mark.asyncio
async def test_executor_error_boundary():
    class FailingLayer:
        async def complete(self, prompt: str) -> AIResponse:
            raise RuntimeError("LLM down")

    executor = Executor(ai_layer=FailingLayer())
    result = await executor.run("do something")

    assert result.success is False
    assert "LLM down" in result.error
```

### CLI Tests

Use `typer.testing.CliRunner` to invoke commands. Use `monkeypatch.chdir` to isolate each test in a temporary directory so `signal init` does not pollute the repo. Patch LLM calls so tests run offline.

```python
from typer.testing import CliRunner
from signalagent.cli.app import app

runner = CliRunner()

def test_init_creates_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--name", "test-agent"])
    assert result.exit_code == 0
    assert (tmp_path / ".signal" / "config.yaml").exists()
```

### Multi-Agent Tests

Multi-agent tests use a sequential `side_effect` list to drive the two LLM calls that happen in a single routed request: Prime's routing call followed by the micro-agent's execution call.

```python
mock_ai.complete = AsyncMock(side_effect=[
    routing_response,    # Prime's routing call
    agent_response,      # Micro-agent's execution call
])
```

Agent tests use a real bus with stub agents for isolation -- this exercises the bus wiring without needing a full runtime. Bootstrap tests use all real objects with only `AILayer` mocked, verifying that the wiring function connects everything correctly.

---

## How to Mock LiteLLM

LiteLLM is patched at the module level where it is called (`litellm.acompletion`), not on the `AILayer` class. Always use `AsyncMock` for the coroutine, and `MagicMock` for the response object and its attributes.

```python
from unittest.mock import AsyncMock, MagicMock

# Build a fake response that looks like a litellm ModelResponse
fake_choice = MagicMock()
fake_choice.message.content = "response text"

fake_response = MagicMock()
fake_response.choices = [fake_choice]
fake_response.model = "gpt-4o-mini"
fake_response.usage.total_tokens = 42

# Patch before the call
monkeypatch.setattr("litellm.acompletion", AsyncMock(return_value=fake_response))
```

Use `monkeypatch.setattr` (pytest) rather than `unittest.mock.patch` decorators -- it integrates better with pytest fixtures and respects test isolation.

### Tool Execution Tests

Tool execution tests follow three patterns:

**Mock AI with tool_calls:** Build a mock AI layer that returns responses with `tool_calls` on the first call and a final text response on the second. This drives the agentic loop through at least one tool execution cycle.

```python
@pytest.mark.asyncio
async def test_runner_executes_tool():
    tool_response = MagicMock()
    tool_response.content = None
    tool_response.tool_calls = [ToolCallRequest(id="1", name="read", arguments={"path": "f.txt"})]

    final_response = MagicMock()
    final_response.content = "done"
    final_response.tool_calls = []

    mock_ai = AsyncMock(side_effect=[tool_response, final_response])
    mock_executor = AsyncMock(return_value=ToolResult(tool_call_id="1", output="contents"))

    runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor, tool_schemas=[], max_iterations=5)
    result = await runner.run([{"role": "user", "content": "read file"}])
    assert result.tool_calls_made == 1
```

**Mock executor:** The ToolExecutor is a simple callable (`async (str, dict) -> ToolResult`). Replace it with an `AsyncMock` to verify the runner passes the correct tool name and arguments without needing real tool implementations.

**tmp_path for FileSystemTool:** FileSystemTool is scoped to a workspace directory. Tests use pytest's `tmp_path` fixture as the workspace root, write test files, and verify read/write/list operations stay within bounds.

```python
def test_file_system_tool_reads(tmp_path):
    (tmp_path / "test.txt").write_text("hello")
    tool = FileSystemTool(workspace=tmp_path)
    result = tool.execute(action="read", path="test.txt")
    assert result.output == "hello"
```

### Hook Tests

Hook tests use fake hook classes instead of mocking the protocol directly. This gives explicit control over block/allow behavior and lets tests inspect call history.

**AllowHook / BlockHook pattern:** Define minimal classes that satisfy the Hook protocol. AllowHook records calls and returns `None` (allow). BlockHook returns a `ToolResult` with an error (block). These are defined per-test-module, not shared fixtures, since they are short and test-specific.

```python
class AllowHook:
    def __init__(self, name="allow"):
        self._name = name
        self.before_calls = []
        self.after_calls = []

    @property
    def name(self):
        return self._name

    async def before_tool_call(self, tool_name, arguments):
        self.before_calls.append((tool_name, arguments))
        return None

    async def after_tool_call(self, tool_name, arguments, result, blocked):
        self.after_calls.append((tool_name, arguments, result, blocked))


class BlockHook:
    def __init__(self, reason="Blocked by policy"):
        self._reason = reason

    @property
    def name(self):
        return "blocker"

    async def before_tool_call(self, tool_name, arguments):
        return ToolResult(output="", error=f"Blocked: {self._reason}")

    async def after_tool_call(self, tool_name, arguments, result, blocked):
        pass
```

**HookExecutor tests** use an `AsyncMock` as the inner executor and combine AllowHook/BlockHook instances to verify: allow-through, block-before-execution, after-hooks-fire-on-block, and fail-open-on-hook-error.

**LogToolCallsHook tests** use `tmp_path` for the JSONL log file and verify that each tool call produces a JSON line with the expected fields (tool_name, arguments, duration, blocked).

### Sub-Agent Tests

Sub-agent tests use a mock runner factory to control the sub-agent's execution without needing real AI calls. The factory returns a mock runner that produces a predetermined RunnerResult when called.

**SpawnSubAgentTool tests** verify: successful spawn with result passthrough, tool inheritance (parent tools minus spawn), sub-agent name defaults, and error handling when the runner raises.

**End-to-end spawn chain tests** wire bootstrap with a mock AI layer that returns spawn_sub_agent tool calls, verifying the full pipeline from parent agent through per-agent executor to sub-agent execution and result return.
