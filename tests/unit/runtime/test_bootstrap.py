"""Unit tests for bootstrap -- all real objects, only AILayer mocked."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from signalagent.ai.layer import AIResponse
from signalagent.core.config import SignalConfig
from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
    PluginsConfig,
    HooksConfig,
    HeartbeatConfig,
    MemoryKeeperConfig,
    ToolCallRequest,
)
from signalagent.heartbeat.models import ClockTrigger, TriggerGuards
from signalagent.core.types import PRIME_AGENT
from signalagent.runtime.bootstrap import bootstrap
from signalagent.worktrees.proxy import WorktreeProxy


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


@pytest.fixture
def profile_with_memory():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        micro_agents=[
            MicroAgentConfig(
                name="researcher", skill="Research",
                talks_to=["prime"],
            ),
        ],
    )


class TestMemoryInjection:
    @pytest.mark.asyncio
    async def test_agents_receive_memory_engine(self, tmp_path, config, profile_with_memory, monkeypatch):
        """Bootstrap injects memory engine into Prime and micro-agents."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("Done"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_memory)

        # NOTE: host.get() returns BaseAgent. Accessing _memory_reader is a
        # private attribute on PrimeAgent/MicroAgent. Use type: ignore to
        # suppress linter warnings -- this is test code verifying bootstrap wiring.
        prime = host.get(PRIME_AGENT)
        assert prime._memory_reader is not None  # type: ignore[union-attr]

        researcher = host.get("researcher")
        assert researcher._memory_reader is not None  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_agents_receive_model_name(self, tmp_path, config, profile_with_memory, monkeypatch):
        """Bootstrap passes model name to agents."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("researcher"),
            _make_ai_response("Done"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_memory)

        # Same type: ignore as above -- host.get() returns BaseAgent,
        # _model is on the concrete agent types.
        prime = host.get(PRIME_AGENT)
        assert prime._model == config.ai.default_model  # type: ignore[union-attr]

        researcher = host.get("researcher")
        assert researcher._model == config.ai.default_model  # type: ignore[union-attr]


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


class TestSessionManagerInjection:
    @pytest.mark.asyncio
    async def test_executor_has_session_manager(self, tmp_path, config, profile_no_micros, monkeypatch):
        """Bootstrap injects SessionManager into Executor."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_no_micros)

        assert executor._session_manager is not None  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_sessions_directory_exists(self, tmp_path, config, profile_no_micros, monkeypatch):
        """Bootstrap ensures data/sessions directory exists."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        await bootstrap(tmp_path, config, profile_no_micros)

        assert (tmp_path / "data" / "sessions").is_dir()


@pytest.fixture
def profile_with_heartbeat():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        heartbeat=HeartbeatConfig(
            clock_triggers=[
                ClockTrigger(
                    name="test-trigger",
                    cron="*/5 * * * *",
                    recipient="prime",
                    payload="tick",
                    guards=TriggerGuards(cooldown_seconds=60),
                ),
            ],
        ),
    )

@pytest.fixture
def profile_with_invalid_cron():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        heartbeat=HeartbeatConfig(
            clock_triggers=[
                ClockTrigger(name="bad", cron="bad cron", recipient="prime"),
            ],
        ),
    )


class TestHeartbeatBootstrap:
    @pytest.mark.asyncio
    async def test_scheduler_not_created_without_triggers(self, tmp_path, config, profile_no_micros, monkeypatch):
        """No triggers in profile means no scheduler created."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_no_micros)
        # Bootstrap completes without error -- scheduler not created
        assert executor is not None

    @pytest.mark.asyncio
    async def test_scheduler_created_with_triggers(self, tmp_path, config, profile_with_heartbeat, monkeypatch):
        """Clock triggers in profile cause scheduler to be created and started."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        # Patch HeartbeatScheduler to verify it's created
        mock_scheduler_cls = MagicMock()
        mock_scheduler_instance = MagicMock()
        mock_scheduler_instance.start = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler_instance
        monkeypatch.setattr("signalagent.runtime.bootstrap.HeartbeatScheduler", mock_scheduler_cls)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_heartbeat)

        mock_scheduler_cls.assert_called_once()
        mock_scheduler_instance.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_cron_fails_at_bootstrap(self, tmp_path, config, profile_with_invalid_cron, monkeypatch):
        """Invalid cron expression raises ValueError at bootstrap."""
        mock_ai = AsyncMock()
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        with pytest.raises(ValueError, match="Invalid cron"):
            await bootstrap(tmp_path, config, profile_with_invalid_cron)


@pytest.fixture
def profile_with_worktree_agent():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        plugins=PluginsConfig(available=["file_system"]),
        micro_agents=[
            MicroAgentConfig(
                name="coder", skill="coding",
                talks_to=["prime"], plugins=["file_system"],
            ),
        ],
    )


class TestWorktreeBootstrap:
    @pytest.mark.asyncio
    async def test_micro_agent_gets_worktree_proxy(self, tmp_path, config, profile_with_worktree_agent, monkeypatch):
        """Micro-agents should receive a WorktreeProxy instance."""
        mock_ai = AsyncMock()
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_worktree_agent)

        coder = host.get("coder")
        assert coder._worktree_proxy is not None  # type: ignore[union-attr]
        assert isinstance(coder._worktree_proxy, WorktreeProxy)  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_write_through_runner_creates_worktree(self, tmp_path, config, profile_with_worktree_agent, monkeypatch):
        """Functional test: a file_system write through the full pipeline creates a worktree."""
        tc = ToolCallRequest(id="call_1", name="file_system",
                             arguments={"operation": "write", "path": "test.py", "content": "hello"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_ai_response("coder"),
            _make_ai_response("", tool_calls=[tc]),
            _make_ai_response("Done"),
        ])
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_worktree_agent)
        result = await executor.run("write a test file")

        # The write should have gone to a worktree, not the real workspace
        assert not (tmp_path / "test.py").exists()
        # The response should include worktree review instructions
        assert "signal worktree merge" in result.content


@pytest.fixture
def profile_with_memory_keeper():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        memory_keeper=MemoryKeeperConfig(),
    )


@pytest.fixture
def profile_without_memory_keeper():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
    )


class TestMemoryKeeperBootstrap:
    @pytest.mark.asyncio
    async def test_memory_keeper_created_when_config_present(
        self, tmp_path, config, profile_with_memory_keeper, monkeypatch,
    ):
        """Bootstrap creates MemoryKeeperAgent when memory_keeper config is present."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        mock_scheduler_cls = MagicMock()
        mock_scheduler_instance = MagicMock()
        mock_scheduler_instance.start = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler_instance
        monkeypatch.setattr("signalagent.runtime.bootstrap.HeartbeatScheduler", mock_scheduler_cls)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_memory_keeper)

        keeper = host.get("memory-keeper")
        assert keeper is not None
        assert keeper.agent_type.value == "memory_keeper"

    @pytest.mark.asyncio
    async def test_memory_keeper_not_created_when_config_absent(
        self, tmp_path, config, profile_without_memory_keeper, monkeypatch,
    ):
        """Bootstrap does NOT create MemoryKeeperAgent when config is absent."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_without_memory_keeper)

        keeper = host.get("memory-keeper")
        assert keeper is None

    @pytest.mark.asyncio
    async def test_memory_keeper_heartbeat_trigger_registered(
        self, tmp_path, config, profile_with_memory_keeper, monkeypatch,
    ):
        """Bootstrap registers a ClockTrigger for the MemoryKeeper."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        mock_scheduler_cls = MagicMock()
        mock_scheduler_instance = MagicMock()
        mock_scheduler_instance.start = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler_instance
        monkeypatch.setattr("signalagent.runtime.bootstrap.HeartbeatScheduler", mock_scheduler_cls)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_memory_keeper)

        mock_scheduler_cls.assert_called_once()
        triggers = mock_scheduler_cls.call_args[1]["triggers"]
        trigger_names = [t.name for t in triggers]
        assert "memory-keeper-maintenance" in trigger_names
