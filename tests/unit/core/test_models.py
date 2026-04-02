from datetime import datetime, timezone
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
    PluginsConfig,
    HeartbeatConfig,
    HooksConfig,
    ForkConfig,
    Memory,
    Message,
    ToolCallRequest,
    ToolResult,
    ToolConfig,
    Turn,
    SessionSummary,
)
from signalagent.core.types import MemoryType, MessageType
from signalagent.heartbeat.models import ClockTrigger, FileEventTrigger, TriggerGuards


class TestPrimeConfig:
    def test_defaults(self):
        config = PrimeConfig()
        assert "helpful" in config.identity.lower() or config.identity != ""

    def test_custom_identity(self):
        config = PrimeConfig(identity="You are a code review expert.")
        assert config.identity == "You are a code review expert."


class TestMicroAgentConfig:
    def test_minimal(self):
        agent = MicroAgentConfig(name="code-review", skill="Code quality")
        assert agent.name == "code-review"
        assert agent.skill == "Code quality"
        assert agent.talks_to == []
        assert agent.plugins == []
        assert agent.can_spawn_subs is False

    def test_full(self):
        agent = MicroAgentConfig(
            name="code-review",
            skill="Code quality, security",
            talks_to=["git", "testing"],
            plugins=["file_system"],
            can_spawn_subs=True,
        )
        assert agent.talks_to == ["git", "testing"]
        assert agent.can_spawn_subs is True


class TestProfile:
    def test_blank_profile(self):
        profile = Profile(name="blank", description="Empty instance")
        assert profile.name == "blank"
        assert profile.micro_agents == []
        assert profile.prime.identity != ""

    def test_devtools_profile(self):
        profile = Profile(
            name="devtools",
            description="Development assistant",
            prime=PrimeConfig(identity="You are a senior development partner."),
            micro_agents=[
                MicroAgentConfig(
                    name="code-review",
                    skill="Code quality",
                    talks_to=["git"],
                    plugins=["file_system"],
                ),
                MicroAgentConfig(
                    name="git",
                    skill="Version control",
                    talks_to=["code-review"],
                    plugins=["git"],
                ),
            ],
            plugins=PluginsConfig(available=["file_system", "git"]),
        )
        assert len(profile.micro_agents) == 2
        assert profile.micro_agents[0].name == "code-review"

    def test_from_yaml_string(self):
        yaml_str = """
name: test
description: Test profile
prime:
  identity: "You are a test agent."
micro_agents:
  - name: reviewer
    skill: "Code review"
    talks_to: [git]
    plugins: [file_system]
    can_spawn_subs: true
plugins:
  available: [file_system, git]
"""
        data = yaml.safe_load(yaml_str)
        profile = Profile(**data)
        assert profile.name == "test"
        assert len(profile.micro_agents) == 1
        assert profile.micro_agents[0].can_spawn_subs is True


class TestMemory:
    def test_construction(self):
        now = datetime.now(timezone.utc)
        mem = Memory(
            id="mem_abc12345",
            agent="prime",
            type=MemoryType.IDENTITY,
            tags=["python", "preferences"],
            content="User prefers explicit error handling.",
            confidence=0.8,
            version=1,
            created=now,
            updated=now,
            accessed=now,
        )
        assert mem.id == "mem_abc12345"
        assert mem.type == MemoryType.IDENTITY
        assert mem.confidence == 0.8
        assert mem.content == "User prefers explicit error handling."

    def test_defaults(self):
        now = datetime.now(timezone.utc)
        mem = Memory(
            id="mem_abc12345",
            agent="prime",
            type=MemoryType.IDENTITY,
            tags=[],
            content="test",
            created=now,
            updated=now,
            accessed=now,
        )
        assert mem.confidence == 0.5
        assert mem.version == 1
        assert mem.access_count == 0
        assert mem.changelog == []
        assert mem.supersedes == []
        assert mem.superseded_by is None
        assert mem.consolidated_from == []

    def test_confidence_rejects_above_one(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            Memory(
                id="mem_abc12345",
                agent="prime",
                type=MemoryType.IDENTITY,
                tags=[],
                content="test",
                confidence=1.5,
                created=now,
                updated=now,
                accessed=now,
            )

    def test_confidence_rejects_below_zero(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            Memory(
                id="mem_abc12345",
                agent="prime",
                type=MemoryType.IDENTITY,
                tags=[],
                content="test",
                confidence=-0.1,
                created=now,
                updated=now,
                accessed=now,
            )

    def test_extra_fields_rejected(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            Memory(
                id="mem_abc12345",
                agent="prime",
                type=MemoryType.IDENTITY,
                tags=[],
                content="test",
                created=now,
                updated=now,
                accessed=now,
                bogus="field",
            )


class TestMessage:
    def test_construction_with_required_fields(self):
        msg = Message(
            type=MessageType.TASK,
            sender="user",
            recipient="prime",
            content="hello",
        )
        assert msg.type == MessageType.TASK
        assert msg.sender == "user"
        assert msg.recipient == "prime"
        assert msg.content == "hello"

    def test_defaults(self):
        msg = Message(
            type=MessageType.TASK,
            sender="user",
            recipient="prime",
            content="hello",
        )
        assert msg.id == ""
        assert msg.created is None
        assert msg.parent_id is None
        assert msg.metadata == {}

    def test_metadata_accepts_any_types(self):
        msg = Message(
            type=MessageType.TASK,
            sender="user",
            recipient="prime",
            content="hello",
            metadata={"confidence": 0.85, "agents": ["code-review", "git"]},
        )
        assert msg.metadata["confidence"] == 0.85
        assert msg.metadata["agents"] == ["code-review", "git"]

    def test_parent_id_threading(self):
        msg = Message(
            type=MessageType.RESULT,
            sender="prime",
            recipient="user",
            content="done",
            parent_id="msg_abc12345",
        )
        assert msg.parent_id == "msg_abc12345"

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            Message(
                type=MessageType.TASK,
                sender="user",
                recipient="prime",
                content="hello",
                bogus="field",
            )


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


class TestHooksConfig:
    def test_defaults(self):
        hc = HooksConfig()
        assert hc.active == []

    def test_with_hooks(self):
        hc = HooksConfig(active=["log_tool_calls", "path_guard"])
        assert hc.active == ["log_tool_calls", "path_guard"]

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            HooksConfig(active=[], extra="bad")


class TestProfileHooksField:
    def test_profile_has_hooks_default(self):
        p = Profile(name="test")
        assert p.hooks.active == []

    def test_profile_with_hooks(self):
        p = Profile(name="test", hooks=HooksConfig(active=["log_tool_calls"]))
        assert p.hooks.active == ["log_tool_calls"]


class TestMicroAgentConfigMaxIterations:
    def test_default_max_iterations(self):
        config = MicroAgentConfig(name="test", skill="testing")
        assert config.max_iterations == 10

    def test_custom_max_iterations(self):
        config = MicroAgentConfig(name="test", skill="testing", max_iterations=5)
        assert config.max_iterations == 5


class TestTurnModel:
    def test_turn_creation(self):
        now = datetime.now(timezone.utc)
        turn = Turn(role="user", content="hello", timestamp=now)
        assert turn.role == "user"
        assert turn.content == "hello"
        assert turn.timestamp == now

    def test_turn_forbids_extra_fields(self):
        with pytest.raises(Exception):
            Turn(role="user", content="hi", timestamp=datetime.now(timezone.utc), extra="bad")


class TestSessionSummaryModel:
    def test_session_summary_creation(self):
        now = datetime.now(timezone.utc)
        summary = SessionSummary(id="ses_abc12345", created=now, preview="hello world", turn_count=5)
        assert summary.id == "ses_abc12345"
        assert summary.turn_count == 5


class TestHeartbeatSender:
    def test_heartbeat_sender_value(self):
        from signalagent.core.types import HEARTBEAT_SENDER
        assert HEARTBEAT_SENDER == "heartbeat"


class TestHeartbeatConfig:
    def test_defaults_empty(self):
        hc = HeartbeatConfig()
        assert hc.clock_triggers == []
        assert hc.event_triggers == []

    def test_with_clock_trigger(self):
        hc = HeartbeatConfig(
            clock_triggers=[
                ClockTrigger(name="test", cron="* * * * *", recipient="prime"),
            ],
        )
        assert len(hc.clock_triggers) == 1
        assert hc.clock_triggers[0].name == "test"

    def test_with_event_trigger(self):
        hc = HeartbeatConfig(
            event_triggers=[
                FileEventTrigger(name="watch", recipient="prime"),
            ],
        )
        assert len(hc.event_triggers) == 1

    def test_rejects_condition_triggers(self):
        """condition_triggers field removed -- extra fields forbidden."""
        with pytest.raises(ValidationError):
            HeartbeatConfig(condition_triggers=[])

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            HeartbeatConfig(bogus="x")


class TestMessageHistory:
    def test_message_history_defaults_to_empty_list(self):
        msg = Message(type=MessageType.TASK, sender="user", recipient="prime", content="hi")
        assert msg.history == []

    def test_message_with_history(self):
        history = [{"role": "user", "content": "prior"}, {"role": "assistant", "content": "reply"}]
        msg = Message(type=MessageType.TASK, sender="user", recipient="prime", content="new", history=history)
        assert len(msg.history) == 2
        assert msg.history[0]["role"] == "user"


class TestForkConfig:
    def test_default_values(self) -> None:
        config = ForkConfig()
        assert config.max_concurrent_branches == 2

    def test_custom_value(self) -> None:
        config = ForkConfig(max_concurrent_branches=4)
        assert config.max_concurrent_branches == 4

    def test_extra_forbidden(self) -> None:
        with pytest.raises(Exception):
            ForkConfig(max_concurrent_branches=2, surprise="bad")

    def test_minimum_one(self) -> None:
        with pytest.raises(Exception):
            ForkConfig(max_concurrent_branches=0)


class TestProfileWithFork:
    def test_profile_has_fork_config(self) -> None:
        p = Profile(name="test")
        assert isinstance(p.fork, ForkConfig)
        assert p.fork.max_concurrent_branches == 2


from signalagent.core.models import MemoryConfig, MemoryKeeperConfig


class TestMemoryConfig:
    def test_defaults(self):
        cfg = MemoryConfig()
        assert cfg.decay_half_life_days == 30

    def test_custom_half_life(self):
        cfg = MemoryConfig(decay_half_life_days=60)
        assert cfg.decay_half_life_days == 60

    def test_rejects_zero_half_life(self):
        import pytest
        with pytest.raises(Exception):
            MemoryConfig(decay_half_life_days=0)

    def test_rejects_extra_fields(self):
        import pytest
        with pytest.raises(Exception):
            MemoryConfig(unknown="x")


class TestMemoryKeeperConfig:
    def test_defaults(self):
        cfg = MemoryKeeperConfig()
        assert cfg.schedule == "0 3 * * 0"
        assert cfg.staleness_threshold_days == 90
        assert cfg.min_confidence == 0.1
        assert cfg.max_candidates_per_run == 20

    def test_custom_values(self):
        cfg = MemoryKeeperConfig(
            schedule="0 4 * * 1",
            staleness_threshold_days=60,
            min_confidence=0.2,
            max_candidates_per_run=10,
        )
        assert cfg.schedule == "0 4 * * 1"
        assert cfg.staleness_threshold_days == 60

    def test_rejects_extra_fields(self):
        import pytest
        with pytest.raises(Exception):
            MemoryKeeperConfig(unknown="x")


class TestProfileMemoryConfig:
    def test_profile_has_memory_defaults(self):
        from signalagent.core.models import Profile
        p = Profile(name="test")
        assert p.memory.decay_half_life_days == 30

    def test_profile_memory_keeper_absent_by_default(self):
        from signalagent.core.models import Profile
        p = Profile(name="test")
        assert p.memory_keeper is None

    def test_profile_memory_keeper_present(self):
        from signalagent.core.models import Profile
        p = Profile(name="test", memory_keeper=MemoryKeeperConfig())
        assert p.memory_keeper is not None
        assert p.memory_keeper.schedule == "0 3 * * 0"
