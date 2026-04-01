"""Unit tests for AgenticRunner -- mock AI + mock tool executor."""
import pytest
from unittest.mock import AsyncMock
from signalagent.ai.layer import AIResponse
from signalagent.core.models import ToolCallRequest, ToolResult
from signalagent.runtime.runner import AgenticRunner, RunnerResult


def _make_text_response(content: str) -> AIResponse:
    return AIResponse(content=content, model="test", provider="test",
                      input_tokens=10, output_tokens=20, tool_calls=[])

def _make_tool_response(tool_calls: list[ToolCallRequest], content: str = "") -> AIResponse:
    return AIResponse(content=content, model="test", provider="test",
                      input_tokens=10, output_tokens=20, tool_calls=tool_calls)


class TestRunnerNoTools:
    @pytest.mark.asyncio
    async def test_single_pass_no_tools(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_text_response("hello"))
        mock_executor = AsyncMock()
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[], max_iterations=10)
        result = await runner.run(system_prompt="You are helpful.", user_content="hi")
        assert result.content == "hello"
        assert result.iterations == 1
        assert result.tool_calls_made == 0
        assert result.truncated is False
        assert mock_ai.complete.call_args.kwargs.get("tools") is None


class TestRunnerWithTools:
    @pytest.mark.asyncio
    async def test_single_tool_call_then_final(self):
        tc = ToolCallRequest(id="call_1", name="file_system",
                             arguments={"operation": "read", "path": "test.txt"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc]),
            _make_text_response("File contains: hello"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="hello"))
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[{"type": "function", "function": {"name": "file_system"}}],
                               max_iterations=10)
        result = await runner.run(system_prompt="sys", user_content="read test.txt")
        assert result.content == "File contains: hello"
        assert result.iterations == 2
        assert result.tool_calls_made == 1
        mock_executor.assert_called_once_with("file_system", {"operation": "read", "path": "test.txt"})

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_response(self):
        tc1 = ToolCallRequest(id="call_1", name="tool_a", arguments={"x": 1})
        tc2 = ToolCallRequest(id="call_2", name="tool_b", arguments={"y": 2})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc1, tc2]),
            _make_text_response("done"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="ok"))
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[{"type": "function", "function": {"name": "tool_a"}},
                                             {"type": "function", "function": {"name": "tool_b"}}],
                               max_iterations=10)
        result = await runner.run(system_prompt="sys", user_content="go")
        assert result.tool_calls_made == 2
        assert result.iterations == 2
        assert mock_executor.call_count == 2

    @pytest.mark.asyncio
    async def test_multi_iteration_tool_loop(self):
        tc1 = ToolCallRequest(id="call_1", name="t", arguments={})
        tc2 = ToolCallRequest(id="call_2", name="t", arguments={})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc1]),
            _make_tool_response([tc2]),
            _make_text_response("done"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="ok"))
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[{"type": "function", "function": {"name": "t"}}],
                               max_iterations=10)
        result = await runner.run(system_prompt="sys", user_content="go")
        assert result.iterations == 3
        assert result.tool_calls_made == 2


class TestRunnerIterationLimit:
    @pytest.mark.asyncio
    async def test_truncated_at_max_iterations(self):
        tc = ToolCallRequest(id="call_1", name="t", arguments={})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_tool_response([tc], content="partial"))
        mock_executor = AsyncMock(return_value=ToolResult(output="ok"))
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[{"type": "function", "function": {"name": "t"}}],
                               max_iterations=3)
        result = await runner.run(system_prompt="sys", user_content="go")
        assert result.truncated is True
        assert result.iterations == 3
        assert result.content == "partial"


class TestRunnerErrorHandling:
    @pytest.mark.asyncio
    async def test_tool_error_fed_back_to_llm(self):
        tc = ToolCallRequest(id="call_1", name="bad_tool", arguments={})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc]),
            _make_text_response("I see the error"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="", error="tool broke"))
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[{"type": "function", "function": {"name": "bad_tool"}}],
                               max_iterations=10)
        result = await runner.run(system_prompt="sys", user_content="go")
        assert result.content == "I see the error"
        second_call_messages = mock_ai.complete.call_args_list[1].kwargs["messages"]
        tool_msg = [m for m in second_call_messages if m.get("role") == "tool"][0]
        assert "Error: tool broke" in tool_msg["content"]

    @pytest.mark.asyncio
    async def test_executor_exception_caught_and_fed_back(self):
        tc = ToolCallRequest(id="call_1", name="crash", arguments={})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc]),
            _make_text_response("recovered"),
        ])
        mock_executor = AsyncMock(side_effect=RuntimeError("executor crashed"))
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[{"type": "function", "function": {"name": "crash"}}],
                               max_iterations=10)
        result = await runner.run(system_prompt="sys", user_content="go")
        assert result.content == "recovered"
        second_call_messages = mock_ai.complete.call_args_list[1].kwargs["messages"]
        tool_msg = [m for m in second_call_messages if m.get("role") == "tool"][0]
        assert "Error:" in tool_msg["content"]


class TestRunnerMessageFormat:
    @pytest.mark.asyncio
    async def test_assistant_message_includes_tool_calls(self):
        tc = ToolCallRequest(id="call_1", name="echo", arguments={"text": "hi"})
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=[
            _make_tool_response([tc]),
            _make_text_response("done"),
        ])
        mock_executor = AsyncMock(return_value=ToolResult(output="hi"))
        runner = AgenticRunner(ai=mock_ai, tool_executor=mock_executor,
                               tool_schemas=[{"type": "function", "function": {"name": "echo"}}],
                               max_iterations=10)
        await runner.run(system_prompt="sys", user_content="go")
        second_call_messages = mock_ai.complete.call_args_list[1].kwargs["messages"]
        assistant_msgs = [m for m in second_call_messages if m.get("role") == "assistant"]
        assert len(assistant_msgs) == 1
        assert "tool_calls" in assistant_msgs[0]
        tc_out = assistant_msgs[0]["tool_calls"][0]
        assert tc_out["id"] == "call_1"
        assert tc_out["type"] == "function"
        assert tc_out["function"]["name"] == "echo"
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_1"
        assert tool_msgs[0]["content"] == "hi"
