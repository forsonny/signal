"""Unit tests for HookRegistry."""
from signalagent.core.models import ToolResult
from signalagent.hooks.registry import HookRegistry

class FakeHook:
    def __init__(self, name: str = "test_hook"):
        self._name = name
    @property
    def name(self) -> str:
        return self._name
    async def before_tool_call(self, tool_name, arguments):
        return None
    async def after_tool_call(self, tool_name, arguments, result, blocked):
        pass

class TestHookRegistryRegisterAndGetAll:
    def test_empty_registry(self):
        assert HookRegistry().get_all() == []
    def test_register_and_get_all(self):
        registry = HookRegistry()
        hook = FakeHook()
        registry.register(hook)
        assert registry.get_all() == [hook]
    def test_register_multiple(self):
        registry = HookRegistry()
        h1, h2 = FakeHook(name="a"), FakeHook(name="b")
        registry.register(h1)
        registry.register(h2)
        assert len(registry.get_all()) == 2
        assert h1 in registry.get_all()
    def test_get_all_preserves_order(self):
        registry = HookRegistry()
        h1, h2 = FakeHook(name="first"), FakeHook(name="second")
        registry.register(h1)
        registry.register(h2)
        assert registry.get_all() == [h1, h2]
