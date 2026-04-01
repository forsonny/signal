"""Unit tests for SpawnSubAgentTool -- mock runner factory."""
import pytest
from unittest.mock import AsyncMock
from signalagent.tools.builtins.spawn_sub_agent import SpawnSubAgentTool


@pytest.fixture
def mock_run_sub():
    return AsyncMock(return_value="Sub-agent completed the analysis.")

@pytest.fixture
def tool(mock_run_sub):
    return SpawnSubAgentTool(run_sub=mock_run_sub, parent_name="researcher")


class TestSpawnSubAgentToolProperties:
    def test_name(self, tool):
        assert tool.name == "spawn_sub_agent"
    def test_description_is_nonempty(self, tool):
        assert len(tool.description) > 0
    def test_parameters_schema(self, tool):
        params = tool.parameters
        assert params["type"] == "object"
        assert "task" in params["properties"]
        assert "skill" in params["properties"]
        assert set(params["required"]) == {"task", "skill"}


class TestSpawnSubAgentExecution:
    @pytest.mark.asyncio
    async def test_calls_run_sub_with_system_prompt_and_task(self, tool, mock_run_sub):
        await tool.execute(task="Analyze the logs", skill="Log analysis")
        mock_run_sub.assert_called_once()
        system_prompt, task = mock_run_sub.call_args[0]
        assert "sub_researcher_1" in system_prompt
        assert "Log analysis" in system_prompt
        assert task == "Analyze the logs"

    @pytest.mark.asyncio
    async def test_returns_tool_result_with_output(self, tool):
        result = await tool.execute(task="Do something", skill="General")
        assert result.output == "Sub-agent completed the analysis."
        assert result.error is None

    @pytest.mark.asyncio
    async def test_auto_generates_sequential_names(self, tool, mock_run_sub):
        await tool.execute(task="Task 1", skill="Skill A")
        await tool.execute(task="Task 2", skill="Skill B")
        first_prompt = mock_run_sub.call_args_list[0][0][0]
        second_prompt = mock_run_sub.call_args_list[1][0][0]
        assert "sub_researcher_1" in first_prompt
        assert "sub_researcher_2" in second_prompt

    @pytest.mark.asyncio
    async def test_system_prompt_contains_skill(self, tool, mock_run_sub):
        await tool.execute(task="Review code", skill="Code quality")
        system_prompt = mock_run_sub.call_args[0][0]
        assert "Code quality" in system_prompt
        assert "ephemeral sub-agent" in system_prompt

    @pytest.mark.asyncio
    async def test_run_sub_error_propagates(self, mock_run_sub):
        mock_run_sub.side_effect = Exception("Runner failed")
        tool = SpawnSubAgentTool(run_sub=mock_run_sub, parent_name="test")
        with pytest.raises(Exception, match="Runner failed"):
            await tool.execute(task="Fail", skill="Testing")
