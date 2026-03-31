import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from signalagent.ai.layer import AILayer, AIResponse
from signalagent.core.config import AIConfig, SignalConfig
from signalagent.core.errors import AIError


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
        MagicMock(message=MagicMock(content=content))
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
