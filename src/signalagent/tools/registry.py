"""ToolRegistry -- lookup layer for tool resolution and schema generation."""
from __future__ import annotations
from signalagent.tools.protocol import Tool


class ToolRegistry:
    """Registry that stores tools by name and generates LLM schemas.

    Tools are registered once at startup and looked up by name during
    the agentic loop when the LLM invokes a function call.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Add a tool to the registry, keyed by its name.

        Args:
            tool: Any object satisfying the Tool protocol.
        """
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Retrieve a tool by name.

        Args:
            name: The unique tool name.

        Returns:
            The registered Tool, or None if not found.
        """
        return self._tools.get(name)

    def get_schemas(self, names: list[str]) -> list[dict]:
        """Return LiteLLM-format tool definitions for the given names.

        Unknown names are silently skipped so callers need not
        pre-validate.

        Args:
            names: Tool names to include in the schema list.

        Returns:
            List of dicts, each with ``type`` and ``function`` keys
            conforming to the LiteLLM tool-call format.
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
