"""Unit tests for ToolRegistry."""
import pytest
from signalagent.core.models import ToolResult
from signalagent.tools.registry import ToolRegistry

class FakeTool:
    def __init__(self, name: str = "echo", description: str = "Echoes input"):
        self._name = name
        self._description = description
    @property
    def name(self) -> str: return self._name
    @property
    def description(self) -> str: return self._description
    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
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
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "echo"
        assert schemas[0]["function"]["description"] == "Echoes input"
        assert schemas[0]["function"]["parameters"]["type"] == "object"
    def test_skips_unknown_names(self):
        registry = ToolRegistry()
        registry.register(FakeTool(name="echo"))
        assert len(registry.get_schemas(["echo", "missing"])) == 1
    def test_empty_names_returns_empty(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        assert registry.get_schemas([]) == []
    def test_multiple_tools(self):
        registry = ToolRegistry()
        registry.register(FakeTool(name="a", description="Tool A"))
        registry.register(FakeTool(name="b", description="Tool B"))
        schemas = registry.get_schemas(["a", "b"])
        assert len(schemas) == 2
        assert {s["function"]["name"] for s in schemas} == {"a", "b"}
