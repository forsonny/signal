"""ToolRegistry -- lookup layer for tool resolution and schema generation."""
from __future__ import annotations
from signalagent.tools.protocol import Tool

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_schemas(self, names: list[str]) -> list[dict]:
        """Return LiteLLM-format tool definitions. Unknown names silently skipped."""
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
