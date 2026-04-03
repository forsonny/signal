"""Protocol definitions for dependency injection across packages.

All protocol types that agents and tools depend on live here. Concrete
implementations live in their respective packages (ai/, runtime/, memory/).
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
    ) -> Any:
        """Send a completion request to an LLM provider.

        Args:
            messages: Chat messages in OpenAI format.
            model: Model identifier override. Falls back to config default.
            tools: Tool definitions in LiteLLM function-calling format.

        Returns:
            AIResponse (or compatible) with content and optional tool_calls.
        """
        ...


@runtime_checkable
class RunnerProtocol(Protocol):
    """Protocol for the agentic loop runner.

    Agents depend on this protocol, not the concrete AgenticRunner.
    """

    async def run(
        self,
        system_prompt: str,
        user_content: str,
        history: list[dict] | None = None,
    ) -> Any:
        """Execute the agentic loop with tool calling.

        Args:
            system_prompt: System-level instruction for the LLM.
            user_content: The user's message or task description.
            history: Optional prior conversation turns.

        Returns:
            RunnerResult (or compatible) with content, iterations, and
            tool_calls_made.
        """
        ...


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
    ) -> Any:
        """Execute a tool by name with the given arguments.

        Args:
            tool_name: Registered name of the tool to invoke.
            arguments: Parsed arguments from the LLM tool call.

        Returns:
            ToolResult with output or error.
        """
        ...


@runtime_checkable
class MemoryReaderProtocol(Protocol):
    """Protocol for memory retrieval so agents don't depend on concrete engine.

    Same pattern as AILayerProtocol -- agents import this, bootstrap injects
    the concrete MemoryEngine.
    """

    async def search(
        self,
        tags: list[str] | None = None,
        agent: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
        touch: bool = False,
        query: str | None = None,
    ) -> list[Any]:
        """Search memories by tags, agent, type, or semantic query.

        Args:
            tags: Tags to match against. Memories must share at least one.
            agent: Filter to a specific agent name.
            memory_type: Filter to a specific memory type string.
            limit: Maximum number of results to return.
            touch: If True, update access stats for returned memories.
            query: Text to embed for semantic search. Optional.

        Returns:
            List of Memory objects matching the criteria.
        """
        ...


@runtime_checkable
class EmbeddingProtocol(Protocol):
    """Protocol for embedding text into vectors.

    Bootstrap injects the concrete implementation (LiteLLM default).
    The protocol allows swapping in local models without changing consumers.
    """

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vector representations.

        Args:
            texts: List of strings to embed.

        Returns:
            List of float vectors, one per input text.
        """
        ...


@runtime_checkable
class WorktreeProxyProtocol(Protocol):
    """Protocol for worktree proxy -- agents call take_result() after task completion.

    task_lock() returns an asyncio.Lock for fork branch serialization.
    """

    def take_result(self) -> Any:
        """Retrieve and clear the last worktree execution result.

        Returns:
            WorktreeResult with changed files and branch info, or None
            if no worktree changes occurred.
        """
        ...

    def task_lock(self) -> Any:
        """Return an async context manager for serializing fork operations.

        Returns:
            asyncio.Lock instance for branch serialization.
        """
        ...
