# Extending Tools

## What you'll learn

- The Tool protocol and what every tool must implement
- How to define JSON Schema parameters for LLM function calling
- How to register a tool and make it available to agents
- How to test a custom tool
- A complete working example

---

## Tool protocol

Every tool in Signal implements the `Tool` protocol defined in
`src/signalagent/tools/protocol.py`:

```python
class Tool(Protocol):
    @property
    def name(self) -> str:
        """Unique tool name used for LLM function calling."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description shown to the LLM."""
        ...

    @property
    def parameters(self) -> dict:
        """JSON Schema for the tool's arguments."""
        ...

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given arguments."""
        ...
```

You do not need to inherit from a base class or explicitly declare that
you implement the protocol. Any class with these four members satisfies
the protocol (structural subtyping).

---

## Implementing a custom tool

### Step 1: Create the tool class

Create a new file in `src/signalagent/tools/builtins/` (for built-in
tools) or in your own package:

```python
"""HttpFetchTool -- fetch a URL and return its text content."""
from __future__ import annotations

import httpx

from signalagent.core.models import ToolResult


class HttpFetchTool:
    """Fetches a URL and returns the response body as text."""

    def __init__(self, max_bytes: int = 512_000) -> None:
        """Initialise the HTTP fetch tool.

        Args:
            max_bytes: Maximum response body size before truncation.
        """
        self._max_bytes = max_bytes

    @property
    def name(self) -> str:
        return "http_fetch"

    @property
    def description(self) -> str:
        return "Fetch a URL and return its text content."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch.",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "HEAD"],
                    "description": "HTTP method (default: GET).",
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        """Fetch the URL and return the response body.

        Args:
            **kwargs: Must include ``url``. Optional: ``method``.

        Returns:
            ToolResult with the response text or an error message.
        """
        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET").upper()

        if not url:
            return ToolResult(output="", error="Missing required parameter: url")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, follow_redirects=True)
                response.raise_for_status()
                body = response.text[:self._max_bytes]
                if len(response.text) > self._max_bytes:
                    body += "\n[truncated]"
                return ToolResult(output=body)
        except httpx.HTTPStatusError as e:
            return ToolResult(output="", error=f"HTTP {e.response.status_code}: {e}")
        except Exception as e:
            return ToolResult(output="", error=str(e))
```

### Step 2: Define JSON Schema parameters

The `parameters` property returns a standard JSON Schema object. The LLM
uses this schema to generate valid tool call arguments.

Key rules:

- The top-level type must be `"object"`.
- List required parameters in the `"required"` array.
- Use `"description"` on every property -- this is what the LLM reads.
- Use `"enum"` for constrained string values.
- Keep the schema flat when possible. Nested objects work but increase
  the chance of malformed LLM output.

### Step 3: Register the tool in bootstrap

Add the tool to the `load_builtin_tool` factory in
`src/signalagent/tools/builtins/__init__.py`:

```python
def load_builtin_tool(name: str, instance_dir: Path) -> "Tool | None":
    if name == "file_system":
        from signalagent.tools.builtins.file_system import FileSystemTool
        return FileSystemTool(root=instance_dir)
    if name == "http_fetch":
        from signalagent.tools.builtins.http_fetch import HttpFetchTool
        return HttpFetchTool()
    return None
```

The deferred import pattern keeps unused tools out of the import graph.

### Step 4: Make the tool available to agents

Add the tool name to the profile's `plugins.available` list and to
each agent's `plugins` list:

```yaml
plugins:
  available:
    - file_system
    - http_fetch

micro_agents:
  - name: researcher
    skill: "Search the web and summarize findings"
    plugins:
      - file_system
      - http_fetch
```

At bootstrap, `ToolRegistry.get_schemas()` generates the LiteLLM-format
function definitions for each agent's tool set. These schemas are passed
to every LLM call in the agentic loop.

---

## How tools are called at runtime

```
1. LLM returns tool_calls: [{name: "http_fetch", arguments: {url: "..."}}]
2. AgenticRunner iterates tool_calls
3. For each: calls tool_executor(tool_name, arguments)
4. WorktreeProxy (if file_system: may redirect to worktree)
5. HookExecutor runs before_tool_call hooks
6. Inner executor: registry.get(name).execute(**arguments)
7. HookExecutor runs after_tool_call hooks
8. ToolResult is appended to message history
9. Loop: LLM sees the result and decides next action
```

Errors in `execute()` are caught by the inner executor and returned as
`ToolResult(error=...)`. The runner feeds the error back to the LLM,
which can retry or try a different approach.

---

## Testing a custom tool

### Direct execution test

```python
import pytest
from signalagent.core.models import ToolResult


class TestHttpFetchTool:
    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        from my_tools.http_fetch import HttpFetchTool

        tool = HttpFetchTool()
        # Use a mock or test server in real tests
        result = await tool.execute(url="https://httpbin.org/get")
        assert result.error is None
        assert result.output  # non-empty response

    @pytest.mark.asyncio
    async def test_missing_url(self):
        from my_tools.http_fetch import HttpFetchTool

        tool = HttpFetchTool()
        result = await tool.execute()
        assert result.error == "Missing required parameter: url"

    def test_protocol_compliance(self):
        from my_tools.http_fetch import HttpFetchTool

        tool = HttpFetchTool()
        assert tool.name == "http_fetch"
        assert tool.description
        params = tool.parameters
        assert params["type"] == "object"
        assert "url" in params["properties"]
        assert "url" in params["required"]
```

### Registry integration test

```python
from signalagent.tools.registry import ToolRegistry


def test_registry_generates_schema():
    tool = HttpFetchTool()
    registry = ToolRegistry()
    registry.register(tool)

    schemas = registry.get_schemas(["http_fetch"])
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "http_fetch"
```

### End-to-end runner test

```python
from unittest.mock import AsyncMock
from signalagent.ai.layer import AIResponse
from signalagent.core.models import ToolCallRequest, ToolResult
from signalagent.runtime.runner import AgenticRunner


class TestHttpFetchInRunner:
    @pytest.mark.asyncio
    async def test_runner_calls_tool(self):
        tc = ToolCallRequest(
            id="call_1", name="http_fetch",
            arguments={"url": "https://example.com"},
        )
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            AIResponse(content="", model="test", provider="test",
                       tool_calls=[tc]),
            AIResponse(content="Page fetched.", model="test",
                       provider="test", tool_calls=[]),
        ])
        mock_executor = AsyncMock(
            return_value=ToolResult(output="<html>...</html>")
        )
        runner = AgenticRunner(
            ai=mock_ai, tool_executor=mock_executor,
            tool_schemas=[{"type": "function",
                           "function": {"name": "http_fetch"}}],
            max_iterations=10,
        )
        result = await runner.run(
            system_prompt="You can fetch URLs.",
            user_content="Get example.com",
        )
        mock_executor.assert_called_once_with(
            "http_fetch", {"url": "https://example.com"},
        )
        assert result.content == "Page fetched."
```

---

## Design guidelines

### Return errors, do not raise

Tools should catch their own exceptions and return
`ToolResult(output="", error=...)`. The runner has an error boundary
that catches exceptions, but returning errors gives the LLM cleaner
feedback.

### Keep execute() fast

Tool calls happen inside the agentic loop. A slow tool blocks the
entire loop iteration. If the operation is inherently slow (large file
download, long-running computation), consider truncation limits or
timeouts.

### Use descriptive parameter schemas

The LLM generates tool call arguments from your JSON Schema. Clear
descriptions and constrained types reduce malformed calls.

### Scope to the instance directory

Tools that access the filesystem should be scoped to the instance
directory. The built-in `FileSystemTool` rejects paths outside its
root directory. Follow this pattern for any tool that touches files.

---

## Next steps

- [Architecture](architecture.md) -- how tools fit into the executor chain
- [Extending Hooks](extending-hooks.md) -- observing and controlling tool calls
- [Extending Agents](extending-agents.md) -- giving agents access to your tool
- [Testing](testing.md) -- more test patterns
