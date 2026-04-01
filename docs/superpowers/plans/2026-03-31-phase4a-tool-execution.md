# Phase 4a: Tool Execution + Agentic Loop -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give micro-agents the ability to call tools via an agentic loop -- call AI, execute tool calls, feed results back, repeat until done.

**Architecture:** New `core/protocols.py` holds all protocol abstractions (AILayerProtocol, RunnerProtocol, ToolExecutor). New `tools/` package provides Tool protocol, ToolRegistry, and built-in file_system tool. New `runtime/runner.py` implements the agentic loop. MicroAgent delegates to RunnerProtocol; bootstrap wires the concrete implementations. No circular dependencies -- agents depend on abstractions in core/, runtime provides implementations.

**Tech Stack:** Python 3.11+, Pydantic v2, LiteLLM (tool calling), asyncio, pytest with asyncio_mode="auto"

---

### Task 1: Move AILayerProtocol to core/protocols.py

Pre-Phase 4a cleanup. AILayerProtocol currently lives in `runtime/executor.py`. Moving it to `core/protocols.py` fixes the dependency direction so `agents/` and `tools/` can import it without depending on `runtime/`.

**Files:**
- Create: `src/signalagent/core/protocols.py`
- Modify: `src/signalagent/runtime/executor.py:7-8,18-26`
- Modify: `src/signalagent/agents/micro.py:8`
- Modify: `src/signalagent/agents/prime.py:17`
- Create: `tests/unit/core/test_protocols.py`

- [ ] **Step 1: Write the failing test for AILayerProtocol in new location**

```python
# tests/unit/core/test_protocols.py
"""Tests for core protocol definitions."""

import pytest
from unittest.mock import AsyncMock

from signalagent.core.protocols import AILayerProtocol


class TestAILayerProtocol:
    def test_async_mock_satisfies_protocol(self):
        """An AsyncMock with the right shape satisfies the protocol."""
        mock = AsyncMock()
        mock.complete = AsyncMock()
        assert isinstance(mock, AILayerProtocol)

    def test_object_without_complete_fails(self):
        class Bad:
            pass
        assert not isinstance(Bad(), AILayerProtocol)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_protocols.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'signalagent.core.protocols'`

- [ ] **Step 3: Create core/protocols.py with AILayerProtocol**

```python
# src/signalagent/core/protocols.py
"""Protocol definitions for dependency injection across packages.

All protocol types that agents and tools depend on live here. Concrete
implementations live in their respective packages (ai/, runtime/).
This keeps the dependency graph clean: core/ depends on nothing,
everything else can depend on core/.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class AILayerProtocol(Protocol):
    """Protocol for the AI layer so agents don't depend on concrete class."""

    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: list[dict] | None = None,
    ) -> Any: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_protocols.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Update imports in executor.py, micro.py, prime.py**

In `src/signalagent/runtime/executor.py`, remove the `AILayerProtocol` class definition (lines 18-26) and the `Protocol, runtime_checkable` imports. Add import from core:

```python
# executor.py -- remove the protocol class and its imports.
# Change the typing imports from:
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable
# to:
from typing import TYPE_CHECKING, Optional

# Add after the existing imports:
from signalagent.core.protocols import AILayerProtocol
```

Keep `AILayerProtocol` as a re-export in executor.py's module scope so nothing breaks:
```python
# Re-export for backward compatibility (prime.py imports from here)
__all__ = ["AILayerProtocol", "Executor", "ExecutorResult"]
```

In `src/signalagent/agents/micro.py`, change:
```python
# from:
from signalagent.runtime.executor import AILayerProtocol
# to:
from signalagent.core.protocols import AILayerProtocol
```

In `src/signalagent/agents/prime.py`, change:
```python
# from:
from signalagent.runtime.executor import AILayerProtocol
# to:
from signalagent.core.protocols import AILayerProtocol
```

- [ ] **Step 6: Run all tests to verify nothing broke**

Run: `uv run pytest -x -q`
Expected: 169 passed

- [ ] **Step 7: Commit**

```bash
git add src/signalagent/core/protocols.py tests/unit/core/test_protocols.py src/signalagent/runtime/executor.py src/signalagent/agents/micro.py src/signalagent/agents/prime.py
git commit -m "refactor: move AILayerProtocol to core/protocols for clean dependency direction"
```

---

### Task 2: Add ToolCallRequest, ToolResult, ToolConfig to core/models.py

New Pydantic models for the tool system. Also adds `max_iterations` to MicroAgentConfig and `ToolConfig` to SignalConfig.

**Files:**
- Modify: `src/signalagent/core/models.py:1-98`
- Modify: `src/signalagent/core/config.py:23-28`
- Modify: `src/signalagent/core/errors.py:24-25`
- Modify: `tests/unit/core/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/core/test_models.py`:

```python
from signalagent.core.models import ToolCallRequest, ToolResult, ToolConfig, MicroAgentConfig


class TestToolCallRequest:
    def test_construction(self):
        tc = ToolCallRequest(id="call_1", name="file_system", arguments={"op": "read"})
        assert tc.id == "call_1"
        assert tc.name == "file_system"
        assert tc.arguments == {"op": "read"}

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ToolCallRequest(id="1", name="x", arguments={}, extra="bad")


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(output="file contents here")
        assert r.output == "file contents here"
        assert r.error is None

    def test_error_result(self):
        r = ToolResult(output="", error="file not found")
        assert r.error == "file not found"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ToolResult(output="x", extra="bad")


class TestToolConfig:
    def test_defaults(self):
        tc = ToolConfig()
        assert tc.max_iterations == 20

    def test_custom_max(self):
        tc = ToolConfig(max_iterations=50)
        assert tc.max_iterations == 50


class TestMicroAgentConfigMaxIterations:
    def test_default_max_iterations(self):
        config = MicroAgentConfig(name="test", skill="testing")
        assert config.max_iterations == 10

    def test_custom_max_iterations(self):
        config = MicroAgentConfig(name="test", skill="testing", max_iterations=5)
        assert config.max_iterations == 5
```

Also add `from pydantic import ValidationError` to the test file's imports if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_models.py::TestToolCallRequest -v`
Expected: FAIL -- `ImportError: cannot import name 'ToolCallRequest'`

- [ ] **Step 3: Add models to core/models.py**

Add after the `Message` class at the bottom of `src/signalagent/core/models.py`:

```python
class ToolCallRequest(BaseModel):
    """What the LLM wants to do -- a request to call a tool.

    Named ToolCallRequest (not ToolCall) to reserve ToolCall for the full
    execution record with result, timing, and tracing (Phase 10).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """Result of executing a tool call."""

    model_config = ConfigDict(extra="forbid")

    output: str
    error: str | None = None


class ToolConfig(BaseModel):
    """Global tool execution settings."""

    model_config = ConfigDict(extra="forbid")

    max_iterations: int = 20
```

Add `max_iterations` field to `MicroAgentConfig`:

```python
class MicroAgentConfig(BaseModel):
    # ... existing fields ...
    max_iterations: int = 10
```

- [ ] **Step 4: Add ToolConfig to SignalConfig**

In `src/signalagent/core/config.py`, add the import and field:

```python
# Add to imports:
from signalagent.core.models import Profile, ToolConfig

# Add field to SignalConfig (after the ai field):
class SignalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    ai: AIConfig = Field(default_factory=AIConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
```

- [ ] **Step 5: Add ToolExecutionError to core/errors.py**

Add after `RoutingError`:

```python
class ToolExecutionError(SignalError):
    """Tool execution failed."""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_models.py -v`
Expected: All model tests PASS

Run: `uv run pytest -x -q`
Expected: All tests pass (169 existing + new)

- [ ] **Step 7: Commit**

```bash
git add src/signalagent/core/models.py src/signalagent/core/config.py src/signalagent/core/errors.py tests/unit/core/test_models.py
git commit -m "feat: add ToolCallRequest, ToolResult, ToolConfig models and ToolExecutionError"
```

---

### Task 3: Extend AILayer with tools parameter and tool_calls response

Add optional `tools` parameter to `AILayer.complete()` and `tool_calls: list[ToolCallRequest]` to `AIResponse`.

**Files:**
- Modify: `src/signalagent/ai/layer.py:1-83`
- Modify: `tests/unit/ai/test_layer.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for the new AILayer behavior**

Add to `tests/unit/ai/test_layer.py`:

```python
from signalagent.core.models import ToolCallRequest


class TestAIResponseToolCalls:
    def test_tool_calls_defaults_to_empty_list(self):
        response = AIResponse(
            content="hello",
            model="test",
            provider="test",
            input_tokens=0,
            output_tokens=0,
        )
        assert response.tool_calls == []

    def test_tool_calls_populated(self):
        tc = ToolCallRequest(id="call_1", name="file_system", arguments={"op": "read"})
        response = AIResponse(
            content="",
            model="test",
            provider="test",
            tool_calls=[tc],
        )
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "file_system"


class TestCompleteWithTools:
    @pytest.mark.asyncio
    async def test_passes_tools_to_litellm(self, monkeypatch, config):
        """When tools are passed, litellm.acompletion receives them."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=None))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_response.model = "test-model"

        mock_acompletion = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("signalagent.ai.layer.litellm.acompletion", mock_acompletion)

        layer = AILayer(config)
        tools = [{"type": "function", "function": {"name": "test", "description": "test", "parameters": {}}}]
        await layer.complete(messages=[{"role": "user", "content": "hi"}], tools=tools)

        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["tools"] == tools

    @pytest.mark.asyncio
    async def test_no_tools_omits_tools_kwarg(self, monkeypatch, config):
        """When tools is None, litellm.acompletion does not receive tools kwarg."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=None))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_response.model = "test-model"

        mock_acompletion = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("signalagent.ai.layer.litellm.acompletion", mock_acompletion)

        layer = AILayer(config)
        await layer.complete(messages=[{"role": "user", "content": "hi"}])

        call_kwargs = mock_acompletion.call_args.kwargs
        assert "tools" not in call_kwargs

    @pytest.mark.asyncio
    async def test_parses_tool_calls_from_response(self, monkeypatch, config):
        """Tool calls in LLM response are parsed into ToolCallRequest objects."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_abc"
        mock_tool_call.function.name = "file_system"
        mock_tool_call.function.arguments = '{"operation": "read", "path": "test.txt"}'

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=None, tool_calls=[mock_tool_call]))
        ]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_response.model = "test-model"

        mock_acompletion = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("signalagent.ai.layer.litellm.acompletion", mock_acompletion)

        layer = AILayer(config)
        result = await layer.complete(
            messages=[{"role": "user", "content": "read file"}],
            tools=[{"type": "function", "function": {"name": "file_system", "description": "fs", "parameters": {}}}],
        )

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_abc"
        assert result.tool_calls[0].name == "file_system"
        assert result.tool_calls[0].arguments == {"operation": "read", "path": "test.txt"}
```

These tests need a `config` fixture. Add to `tests/unit/ai/test_layer.py` if not present:

```python
from signalagent.core.config import SignalConfig

@pytest.fixture
def config():
    return SignalConfig(profile_name="test")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/ai/test_layer.py::TestAIResponseToolCalls -v`
Expected: FAIL -- `AIResponse` has no `tool_calls` field

- [ ] **Step 3: Implement the changes in ai/layer.py**

Modify `src/signalagent/ai/layer.py`:

Add import at top:
```python
import json
from signalagent.core.models import ToolCallRequest
```

Add field to `AIResponse`:
```python
class AIResponse(BaseModel):
    """Unified response from any LLM provider."""
    model_config = ConfigDict(extra="forbid")

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
```

Update `complete()` method:
```python
async def complete(
    self,
    messages: list[dict],
    model: Optional[str] = None,
    tools: list[dict] | None = None,
) -> AIResponse:
    model = model or self._config.ai.default_model
    try:
        kwargs: dict = {"model": model, "messages": messages}
        if tools is not None:
            kwargs["tools"] = tools
        response = await litellm.acompletion(**kwargs)
    except Exception as e:
        raise AIError(f"LLM call failed: {e}") from e

    choice = response.choices[0]
    usage = response.usage

    provider = model.split("/")[0] if "/" in model else "unknown"

    cost = 0.0
    try:
        cost = litellm.completion_cost(completion_response=response) or 0.0
    except Exception:
        pass

    # Parse tool calls if present
    parsed_tool_calls: list[ToolCallRequest] = []
    raw_tool_calls = choice.message.tool_calls
    if raw_tool_calls:
        for tc in raw_tool_calls:
            arguments = tc.function.arguments
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            parsed_tool_calls.append(
                ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments,
                )
            )

    return AIResponse(
        content=choice.message.content or "",
        model=response.model or model,
        provider=provider,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        cost=cost,
        tool_calls=parsed_tool_calls,
    )
```

- [ ] **Step 4: Update AILayerProtocol to include tools parameter**

The protocol in `core/protocols.py` already has the `tools` parameter from Step 3 of Task 1. Verify it matches:

```python
async def complete(
    self,
    messages: list[dict],
    model: Optional[str] = None,
    tools: list[dict] | None = None,
) -> Any: ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/ai/test_layer.py -v`
Expected: All PASS

Run: `uv run pytest -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/ai/layer.py tests/unit/ai/test_layer.py
git commit -m "feat: extend AILayer with tools parameter and tool_calls on AIResponse"
```

---

### Task 4: Tool protocol and ToolRegistry

Create the `tools/` package with Tool protocol and ToolRegistry.

**Files:**
- Create: `src/signalagent/tools/__init__.py`
- Create: `src/signalagent/tools/protocol.py`
- Create: `src/signalagent/tools/registry.py`
- Create: `tests/unit/tools/__init__.py`
- Create: `tests/unit/tools/test_registry.py`

- [ ] **Step 1: Write failing tests for ToolRegistry**

```python
# tests/unit/tools/__init__.py
# (empty)
```

```python
# tests/unit/tools/test_registry.py
"""Unit tests for ToolRegistry."""

import pytest

from signalagent.core.models import ToolResult
from signalagent.tools.registry import ToolRegistry


class FakeTool:
    """Concrete tool for testing."""

    def __init__(self, name: str = "echo", description: str = "Echoes input"):
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(output=kwargs.get("text", ""))


class TestToolRegistryRegisterAndGet:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = FakeTool()
        registry.register(tool)
        assert registry.get("echo") is tool

    def test_get_returns_none_for_unknown(self):
        registry = ToolRegistry()
        assert registry.get("unknown") is None

    def test_register_multiple(self):
        registry = ToolRegistry()
        t1 = FakeTool(name="a")
        t2 = FakeTool(name="b")
        registry.register(t1)
        registry.register(t2)
        assert registry.get("a") is t1
        assert registry.get("b") is t2


class TestToolRegistryGetSchemas:
    def test_returns_litellm_format(self):
        registry = ToolRegistry()
        registry.register(FakeTool(name="echo", description="Echoes input"))
        schemas = registry.get_schemas(["echo"])
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "echo"
        assert schema["function"]["description"] == "Echoes input"
        assert schema["function"]["parameters"]["type"] == "object"

    def test_skips_unknown_names(self):
        registry = ToolRegistry()
        registry.register(FakeTool(name="echo"))
        schemas = registry.get_schemas(["echo", "missing"])
        assert len(schemas) == 1

    def test_empty_names_returns_empty(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        schemas = registry.get_schemas([])
        assert schemas == []

    def test_multiple_tools(self):
        registry = ToolRegistry()
        registry.register(FakeTool(name="a", description="Tool A"))
        registry.register(FakeTool(name="b", description="Tool B"))
        schemas = registry.get_schemas(["a", "b"])
        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert names == {"a", "b"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tools/test_registry.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'signalagent.tools'`

- [ ] **Step 3: Create the tools package, protocol, and registry**

```python
# src/signalagent/tools/__init__.py
# (empty)
```

```python
# src/signalagent/tools/protocol.py
"""Tool protocol -- interface every tool must implement."""

from __future__ import annotations

from typing import Protocol

from signalagent.core.models import ToolResult


class Tool(Protocol):
    """Protocol for tools that agents can call."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict: ...

    async def execute(self, **kwargs) -> ToolResult: ...
```

```python
# src/signalagent/tools/registry.py
"""ToolRegistry -- lookup layer for tool resolution and schema generation."""

from __future__ import annotations

from signalagent.tools.protocol import Tool


class ToolRegistry:
    """Maps tool names to implementations and produces LiteLLM-format schemas.

    This is a lookup layer only. It does not execute tools.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool by name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Look up a tool by name. Returns None if not found."""
        return self._tools.get(name)

    def get_schemas(self, names: list[str]) -> list[dict]:
        """Return LiteLLM-format tool definitions for the given names.

        Unknown names are silently skipped.
        """
        schemas = []
        for name in names:
            tool = self._tools.get(name)
            if tool is not None:
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                })
        return schemas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/tools/test_registry.py -v`
Expected: All PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/tools/__init__.py src/signalagent/tools/protocol.py src/signalagent/tools/registry.py tests/unit/tools/__init__.py tests/unit/tools/test_registry.py
git commit -m "feat: add Tool protocol and ToolRegistry with LiteLLM-format schema generation"
```

---

### Task 5: Built-in file_system tool

FileSystemTool with read (size-capped), write, and list operations, scoped to instance directory.

**Files:**
- Create: `src/signalagent/tools/builtins/__init__.py`
- Create: `src/signalagent/tools/builtins/file_system.py`
- Create: `tests/unit/tools/builtins/__init__.py`
- Create: `tests/unit/tools/builtins/test_file_system.py`

- [ ] **Step 1: Write failing tests for FileSystemTool**

```python
# tests/unit/tools/builtins/__init__.py
# (empty)
```

```python
# tests/unit/tools/builtins/test_file_system.py
"""Unit tests for FileSystemTool -- uses tmp_path for isolation."""

import pytest

from signalagent.tools.builtins.file_system import FileSystemTool


@pytest.fixture
def tool(tmp_path):
    return FileSystemTool(root=tmp_path)


class TestFileSystemToolProperties:
    def test_name(self, tool):
        assert tool.name == "file_system"

    def test_description_is_nonempty(self, tool):
        assert len(tool.description) > 0

    def test_parameters_schema(self, tool):
        params = tool.parameters
        assert params["type"] == "object"
        assert "operation" in params["properties"]
        assert "path" in params["properties"]
        assert params["properties"]["operation"]["enum"] == ["read", "write", "list"]


class TestFileSystemRead:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tool, tmp_path):
        (tmp_path / "hello.txt").write_text("hello world")
        result = await tool.execute(operation="read", path="hello.txt")
        assert result.output == "hello world"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_read_missing_file(self, tool):
        result = await tool.execute(operation="read", path="nope.txt")
        assert result.error is not None
        assert "not found" in result.error.lower() or "does not exist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_truncates_large_file(self, tool, tmp_path):
        large = "x" * (2 * 1024 * 1024)  # 2MB
        (tmp_path / "big.txt").write_text(large)
        result = await tool.execute(operation="read", path="big.txt")
        assert len(result.output) < len(large)
        assert "truncated" in result.output.lower()

    @pytest.mark.asyncio
    async def test_read_nested_path(self, tool, tmp_path):
        sub = tmp_path / "sub" / "dir"
        sub.mkdir(parents=True)
        (sub / "file.txt").write_text("nested")
        result = await tool.execute(operation="read", path="sub/dir/file.txt")
        assert result.output == "nested"


class TestFileSystemWrite:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, tool, tmp_path):
        result = await tool.execute(operation="write", path="new.txt", content="hello")
        assert result.error is None
        assert (tmp_path / "new.txt").read_text() == "hello"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tool, tmp_path):
        result = await tool.execute(operation="write", path="a/b/c.txt", content="deep")
        assert result.error is None
        assert (tmp_path / "a" / "b" / "c.txt").read_text() == "deep"

    @pytest.mark.asyncio
    async def test_write_overwrites_existing(self, tool, tmp_path):
        (tmp_path / "exist.txt").write_text("old")
        result = await tool.execute(operation="write", path="exist.txt", content="new")
        assert result.error is None
        assert (tmp_path / "exist.txt").read_text() == "new"


class TestFileSystemList:
    @pytest.mark.asyncio
    async def test_list_directory(self, tool, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "subdir").mkdir()
        result = await tool.execute(operation="list", path=".")
        assert result.error is None
        assert "a.txt" in result.output
        assert "b.txt" in result.output
        assert "subdir" in result.output

    @pytest.mark.asyncio
    async def test_list_missing_directory(self, tool):
        result = await tool.execute(operation="list", path="nope")
        assert result.error is not None


class TestFileSystemSecurity:
    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, tool):
        result = await tool.execute(operation="read", path="../../../etc/passwd")
        assert result.error is not None
        assert "outside workspace" in result.error.lower()

    @pytest.mark.asyncio
    async def test_absolute_path_blocked(self, tool):
        result = await tool.execute(operation="read", path="/etc/passwd")
        assert result.error is not None
        assert "outside workspace" in result.error.lower()

    @pytest.mark.asyncio
    async def test_write_traversal_blocked(self, tool):
        result = await tool.execute(operation="write", path="../escape.txt", content="bad")
        assert result.error is not None
        assert "outside workspace" in result.error.lower()


class TestFileSystemInvalidOperation:
    @pytest.mark.asyncio
    async def test_unknown_operation(self, tool):
        result = await tool.execute(operation="delete", path="file.txt")
        assert result.error is not None
        assert "unknown operation" in result.error.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tools/builtins/test_file_system.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'signalagent.tools.builtins'`

- [ ] **Step 3: Implement FileSystemTool**

```python
# src/signalagent/tools/builtins/__init__.py
"""Built-in tool loading."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signalagent.tools.protocol import Tool


def load_builtin_tool(name: str, instance_dir: Path) -> Tool | None:
    """Load a built-in tool by name. Returns None for unknown names."""
    if name == "file_system":
        from signalagent.tools.builtins.file_system import FileSystemTool
        return FileSystemTool(root=instance_dir)
    return None
```

```python
# src/signalagent/tools/builtins/file_system.py
"""FileSystemTool -- read, write, list files scoped to a workspace root."""

from __future__ import annotations

from pathlib import Path

from signalagent.core.models import ToolResult

# 1 MB default read cap
DEFAULT_MAX_READ_BYTES = 1 * 1024 * 1024


class FileSystemTool:
    """File system operations scoped to a workspace directory.

    All paths are resolved relative to root. Traversal outside root
    is rejected. No destructive operations (delete, move, chmod).
    """

    def __init__(
        self,
        root: Path,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
    ) -> None:
        self._root = root.resolve()
        self._max_read_bytes = max_read_bytes

    @property
    def name(self) -> str:
        return "file_system"

    @property
    def description(self) -> str:
        return "Read, write, and list files within the workspace."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "list"],
                    "description": "The operation to perform.",
                },
                "path": {
                    "type": "string",
                    "description": "Relative path within workspace.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (write operation only).",
                },
            },
            "required": ["operation", "path"],
        }

    def _resolve_safe(self, path_str: str) -> Path | None:
        """Resolve path relative to root. Returns None if it escapes."""
        target = (self._root / path_str).resolve()
        if not str(target).startswith(str(self._root)):
            return None
        return target

    async def execute(self, **kwargs) -> ToolResult:
        """Execute a file system operation."""
        operation = kwargs.get("operation", "")
        path_str = kwargs.get("path", "")

        if operation == "read":
            return await self._read(path_str)
        elif operation == "write":
            content = kwargs.get("content", "")
            return await self._write(path_str, content)
        elif operation == "list":
            return await self._list(path_str)
        else:
            return ToolResult(output="", error=f"Unknown operation: {operation}")

    async def _read(self, path_str: str) -> ToolResult:
        target = self._resolve_safe(path_str)
        if target is None:
            return ToolResult(output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(output="", error=f"File does not exist: {path_str}")

        if not target.is_file():
            return ToolResult(output="", error=f"Not a file: {path_str}")

        file_size = target.stat().st_size
        if file_size <= self._max_read_bytes:
            content = target.read_text(encoding="utf-8", errors="replace")
            return ToolResult(output=content)

        # Truncated read
        raw = target.read_bytes()[:self._max_read_bytes]
        content = raw.decode("utf-8", errors="replace")
        size_mb = file_size / (1024 * 1024)
        cap_mb = self._max_read_bytes / (1024 * 1024)
        content += f"\n[truncated at {cap_mb:.0f}MB, file is {size_mb:.1f}MB]"
        return ToolResult(output=content)

    async def _write(self, path_str: str, content: str) -> ToolResult:
        target = self._resolve_safe(path_str)
        if target is None:
            return ToolResult(output="", error="Path outside workspace")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(output=f"Written: {path_str}")

    async def _list(self, path_str: str) -> ToolResult:
        target = self._resolve_safe(path_str)
        if target is None:
            return ToolResult(output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(output="", error=f"Directory does not exist: {path_str}")

        if not target.is_dir():
            return ToolResult(output="", error=f"Not a directory: {path_str}")

        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
        return ToolResult(output="\n".join(entries))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/tools/builtins/test_file_system.py -v`
Expected: All PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/tools/builtins/__init__.py src/signalagent/tools/builtins/file_system.py tests/unit/tools/builtins/__init__.py tests/unit/tools/builtins/test_file_system.py
git commit -m "feat: add FileSystemTool with scoped read/write/list and path traversal protection"
```

---

### Task 6: Add RunnerProtocol and ToolExecutor to core/protocols.py

Add the remaining protocol definitions that the runner and agents depend on.

**Files:**
- Modify: `src/signalagent/core/protocols.py`
- Modify: `tests/unit/core/test_protocols.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/core/test_protocols.py`:

```python
from signalagent.core.protocols import RunnerProtocol, ToolExecutor


class TestRunnerProtocol:
    def test_async_mock_satisfies_protocol(self):
        mock = AsyncMock()
        mock.run = AsyncMock()
        assert isinstance(mock, RunnerProtocol)


class TestToolExecutor:
    def test_async_callable_satisfies_protocol(self):
        mock = AsyncMock()
        assert isinstance(mock, ToolExecutor)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_protocols.py::TestRunnerProtocol -v`
Expected: FAIL -- `ImportError: cannot import name 'RunnerProtocol'`

- [ ] **Step 3: Add RunnerProtocol and ToolExecutor to core/protocols.py**

Append to `src/signalagent/core/protocols.py`:

```python
@runtime_checkable
class RunnerProtocol(Protocol):
    """Protocol for the agentic loop runner.

    Agents depend on this protocol, not the concrete AgenticRunner.
    """

    async def run(
        self,
        system_prompt: str,
        user_content: str,
    ) -> Any: ...


@runtime_checkable
class ToolExecutor(Protocol):
    """Protocol for tool execution callable.

    The runner calls this to execute tools. In 4a it wraps
    registry.get(name).execute(**args). In 4b it gets replaced
    with a hook-aware version.
    """

    async def __call__(
        self,
        tool_name: str,
        arguments: dict,
    ) -> Any: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_protocols.py -v`
Expected: All PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/core/protocols.py tests/unit/core/test_protocols.py
git commit -m "feat: add RunnerProtocol and ToolExecutor to core/protocols"
```

---

### Task 7: AgenticRunner

The agentic loop implementation. Calls AI with tools, executes tool calls via ToolExecutor, feeds results back, repeats until final text or iteration limit.

**Files:**
- Create: `src/signalagent/runtime/runner.py`
- Create: `tests/unit/runtime/test_runner.py`

- [ ] **Step 1: Write failing tests for AgenticRunner**

```python
# tests/unit/runtime/test_runner.py
"""Unit tests for AgenticRunner -- mock AI + mock tool executor."""

import pytest
from unittest.mock import AsyncMock

from signalagent.ai.layer import AIResponse
from signalagent.core.models import ToolCallRequest, ToolResult
from signalagent.runtime.runner import AgenticRunner, RunnerResult


def _make_text_response(content: str) -> AIResponse:
    """AI response with no tool calls -- final answer."""
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
        tool_calls=[],
    )


def _make_tool_response(tool_calls: list[ToolCallRequest], content: str = "") -> AIResponse:
    """AI response with tool calls."""
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
        tool_calls=tool_calls,
    )


class TestRunnerNoTools:
    @pytest.mark.asyncio
    async def test_single_pass_no_tools(self):
        """With no tool schemas, runner makes one AI call and returns."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_text_response("hello"))
        mock_executor = AsyncMock()

        runner = AgenticRunner(
            ai=mock_ai,
            tool_executor=mock_executor,
            tool_schemas=[],
            max_iterations=10,
        )
        result = await runner.run(system_prompt="You are helpful.", user_content="hi")

        assert result.content == "hello"
        assert result.iterations == 1
        assert result.tool_calls_made == 0
        assert result.truncated is False
        mock_ai.complete.assert_called_once()
        # tools should be None when schemas are empty
        assert mock_ai.complete.call_args.kwargs.get("tools") is None


class TestRunnerWithTools:
    @pytest.mark.asyncio
    async def test_single_tool_call_then_final(self):
        """AI calls one tool, gets result, then returns final text."""
        tc = ToolCallRequest(id="call_1", name="file_system", arguments={"operation": "read", "path": "test.txt"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc]),
            _make_text_response("File contains: hello"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="hello"))

        runner = AgenticRunner(
            ai=mock_ai,
            tool_executor=mock_executor,
            tool_schemas=[{"type": "function", "function": {"name": "file_system"}}],
            max_iterations=10,
        )
        result = await runner.run(system_prompt="sys", user_content="read test.txt")

        assert result.content == "File contains: hello"
        assert result.iterations == 2
        assert result.tool_calls_made == 1
        mock_executor.assert_called_once_with("file_system", {"operation": "read", "path": "test.txt"})

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_response(self):
        """AI returns 2 tool calls in one response, both executed."""
        tc1 = ToolCallRequest(id="call_1", name="tool_a", arguments={"x": 1})
        tc2 = ToolCallRequest(id="call_2", name="tool_b", arguments={"y": 2})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc1, tc2]),
            _make_text_response("done"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="ok"))

        runner = AgenticRunner(
            ai=mock_ai,
            tool_executor=mock_executor,
            tool_schemas=[{"type": "function", "function": {"name": "tool_a"}},
                          {"type": "function", "function": {"name": "tool_b"}}],
            max_iterations=10,
        )
        result = await runner.run(system_prompt="sys", user_content="go")

        assert result.tool_calls_made == 2
        assert result.iterations == 2
        assert mock_executor.call_count == 2

    @pytest.mark.asyncio
    async def test_multi_iteration_tool_loop(self):
        """AI calls tools across multiple iterations before returning final text."""
        tc1 = ToolCallRequest(id="call_1", name="t", arguments={})
        tc2 = ToolCallRequest(id="call_2", name="t", arguments={})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc1]),
            _make_tool_response([tc2]),
            _make_text_response("done"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="ok"))

        runner = AgenticRunner(
            ai=mock_ai,
            tool_executor=mock_executor,
            tool_schemas=[{"type": "function", "function": {"name": "t"}}],
            max_iterations=10,
        )
        result = await runner.run(system_prompt="sys", user_content="go")

        assert result.iterations == 3
        assert result.tool_calls_made == 2


class TestRunnerIterationLimit:
    @pytest.mark.asyncio
    async def test_truncated_at_max_iterations(self):
        """Runner stops at max_iterations and returns truncated=True."""
        tc = ToolCallRequest(id="call_1", name="t", arguments={})
        mock_ai = AsyncMock()
        # Always returns tool calls -- never a final text
        mock_ai.complete = AsyncMock(return_value=_make_tool_response([tc], content="partial"))
        mock_executor = AsyncMock(return_value=ToolResult(output="ok"))

        runner = AgenticRunner(
            ai=mock_ai,
            tool_executor=mock_executor,
            tool_schemas=[{"type": "function", "function": {"name": "t"}}],
            max_iterations=3,
        )
        result = await runner.run(system_prompt="sys", user_content="go")

        assert result.truncated is True
        assert result.iterations == 3
        assert result.content == "partial"


class TestRunnerErrorHandling:
    @pytest.mark.asyncio
    async def test_tool_error_fed_back_to_llm(self):
        """ToolResult with error is fed back as error content, loop continues."""
        tc = ToolCallRequest(id="call_1", name="bad_tool", arguments={})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc]),
            _make_text_response("I see the error"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="", error="tool broke"))

        runner = AgenticRunner(
            ai=mock_ai,
            tool_executor=mock_executor,
            tool_schemas=[{"type": "function", "function": {"name": "bad_tool"}}],
            max_iterations=10,
        )
        result = await runner.run(system_prompt="sys", user_content="go")

        assert result.content == "I see the error"
        # Verify the error was fed back as tool result
        second_call_messages = mock_ai.complete.call_args_list[1].kwargs["messages"]
        tool_msg = [m for m in second_call_messages if m.get("role") == "tool"][0]
        assert "Error: tool broke" in tool_msg["content"]

    @pytest.mark.asyncio
    async def test_executor_exception_caught_and_fed_back(self):
        """Unexpected exception from executor is caught and fed back."""
        tc = ToolCallRequest(id="call_1", name="crash", arguments={})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc]),
            _make_text_response("recovered"),
        ])
        mock_executor = AsyncMock(side_effect=RuntimeError("executor crashed"))

        runner = AgenticRunner(
            ai=mock_ai,
            tool_executor=mock_executor,
            tool_schemas=[{"type": "function", "function": {"name": "crash"}}],
            max_iterations=10,
        )
        result = await runner.run(system_prompt="sys", user_content="go")

        assert result.content == "recovered"
        second_call_messages = mock_ai.complete.call_args_list[1].kwargs["messages"]
        tool_msg = [m for m in second_call_messages if m.get("role") == "tool"][0]
        assert "Error:" in tool_msg["content"]


class TestRunnerMessageFormat:
    @pytest.mark.asyncio
    async def test_assistant_message_includes_tool_calls(self):
        """The assistant message appended to history has correct LiteLLM format."""
        tc = ToolCallRequest(id="call_1", name="echo", arguments={"text": "hi"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc]),
            _make_text_response("done"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="hi"))

        runner = AgenticRunner(
            ai=mock_ai,
            tool_executor=mock_executor,
            tool_schemas=[{"type": "function", "function": {"name": "echo"}}],
            max_iterations=10,
        )
        await runner.run(system_prompt="sys", user_content="go")

        # Check the second AI call's messages
        second_call_messages = mock_ai.complete.call_args_list[1].kwargs["messages"]

        # Find assistant message with tool_calls
        assistant_msgs = [m for m in second_call_messages if m.get("role") == "assistant"]
        assert len(assistant_msgs) == 1
        assert "tool_calls" in assistant_msgs[0]
        tc_out = assistant_msgs[0]["tool_calls"][0]
        assert tc_out["id"] == "call_1"
        assert tc_out["type"] == "function"
        assert tc_out["function"]["name"] == "echo"

        # Find tool result message
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_1"
        assert tool_msgs[0]["content"] == "hi"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/runtime/test_runner.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'signalagent.runtime.runner'`

- [ ] **Step 3: Implement AgenticRunner**

```python
# src/signalagent/runtime/runner.py
"""AgenticRunner -- agentic loop with tool calling."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict

from signalagent.core.models import ToolResult
from signalagent.core.protocols import AILayerProtocol, ToolExecutor

logger = logging.getLogger(__name__)


class RunnerResult(BaseModel):
    """Result of an agentic runner execution."""

    model_config = ConfigDict(extra="forbid")

    content: str
    iterations: int
    tool_calls_made: int
    truncated: bool = False


class AgenticRunner:
    """Agentic loop: call AI, execute tools, feed results back, repeat.

    Implements RunnerProtocol. Agents inject their system prompt and
    user content; the runner handles the mechanics of the loop.
    """

    def __init__(
        self,
        ai: AILayerProtocol,
        tool_executor: ToolExecutor,
        tool_schemas: list[dict],
        max_iterations: int,
    ) -> None:
        self._ai = ai
        self._tool_executor = tool_executor
        self._tool_schemas = tool_schemas
        self._max_iterations = max_iterations

    async def run(
        self,
        system_prompt: str,
        user_content: str,
    ) -> RunnerResult:
        """Execute the agentic loop.

        Returns RunnerResult with the final text and execution stats.
        """
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        tools = self._tool_schemas if self._tool_schemas else None
        iterations = 0
        total_tool_calls = 0
        last_content = ""

        while iterations < self._max_iterations:
            iterations += 1

            response = await self._ai.complete(messages=messages, tools=tools)
            last_content = response.content or ""

            if not response.tool_calls:
                # No tool calls -- final answer
                return RunnerResult(
                    content=last_content,
                    iterations=iterations,
                    tool_calls_made=total_tool_calls,
                )

            # Append assistant message with tool calls (LiteLLM format)
            messages.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ],
            })

            # Execute each tool call and append results
            for tc in response.tool_calls:
                total_tool_calls += 1
                try:
                    result = await self._tool_executor(tc.name, tc.arguments)
                except Exception as e:
                    logger.warning("Tool executor raised: %s", e)
                    result = ToolResult(output="", error=str(e))

                if result.error:
                    content = f"Error: {result.error}"
                else:
                    content = result.output

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })

        # Hit iteration limit
        return RunnerResult(
            content=last_content,
            iterations=iterations,
            tool_calls_made=total_tool_calls,
            truncated=True,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/runtime/test_runner.py -v`
Expected: All PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/signalagent/runtime/runner.py tests/unit/runtime/test_runner.py
git commit -m "feat: add AgenticRunner with tool-calling loop, error recovery, and iteration limits"
```

---

### Task 8: Refactor MicroAgent, update bootstrap and dependent tests

MicroAgent drops its direct `ai` reference and delegates all LLM interaction to the runner. Bootstrap wires the tool pipeline. All dependent tests updated in the same task so every commit passes.

**Files:**
- Modify: `src/signalagent/agents/micro.py:1-56`
- Modify: `tests/unit/agents/test_micro.py:1-105`
- Modify: `src/signalagent/runtime/bootstrap.py:1-57`
- Modify: `tests/unit/runtime/test_bootstrap.py:1-108`
- Modify: `tests/unit/agents/test_prime.py:1-254`

- [ ] **Step 1: Update test_micro.py for runner-based MicroAgent**

Replace the entire test file:

```python
# tests/unit/agents/test_micro.py
"""Unit tests for MicroAgent -- mock runner only."""

import pytest
from unittest.mock import AsyncMock

from signalagent.agents.micro import MicroAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.types import AgentType, MessageType
from signalagent.runtime.runner import RunnerResult


def _make_config(
    name: str = "code-review",
    skill: str = "Code quality, security, style consistency",
) -> MicroAgentConfig:
    return MicroAgentConfig(name=name, skill=skill)


def _make_runner_result(content: str = "Review complete.") -> RunnerResult:
    return RunnerResult(
        content=content,
        iterations=1,
        tool_calls_made=0,
    )


def _make_task_message(content: str = "Review this code") -> Message:
    return Message(
        id="msg_test0001",
        type=MessageType.TASK,
        sender="prime",
        recipient="code-review",
        content=content,
    )


class TestMicroAgentConstruction:
    def test_name_from_config(self):
        config = _make_config(name="git-agent")
        mock_runner = AsyncMock()
        agent = MicroAgent(config=config, runner=mock_runner)
        assert agent.name == "git-agent"
        assert agent.agent_type == AgentType.MICRO

    def test_skill_property_returns_config_skill(self):
        config = _make_config(name="code-review", skill="Code quality")
        mock_runner = AsyncMock()
        agent = MicroAgent(config=config, runner=mock_runner)
        assert agent.skill == "Code quality"

    def test_system_prompt_contains_name_and_skill(self):
        config = _make_config(name="code-review", skill="Code quality")
        mock_runner = AsyncMock()
        agent = MicroAgent(config=config, runner=mock_runner)
        prompt = agent._system_prompt
        assert "code-review" in prompt
        assert "Code quality" in prompt
        assert "specialist micro-agent" in prompt


class TestMicroAgentExecution:
    @pytest.mark.asyncio
    async def test_delegates_to_runner(self):
        config = _make_config()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        agent = MicroAgent(config=config, runner=mock_runner)

        msg = _make_task_message()
        await agent._handle(msg)

        mock_runner.run.assert_called_once()
        call_kwargs = mock_runner.run.call_args.kwargs
        assert "code-review" in call_kwargs["system_prompt"]
        assert call_kwargs["user_content"] == "Review this code"

    @pytest.mark.asyncio
    async def test_returns_result_message(self):
        config = _make_config()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result("All good."))
        agent = MicroAgent(config=config, runner=mock_runner)

        msg = _make_task_message()
        result = await agent._handle(msg)

        assert result is not None
        assert result.type == MessageType.RESULT
        assert result.content == "All good."
        assert result.sender == "code-review"
        assert result.recipient == "prime"
        assert result.parent_id == "msg_test0001"

    @pytest.mark.asyncio
    async def test_runner_error_propagates(self):
        config = _make_config()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=Exception("LLM down"))
        agent = MicroAgent(config=config, runner=mock_runner)

        msg = _make_task_message()
        with pytest.raises(Exception, match="LLM down"):
            await agent._handle(msg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_micro.py -v`
Expected: FAIL -- `MicroAgent.__init__() got an unexpected keyword argument 'runner'` (since MicroAgent still takes `ai`)

- [ ] **Step 3: Refactor MicroAgent**

Replace `src/signalagent/agents/micro.py`:

```python
# src/signalagent/agents/micro.py
"""MicroAgent -- skill-based specialist agent."""

from __future__ import annotations

from signalagent.agents.base import BaseAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.protocols import RunnerProtocol
from signalagent.core.types import AgentType, MessageType


class MicroAgent(BaseAgent):
    """Specialist agent that handles tasks using a skill-based system prompt.

    Delegates all LLM interaction to an injected RunnerProtocol. The runner
    handles the agentic loop (tool calling, iteration, error recovery).
    """

    def __init__(self, config: MicroAgentConfig, runner: RunnerProtocol) -> None:
        super().__init__(name=config.name, agent_type=AgentType.MICRO)
        self._config = config
        self._runner = runner
        self._system_prompt = self._build_system_prompt()

    @property
    def skill(self) -> str:
        """Agent's skill description from config."""
        return self._config.skill

    def _build_system_prompt(self) -> str:
        """Generate system prompt from template + config."""
        return (
            f"You are {self._config.name}, a specialist micro-agent "
            f"in the Signal system.\n\n"
            f"Your skill: {self._config.skill}\n\n"
            "You receive tasks from the Prime agent. "
            "Complete the task and return your results."
        )

    async def _handle(self, message: Message) -> Message | None:
        """Execute task via runner. Runner handles tool loop."""
        result = await self._runner.run(
            system_prompt=self._system_prompt,
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/test_micro.py -v`
Expected: All PASS (6 tests)

- [ ] **Step 5: Update bootstrap.py**

Replace `src/signalagent/runtime/bootstrap.py`:

```python
# src/signalagent/runtime/bootstrap.py
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
from signalagent.runtime.executor import Executor
from signalagent.runtime.runner import AgenticRunner
from signalagent.tools.builtins import load_builtin_tool
from signalagent.tools.registry import ToolRegistry


async def bootstrap(
    instance_dir: Path,
    config: SignalConfig,
    profile: Profile,
) -> tuple[Executor, MessageBus, AgentHost]:
    """Wire up the full multi-agent runtime.

    1. Create AILayer from config
    2. Create MessageBus
    3. Create AgentHost with bus
    4. Create ToolRegistry, load built-in tools from profile
    5. Create ToolExecutor callable (wraps registry + error handling)
    6. Create and register PrimeAgent (talks_to=None, unrestricted, no tools)
    7. Create and register micro-agents with runners from profile
    8. Create Executor with bus
    9. Return (executor, bus, host)

    USER_SENDER is not registered on the bus. The bus explicitly
    allows it as a sender without registration (virtual sender).
    """
    ai = AILayer(config)
    bus = MessageBus()
    host = AgentHost(bus)

    # Tool registry -- load tools declared in profile
    registry = ToolRegistry()
    for tool_name in profile.plugins.available:
        tool = load_builtin_tool(tool_name, instance_dir)
        if tool is not None:
            registry.register(tool)

    # Tool executor -- thin wrapper, 4b replaces with hook-aware version
    async def tool_executor(tool_name: str, arguments: dict) -> ToolResult:
        tool = registry.get(tool_name)
        if tool is None:
            return ToolResult(output="", error=f"Unknown tool: {tool_name}")
        try:
            return await tool.execute(**arguments)
        except Exception as e:
            return ToolResult(output="", error=str(e))

    global_max = config.tools.max_iterations

    # Prime agent (no tools, routing + direct handling only)
    prime = PrimeAgent(
        identity=profile.prime.identity,
        ai=ai,
        host=host,
        bus=bus,
    )
    host.register(prime, talks_to=None)

    # Micro-agents from profile, each with their own runner
    for micro_config in profile.micro_agents:
        agent_max = min(micro_config.max_iterations, global_max)
        tool_schemas = registry.get_schemas(micro_config.plugins)
        runner = AgenticRunner(
            ai=ai,
            tool_executor=tool_executor,
            tool_schemas=tool_schemas,
            max_iterations=agent_max,
        )
        agent = MicroAgent(config=micro_config, runner=runner)
        # Always convert to set -- empty list [] becomes empty set() (talk to
        # nobody), not None (unrestricted). Only Prime gets talks_to=None.
        talks_to = set(micro_config.talks_to)
        host.register(agent, talks_to=talks_to)

    executor = Executor(bus=bus)
    return executor, bus, host
```

- [ ] **Step 6: Update test_bootstrap.py**

Replace `tests/unit/runtime/test_bootstrap.py`:

```python
# tests/unit/runtime/test_bootstrap.py
"""Unit tests for bootstrap -- all real objects, only AILayer mocked."""

import pytest
from unittest.mock import AsyncMock

from signalagent.ai.layer import AIResponse
from signalagent.core.config import SignalConfig
from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
    PluginsConfig,
    ToolCallRequest,
)
from signalagent.core.types import PRIME_AGENT
from signalagent.runtime.bootstrap import bootstrap


def _make_ai_response(content: str, tool_calls: list | None = None) -> AIResponse:
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
        tool_calls=tool_calls or [],
    )


@pytest.fixture
def config() -> SignalConfig:
    return SignalConfig(profile_name="test")


@pytest.fixture
def profile_with_micros() -> Profile:
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        micro_agents=[
            MicroAgentConfig(
                name="code-review",
                skill="Code quality",
                talks_to=["prime"],
            ),
            MicroAgentConfig(
                name="git",
                skill="Version control",
                talks_to=["prime", "code-review"],
            ),
        ],
    )


@pytest.fixture
def profile_no_micros() -> Profile:
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
    )


@pytest.fixture
def profile_with_tools() -> Profile:
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="researcher",
                skill="Research files",
                talks_to=["prime"],
                plugins=["file_system"],
            ),
        ],
    )


class TestBootstrap:
    @pytest.mark.asyncio
    async def test_returns_executor_bus_host(self, tmp_path, config, profile_with_micros, monkeypatch):
        mock_ai_class = AsyncMock()
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", mock_ai_class)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_micros)

        assert executor is not None
        assert bus is not None
        assert host is not None
        assert host.get(PRIME_AGENT) is not None
        assert host.get("code-review") is not None
        assert host.get("git") is not None

    @pytest.mark.asyncio
    async def test_end_to_end_routing(self, tmp_path, config, profile_with_micros, monkeypatch):
        """Full path: executor -> bus -> Prime -> routing -> bus -> micro -> response."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            side_effect=[
                _make_ai_response("code-review"),       # Prime routing call
                _make_ai_response("Review complete"),    # MicroAgent via runner (no tools)
            ]
        )
        mock_ai_class = lambda config: mock_ai
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", mock_ai_class)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_micros)
        result = await executor.run("review my code")

        assert result.content == "Review complete"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_no_micros_prime_handles_directly(self, tmp_path, config, profile_no_micros, monkeypatch):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("I handled it"),
        )
        mock_ai_class = lambda config: mock_ai
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", mock_ai_class)

        executor, bus, host = await bootstrap(tmp_path, config, profile_no_micros)
        result = await executor.run("hello")

        assert result.content == "I handled it"
        assert mock_ai.complete.call_count == 1

    @pytest.mark.asyncio
    async def test_micro_agent_uses_tool(self, tmp_path, config, profile_with_tools, monkeypatch):
        """Micro-agent calls file_system tool via runner, gets result, returns final text."""
        # Write a test file in the instance dir
        (tmp_path / "notes.txt").write_text("important data")

        tc = ToolCallRequest(id="call_1", name="file_system", arguments={"operation": "read", "path": "notes.txt"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            side_effect=[
                _make_ai_response("researcher"),                  # Prime routing
                _make_ai_response("", tool_calls=[tc]),           # Runner iteration 1: tool call
                _make_ai_response("Found: important data"),       # Runner iteration 2: final text
            ]
        )
        mock_ai_class = lambda config: mock_ai
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", mock_ai_class)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_tools)
        result = await executor.run("read my notes")

        assert result.content == "Found: important data"
        assert result.error is None
```

- [ ] **Step 7: Update test_prime.py to use runner-based micro-agents**

In `tests/unit/agents/test_prime.py`, the `StubMicro` class is a `BaseAgent` subclass, not a `MicroAgent`, so it doesn't need a runner and is unaffected. However, the file imports `MicroAgent` and `MicroAgentConfig` -- verify these are not used in the test class construction. If `MicroAgent` is imported but unused, remove the import.

Check lines 8-9:
```python
from signalagent.agents.micro import MicroAgent
```

If this import exists but `MicroAgent` is not directly constructed in the test file, remove it to prevent import errors. The `StubMicro` class extending `BaseAgent` directly is correct for these tests.

- [ ] **Step 8: Run all tests**

Run: `uv run pytest -x -q`
Expected: All tests pass

- [ ] **Step 9: Commit**

```bash
git add src/signalagent/agents/micro.py tests/unit/agents/test_micro.py src/signalagent/runtime/bootstrap.py tests/unit/runtime/test_bootstrap.py tests/unit/agents/test_prime.py
git commit -m "feat: MicroAgent delegates to runner, wire tool pipeline in bootstrap"
```

---

### Task 9: Update docs, bump version, verify end-to-end

Update architecture docs, project structure, roadmap, README, CHANGELOG, and VERSION.

**Files:**
- Modify: `docs/dev/architecture.md`
- Modify: `docs/dev/project-structure.md`
- Modify: `docs/dev/testing.md`
- Modify: `docs/dev/roadmap.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`
- Modify: `src/signalagent/__init__.py`

- [ ] **Step 1: Run full test suite and count**

Run: `uv run pytest -x -q`
Expected: All pass. Note the test count (should be ~200+).

- [ ] **Step 2: Update architecture.md**

Add a "Tool Execution Architecture" subsection under "Current Architecture" describing:
- AgenticRunner loop (call AI, execute tools, feed back, repeat)
- ToolRegistry for name-to-implementation lookup
- ToolExecutor as injected callable (hook point for 4b)
- FileSystemTool as the first built-in tool
- Two-tier iteration limits
- Update "Current Architecture" header to say "Phase 4a"
- Update module dependency diagram to include tools/ and runtime/runner

- [ ] **Step 3: Update project-structure.md**

Add the new files:
- `core/protocols.py` -- protocol definitions (AILayerProtocol, RunnerProtocol, ToolExecutor)
- `tools/` -- tool protocol, registry, builtins
- `tools/builtins/` -- built-in tool implementations
- `runtime/runner.py` -- AgenticRunner

Update "Modules Planned but Not Yet Created" to remove `tools/` (now created) and mark `plugins/` as remaining for 4b.

Add new test directories.

- [ ] **Step 4: Update roadmap.md**

Change Phase 4 row to show two sub-phases:
- Phase 4a: Tool Execution + Agentic Loop -- Complete
- Phase 4b: Hooks + Sub-Agents -- Planned

- [ ] **Step 5: Update testing.md**

Update test count. Add section about tool execution test patterns (mock AI with tool_calls, mock executor, tmp_path for file system tool).

- [ ] **Step 6: Update README.md**

Update status line to Phase 4a and describe what's new: agents can now call tools, agentic loop, file system tool.

- [ ] **Step 7: Update CHANGELOG.md**

Add `## [0.4.0] - 2026-03-31` section with all Phase 4a additions.

- [ ] **Step 8: Bump version**

In `src/signalagent/__init__.py`:
```python
__version__ = "0.4.0"
```

In `VERSION`:
```
0.4.0
```

- [ ] **Step 9: Run full test suite one final time**

Run: `uv run pytest -v`
Expected: All pass

- [ ] **Step 10: Commit**

```bash
git add docs/ README.md CHANGELOG.md VERSION src/signalagent/__init__.py
git commit -m "docs: update architecture, structure, testing, and roadmap for Phase 4a"
```

```bash
git commit -m "chore: bump version to 0.4.0 for Phase 4a tool execution"
```

---

## Self-Review

**Spec coverage check:**
- (a) AILayer tools param + tool_calls: Task 3
- (b) ToolRegistry + LiteLLM schemas: Task 4
- (c) AgenticRunner loop: Task 7
- (d) ToolExecutor error handling: Task 7 (runner catches), Task 9 (bootstrap executor)
- (e) FileSystemTool: Task 5
- (f) Two-tier iteration limits: Task 2 (models), Task 9 (bootstrap clamping)
- (g) MicroAgent delegates to RunnerProtocol: Task 8
- (h) End-to-end signal talk: Task 8 (test_micro_agent_uses_tool)
- (i) Protocols in core/: Task 1 (AILayerProtocol), Task 6 (RunnerProtocol, ToolExecutor)
- (j) Multiple tool calls per iteration: Task 7 (test_multiple_tool_calls_in_one_response)

All 10 done-when criteria covered.

**Placeholder scan:** No TBD, TODO, "implement later", or vague steps found.

**Type consistency check:**
- `ToolCallRequest` used consistently across Task 2 (model), Task 3 (AIResponse), Task 7 (runner tests), Task 9 (bootstrap tests)
- `ToolResult` used consistently across Task 2 (model), Task 4 (FakeTool), Task 5 (FileSystemTool), Task 7 (runner tests), Task 9 (bootstrap executor)
- `RunnerResult` defined in Task 7, used in Task 8 (test_micro.py, test_bootstrap.py)
- `RunnerProtocol` defined in Task 6, used by MicroAgent in Task 8
- `MicroAgent(config=, runner=)` signature consistent between Task 8 (implementation and bootstrap)
- `AgenticRunner.__init__(ai=, tool_executor=, tool_schemas=, max_iterations=)` consistent between Task 7 (implementation) and Task 8 (bootstrap wiring)
- `ToolRegistry.get_schemas(names)` consistent between Task 4 (implementation) and Task 8 (bootstrap call)
- `load_builtin_tool(name, instance_dir)` consistent between Task 5 (implementation) and Task 8 (bootstrap call)
