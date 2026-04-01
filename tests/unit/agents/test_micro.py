"""Unit tests for MicroAgent -- mock AILayer only."""

import pytest
from unittest.mock import AsyncMock

from signalagent.agents.micro import MicroAgent
from signalagent.ai.layer import AIResponse
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.types import AgentType, MessageType


def _make_config(
    name: str = "code-review",
    skill: str = "Code quality, security, style consistency",
) -> MicroAgentConfig:
    return MicroAgentConfig(name=name, skill=skill)


def _make_ai_response(content: str = "Review complete.") -> AIResponse:
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
    )


def _make_task_message(content: str = "Review this code") -> Message:
    return Message(
        id="msg_test0001",
        type=MessageType.TASK,
        sender="prime",
        recipient="code-review",
        content=content,
    )


class TestMicroAgentConstruction:
    def test_name_from_config(self):
        config = _make_config(name="git-agent")
        agent = MicroAgent(config=config, ai=AsyncMock())
        assert agent.name == "git-agent"
        assert agent.agent_type == AgentType.MICRO

    def test_skill_property_returns_config_skill(self):
        config = _make_config(name="code-review", skill="Code quality")
        agent = MicroAgent(config=config, ai=AsyncMock())
        assert agent.skill == "Code quality"

    def test_system_prompt_contains_name_and_skill(self):
        config = _make_config(name="code-review", skill="Code quality")
        agent = MicroAgent(config=config, ai=AsyncMock())
        prompt = agent._system_prompt
        assert "code-review" in prompt
        assert "Code quality" in prompt
        assert "specialist micro-agent" in prompt


class TestMicroAgentExecution:
    @pytest.mark.asyncio
    async def test_calls_ai_with_system_prompt(self):
        config = _make_config()
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response())
        agent = MicroAgent(config=config, ai=mock_ai)

        msg = _make_task_message()
        await agent._handle(msg)

        mock_ai.complete.assert_called_once()
        call_messages = mock_ai.complete.call_args.kwargs["messages"]
        assert call_messages[0]["role"] == "system"
        assert "code-review" in call_messages[0]["content"]
        assert call_messages[1]["role"] == "user"
        assert call_messages[1]["content"] == "Review this code"

    @pytest.mark.asyncio
    async def test_returns_result_message(self):
        config = _make_config()
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("All good."))
        agent = MicroAgent(config=config, ai=mock_ai)

        msg = _make_task_message()
        result = await agent._handle(msg)

        assert result is not None
        assert result.type == MessageType.RESULT
        assert result.content == "All good."
        assert result.sender == "code-review"
        assert result.recipient == "prime"
        assert result.parent_id == "msg_test0001"

    @pytest.mark.asyncio
    async def test_ai_error_propagates(self):
        config = _make_config()
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=Exception("LLM down"))
        agent = MicroAgent(config=config, ai=mock_ai)

        msg = _make_task_message()
        with pytest.raises(Exception, match="LLM down"):
            await agent._handle(msg)
