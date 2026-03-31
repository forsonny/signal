import pytest
from unittest.mock import AsyncMock

from signalagent.ai.layer import AIResponse
from signalagent.core.models import PrimeConfig, Profile
from signalagent.runtime.executor import Executor, ExecutorResult


def _make_profile(identity: str = "You are a test assistant.") -> Profile:
    return Profile(
        name="test",
        prime=PrimeConfig(identity=identity),
    )


def _make_ai_response(content: str = "Test response") -> AIResponse:
    return AIResponse(
        content=content,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=20,
    )


class TestExecutorResult:
    def test_success(self):
        result = ExecutorResult(content="Hello!")
        assert result.content == "Hello!"
        assert result.error is None

    def test_error(self):
        result = ExecutorResult(content="", error="something broke")
        assert result.error == "something broke"


class TestExecutor:
    @pytest.mark.asyncio
    async def test_run_returns_content(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("Hello!"))

        executor = Executor(ai=mock_ai, profile=_make_profile())
        result = await executor.run("hi")

        assert result.content == "Hello!"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_run_sends_system_prompt(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response())

        executor = Executor(
            ai=mock_ai,
            profile=_make_profile("You are a pirate."),
        )
        await executor.run("hello")

        call_args = mock_ai.complete.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a pirate."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_run_error_boundary(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(side_effect=Exception("LLM exploded"))

        executor = Executor(ai=mock_ai, profile=_make_profile())
        result = await executor.run("hello")

        assert result.content == ""
        assert result.error is not None
        assert "LLM exploded" in result.error

    @pytest.mark.asyncio
    async def test_run_tracks_token_usage(self):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response())

        executor = Executor(ai=mock_ai, profile=_make_profile())
        result = await executor.run("hello")

        assert result.input_tokens == 10
        assert result.output_tokens == 20
