import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from signalagent.ai.layer import AILayer, AIResponse
from signalagent.core.config import AIConfig, SignalConfig
from signalagent.core.errors import AIError
from signalagent.core.models import ToolCallRequest


class TestAIResponse:
    def test_fields(self):
        resp = AIResponse(
            content="Hello!",
            model="anthropic/claude-sonnet-4-20250514",
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            cost=0.001,
        )
        assert resp.content == "Hello!"
        assert resp.input_tokens == 10

    def test_defaults(self):
        resp = AIResponse(
            content="Hi", model="test", provider="test"
        )
        assert resp.input_tokens == 0
        assert resp.cost == 0.0


def _mock_litellm_response(content="Hello! How can I help?"):
    response = MagicMock()
    response.choices = [
        MagicMock(message=MagicMock(content=content, tool_calls=None))
    ]
    response.usage = MagicMock(prompt_tokens=15, completion_tokens=25)
    response.model = "anthropic/claude-sonnet-4-20250514"
    return response


class TestAILayer:
    @pytest.fixture
    def config(self):
        return SignalConfig(profile_name="blank")

    @pytest.fixture
    def layer(self, config):
        return AILayer(config)

    @pytest.mark.asyncio
    async def test_complete_returns_response(self, layer):
        mock_resp = _mock_litellm_response("Test response")
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
            result = await layer.complete(
                messages=[{"role": "user", "content": "hello"}]
            )
        assert isinstance(result, AIResponse)
        assert result.content == "Test response"
        assert result.input_tokens == 15
        assert result.output_tokens == 25
        assert result.provider == "anthropic"

    @pytest.mark.asyncio
    async def test_complete_uses_default_model(self, layer):
        mock_resp = _mock_litellm_response()
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp) as mock_call:
            await layer.complete(
                messages=[{"role": "user", "content": "hello"}]
            )
        call_kwargs = mock_call.call_args
        assert call_kwargs.kwargs["model"] == "anthropic/claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_complete_uses_override_model(self, layer):
        mock_resp = _mock_litellm_response()
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp) as mock_call:
            await layer.complete(
                messages=[{"role": "user", "content": "hello"}],
                model="openai/gpt-4o",
            )
        call_kwargs = mock_call.call_args
        assert call_kwargs.kwargs["model"] == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_complete_wraps_errors(self, layer):
        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("API down")):
            with pytest.raises(AIError, match="LLM call failed"):
                await layer.complete(
                    messages=[{"role": "user", "content": "hello"}]
                )


class TestAIResponseToolCalls:
    def test_tool_calls_defaults_to_empty_list(self):
        response = AIResponse(
            content="hello", model="test", provider="test",
            input_tokens=0, output_tokens=0,
        )
        assert response.tool_calls == []

    def test_tool_calls_populated(self):
        tc = ToolCallRequest(id="call_1", name="file_system", arguments={"op": "read"})
        response = AIResponse(
            content="", model="test", provider="test",
            tool_calls=[tc],
        )
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "file_system"


class TestCompleteWithTools:
    @pytest.fixture
    def config(self):
        return SignalConfig(profile_name="test")

    @pytest.mark.asyncio
    async def test_passes_tools_to_litellm(self, monkeypatch, config):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=None))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_response.model = "test-model"
        mock_acompletion = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("signalagent.ai.layer.litellm.acompletion", mock_acompletion)

        layer = AILayer(config)
        tools = [{"type": "function", "function": {"name": "test", "description": "test", "parameters": {}}}]
        await layer.complete(messages=[{"role": "user", "content": "hi"}], tools=tools)
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["tools"] == tools

    @pytest.mark.asyncio
    async def test_no_tools_omits_tools_kwarg(self, monkeypatch, config):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=None))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_response.model = "test-model"
        mock_acompletion = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("signalagent.ai.layer.litellm.acompletion", mock_acompletion)

        layer = AILayer(config)
        await layer.complete(messages=[{"role": "user", "content": "hi"}])
        call_kwargs = mock_acompletion.call_args.kwargs
        assert "tools" not in call_kwargs

    @pytest.mark.asyncio
    async def test_parses_tool_calls_from_response(self, monkeypatch, config):
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_abc"
        mock_tool_call.function.name = "file_system"
        mock_tool_call.function.arguments = '{"operation": "read", "path": "test.txt"}'

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=None, tool_calls=[mock_tool_call]))
        ]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_response.model = "test-model"
        mock_acompletion = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("signalagent.ai.layer.litellm.acompletion", mock_acompletion)

        layer = AILayer(config)
        result = await layer.complete(
            messages=[{"role": "user", "content": "read file"}],
            tools=[{"type": "function", "function": {"name": "file_system", "description": "fs", "parameters": {}}}],
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_abc"
        assert result.tool_calls[0].name == "file_system"
        assert result.tool_calls[0].arguments == {"operation": "read", "path": "test.txt"}
