"""Unit tests for MicroAgent -- mock runner only."""
import pytest
from unittest.mock import AsyncMock, patch

from signalagent.agents.micro import MicroAgent
from signalagent.core.models import MicroAgentConfig, Memory, Message
from signalagent.core.types import AgentType, MemoryType, MessageType
from signalagent.runtime.runner import RunnerResult

from datetime import datetime, timezone


def _make_config(name="code-review", skill="Code quality, security, style consistency"):
    return MicroAgentConfig(name=name, skill=skill)

def _make_runner_result(content="Review complete."):
    return RunnerResult(content=content, iterations=1, tool_calls_made=0)

def _make_task_message(content="Review this code"):
    return Message(id="msg_test0001", type=MessageType.TASK,
                   sender="prime", recipient="code-review", content=content)

def _make_memory(content="Relevant context", tags=None):
    now = datetime.now(timezone.utc)
    return Memory(
        id="mem_test0001", agent="code-review", type=MemoryType.LEARNING,
        tags=tags or ["code"], content=content, confidence=0.8, version=1,
        created=now, updated=now, accessed=now, access_count=0,
    )


def _stub_count_tokens(text: str, model: str) -> int:
    """Approximate: 1 token per 4 characters."""
    return len(text) // 4


class TestMicroAgentConstruction:
    def test_name_from_config(self):
        agent = MicroAgent(config=_make_config(name="git-agent"), runner=AsyncMock())
        assert agent.name == "git-agent"
        assert agent.agent_type == AgentType.MICRO

    def test_skill_property_returns_config_skill(self):
        agent = MicroAgent(config=_make_config(skill="Code quality"), runner=AsyncMock())
        assert agent.skill == "Code quality"

    def test_identity_contains_name_and_skill(self):
        agent = MicroAgent(config=_make_config(name="code-review", skill="Code quality"), runner=AsyncMock())
        identity = agent._build_identity()
        assert "code-review" in identity
        assert "Code quality" in identity
        assert "specialist micro-agent" in identity


class TestMicroAgentExecution:
    @pytest.mark.asyncio
    async def test_delegates_to_runner(self):
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        await agent._handle(_make_task_message())
        mock_runner.run.assert_called_once()
        call_kwargs = mock_runner.run.call_args.kwargs
        assert "code-review" in call_kwargs["system_prompt"]
        assert call_kwargs["user_content"] == "Review this code"

    @pytest.mark.asyncio
    async def test_returns_result_message(self):
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result("All good."))
        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        result = await agent._handle(_make_task_message())
        assert result is not None
        assert result.type == MessageType.RESULT
        assert result.content == "All good."
        assert result.sender == "code-review"
        assert result.recipient == "prime"
        assert result.parent_id == "msg_test0001"

    @pytest.mark.asyncio
    async def test_runner_error_propagates(self):
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=Exception("LLM down"))
        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        with pytest.raises(Exception, match="LLM down"):
            await agent._handle(_make_task_message())


class TestMicroAgentMemoryIntegration:
    @pytest.mark.asyncio
    async def test_retrieves_memories_and_enriches_prompt(self):
        """When memory_reader is provided, system prompt includes memories."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(return_value=[_make_memory()])

        agent = MicroAgent(
            config=_make_config(), runner=mock_runner,
            memory_reader=mock_reader, model="test-model",
        )
        with patch("signalagent.prompts.builder.count_tokens", side_effect=_stub_count_tokens), \
             patch("signalagent.prompts.builder.get_context_window", return_value=10000):
            await agent._handle(_make_task_message())

        mock_reader.search.assert_called_once()
        call_kwargs = mock_reader.search.call_args.kwargs
        assert call_kwargs["agent"] == "code-review"

        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "Relevant context" in system_prompt
        assert "## Context" in system_prompt

    @pytest.mark.asyncio
    async def test_no_memory_reader_uses_identity_only(self):
        """Without memory_reader, prompt is the static identity string."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())

        agent = MicroAgent(config=_make_config(), runner=mock_runner)
        await agent._handle(_make_task_message())

        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "code-review" in system_prompt
        assert "## Context" not in system_prompt

    @pytest.mark.asyncio
    async def test_memory_search_failure_proceeds_without_context(self):
        """If memory search fails, agent proceeds with identity-only prompt."""
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=_make_runner_result())
        mock_reader = AsyncMock()
        mock_reader.search = AsyncMock(side_effect=Exception("DB error"))

        agent = MicroAgent(
            config=_make_config(), runner=mock_runner,
            memory_reader=mock_reader, model="test-model",
        )
        result = await agent._handle(_make_task_message())

        assert result is not None
        assert result.content == "Review complete."
        system_prompt = mock_runner.run.call_args.kwargs["system_prompt"]
        assert "## Context" not in system_prompt
