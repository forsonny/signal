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
    HooksConfig,
    ToolCallRequest,
)
from signalagent.core.types import PRIME_AGENT
from signalagent.runtime.bootstrap import bootstrap


def _make_ai_response(content: str, tool_calls: list | None = None) -> AIResponse:
    return AIResponse(content=content, model="test-model", provider="test",
                      input_tokens=10, output_tokens=20,
                      tool_calls=tool_calls or [])


@pytest.fixture
def config():
    return SignalConfig(profile_name="test")

@pytest.fixture
def profile_with_micros():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        micro_agents=[
            MicroAgentConfig(name="code-review", skill="Code quality", talks_to=["prime"]),
            MicroAgentConfig(name="git", skill="Version control", talks_to=["prime", "code-review"]),
        ],
    )

@pytest.fixture
def profile_no_micros():
    return Profile(name="test", prime=PrimeConfig(identity="You are a test prime."))

@pytest.fixture
def profile_with_tools():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(name="researcher", skill="Research files",
                             talks_to=["prime"], plugins=["file_system"]),
        ],
    )

@pytest.fixture
def profile_with_hooks():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        hooks=HooksConfig(active=["log_tool_calls"]),
        micro_agents=[
            MicroAgentConfig(name="researcher", skill="Research files",
                             talks_to=["prime"], plugins=["file_system"]),
        ],
    )


@pytest.fixture
def profile_with_spawn():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="manager", skill="Task management",
                talks_to=["prime"], plugins=["file_system"],
                can_spawn_subs=True,
            ),
        ],
    )


@pytest.fixture
def profile_without_spawn():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="worker", skill="Basic work",
                talks_to=["prime"], plugins=["file_system"],
                can_spawn_subs=False,
            ),
        ],
    )


class TestBootstrap:
    @pytest.mark.asyncio
    async def test_returns_executor_bus_host(self, tmp_path, config, profile_with_micros, monkeypatch):
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", AsyncMock())
        executor, bus, host = await bootstrap(tmp_path, config, profile_with_micros)
        assert executor is not None
        assert host.get(PRIME_AGENT) is not None
        assert host.get("code-review") is not None
        assert host.get("git") is not None

    @pytest.mark.asyncio
    async def test_end_to_end_routing(self, tmp_path, config, profile_with_micros, monkeypatch):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("code-review"),
            _make_ai_response("Review complete"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)
        executor, bus, host = await bootstrap(tmp_path, config, profile_with_micros)
        result = await executor.run("review my code")
        assert result.content == "Review complete"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_no_micros_prime_handles_directly(self, tmp_path, config, profile_no_micros, monkeypatch):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("I handled it"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)
        executor, bus, host = await bootstrap(tmp_path, config, profile_no_micros)
        result = await executor.run("hello")
        assert result.content == "I handled it"
        assert mock_ai.complete.call_count == 1

    @pytest.mark.asyncio
    async def test_micro_agent_uses_tool(self, tmp_path, config, profile_with_tools, monkeypatch):
        (tmp_path / "notes.txt").write_text("important data")
        tc = ToolCallRequest(id="call_1", name="file_system",
                             arguments={"operation": "read", "path": "notes.txt"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("", tool_calls=[tc]),
            _make_ai_response("Found: important data"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)
        executor, bus, host = await bootstrap(tmp_path, config, profile_with_tools)
        result = await executor.run("read my notes")
        assert result.content == "Found: important data"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_hooks_log_tool_calls(self, tmp_path, config, profile_with_hooks, monkeypatch):
        """Tool calls are logged to JSONL when log_tool_calls hook is active."""
        (tmp_path / "notes.txt").write_text("data")
        tc = ToolCallRequest(id="call_1", name="file_system",
                             arguments={"operation": "read", "path": "notes.txt"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("", tool_calls=[tc]),
            _make_ai_response("Got it"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)
        executor, bus, host = await bootstrap(tmp_path, config, profile_with_hooks)
        result = await executor.run("read notes")
        assert result.content == "Got it"

        # Verify log file was written
        import json
        log_file = tmp_path / "logs" / "tool_calls.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["tool_name"] == "file_system"
        assert entry["blocked"] is False

    @pytest.mark.asyncio
    async def test_sub_agent_spawn_end_to_end(self, tmp_path, config, profile_with_spawn, monkeypatch):
        """Micro-agent spawns sub-agent, sub-agent uses tool, result flows back."""
        (tmp_path / "data.txt").write_text("secret info")

        spawn_tc = ToolCallRequest(
            id="call_1", name="spawn_sub_agent",
            arguments={"task": "Read data.txt and summarize", "skill": "File analysis"},
        )
        file_tc = ToolCallRequest(
            id="call_2", name="file_system",
            arguments={"operation": "read", "path": "data.txt"},
        )

        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            # Prime routes to manager
            _make_ai_response("manager"),
            # Manager's runner: LLM calls spawn_sub_agent
            _make_ai_response("", tool_calls=[spawn_tc]),
            # Sub-agent's runner: LLM calls file_system
            _make_ai_response("", tool_calls=[file_tc]),
            # Sub-agent's runner: LLM returns final text
            _make_ai_response("File contains: secret info"),
            # Manager's runner: LLM returns final text (after getting spawn result)
            _make_ai_response("Sub-agent found: secret info"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_spawn)
        result = await executor.run("analyze data.txt")

        assert result.content == "Sub-agent found: secret info"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_no_spawn_without_can_spawn_subs(self, tmp_path, config, profile_without_spawn, monkeypatch):
        """Micro-agent without can_spawn_subs does NOT get spawn_sub_agent tool."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("worker"),
            _make_ai_response("Done"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_without_spawn)

        # Verify the worker's AI call did NOT receive spawn_sub_agent in tools
        await executor.run("do something")
        worker_call = mock_ai.complete.call_args_list[1]
        tools = worker_call.kwargs.get("tools") or []
        tool_names = [t["function"]["name"] for t in tools]
        assert "spawn_sub_agent" not in tool_names
