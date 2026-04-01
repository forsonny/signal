"""Unit tests for LogToolCallsHook -- uses tmp_path for isolation."""
import json
import pytest
from signalagent.core.models import ToolResult
from signalagent.hooks.builtins.log_tool_calls import LogToolCallsHook

@pytest.fixture
def hook(tmp_path):
    return LogToolCallsHook(log_dir=tmp_path)

@pytest.fixture
def log_file(tmp_path):
    return tmp_path / "tool_calls.jsonl"

class TestLogToolCallsHookProperties:
    def test_name(self, hook):
        assert hook.name == "log_tool_calls"

class TestLogToolCallsBeforeHook:
    @pytest.mark.asyncio
    async def test_always_allows(self, hook):
        result = await hook.before_tool_call("file_system", {"op": "read"})
        assert result is None

class TestLogToolCallsAfterHook:
    @pytest.mark.asyncio
    async def test_writes_jsonl_entry(self, hook, log_file):
        await hook.before_tool_call("file_system", {"operation": "read", "path": "test.txt"})
        await hook.after_tool_call(
            "file_system", {"operation": "read", "path": "test.txt"},
            ToolResult(output="hello"), blocked=False,
        )
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["tool_name"] == "file_system"
        assert entry["arguments"] == {"operation": "read", "path": "test.txt"}
        assert entry["error"] is None
        assert entry["blocked"] is False
        assert "timestamp" in entry
        assert "duration_ms" in entry

    @pytest.mark.asyncio
    async def test_logs_error(self, hook, log_file):
        await hook.before_tool_call("file_system", {"op": "read"})
        await hook.after_tool_call(
            "file_system", {"op": "read"},
            ToolResult(output="", error="File not found"), blocked=False,
        )
        entry = json.loads(log_file.read_text().strip())
        assert entry["error"] == "File not found"
        assert entry["blocked"] is False

    @pytest.mark.asyncio
    async def test_logs_blocked_call(self, hook, log_file):
        await hook.before_tool_call("file_system", {})
        await hook.after_tool_call(
            "file_system", {},
            ToolResult(output="", error="Blocked: policy"), blocked=True,
        )
        entry = json.loads(log_file.read_text().strip())
        assert entry["blocked"] is True
        assert entry["error"] == "Blocked: policy"

    @pytest.mark.asyncio
    async def test_appends_multiple_entries(self, hook, log_file):
        for i in range(3):
            await hook.before_tool_call("tool", {"i": i})
            await hook.after_tool_call("tool", {"i": i}, ToolResult(output=f"r{i}"), blocked=False)
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_creates_log_dir_if_missing(self, tmp_path):
        log_dir = tmp_path / "nested" / "logs"
        hook = LogToolCallsHook(log_dir=log_dir)
        await hook.before_tool_call("t", {})
        await hook.after_tool_call("t", {}, ToolResult(output="ok"), blocked=False)
        assert (log_dir / "tool_calls.jsonl").exists()

    @pytest.mark.asyncio
    async def test_duration_is_positive(self, hook, log_file):
        await hook.before_tool_call("t", {})
        await hook.after_tool_call("t", {}, ToolResult(output="ok"), blocked=False)
        entry = json.loads(log_file.read_text().strip())
        assert entry["duration_ms"] >= 0

class TestLoadBuiltinHook:
    def test_loads_log_tool_calls(self, tmp_path):
        from signalagent.hooks.builtins import load_builtin_hook
        hook = load_builtin_hook("log_tool_calls", tmp_path)
        assert hook is not None
        assert hook.name == "log_tool_calls"

    def test_returns_none_for_unknown(self, tmp_path):
        from signalagent.hooks.builtins import load_builtin_hook
        assert load_builtin_hook("unknown_hook", tmp_path) is None
