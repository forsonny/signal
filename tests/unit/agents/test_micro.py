"""Unit tests for MicroAgent -- mock runner only."""
import pytest
from unittest.mock import AsyncMock

from signalagent.agents.micro import MicroAgent
from signalagent.core.models import MicroAgentConfig, Message
from signalagent.core.types import AgentType, MessageType
from signalagent.runtime.runner import RunnerResult


def _make_config(name="code-review", skill="Code quality, security, style consistency"):
    return MicroAgentConfig(name=name, skill=skill)

def _make_runner_result(content="Review complete."):
    return RunnerResult(content=content, iterations=1, tool_calls_made=0)

def _make_task_message(content="Review this code"):
    return Message(id="msg_test0001", type=MessageType.TASK,
                   sender="prime", recipient="code-review", content=content)


class TestMicroAgentConstruction:
    def test_name_from_config(self):
        agent = MicroAgent(config=_make_config(name="git-agent"), runner=AsyncMock())
        assert agent.name == "git-agent"
        assert agent.agent_type == AgentType.MICRO

    def test_skill_property_returns_config_skill(self):
        agent = MicroAgent(config=_make_config(skill="Code quality"), runner=AsyncMock())
        assert agent.skill == "Code quality"

    def test_system_prompt_contains_name_and_skill(self):
        agent = MicroAgent(config=_make_config(name="code-review", skill="Code quality"), runner=AsyncMock())
        prompt = agent._system_prompt
        assert "code-review" in prompt
        assert "Code quality" in prompt
        assert "specialist micro-agent" in prompt


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
