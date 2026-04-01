"""Unit tests for token counting utilities."""
import pytest
from unittest.mock import patch, MagicMock

from signalagent.prompts.tokens import count_tokens, get_context_window


class TestCountTokens:
    def test_returns_token_count(self):
        """count_tokens delegates to litellm.token_counter."""
        with patch("signalagent.prompts.tokens.litellm") as mock_litellm:
            mock_litellm.token_counter.return_value = 42
            result = count_tokens("hello world", "anthropic/claude-sonnet-4-20250514")
            assert result == 42
            mock_litellm.token_counter.assert_called_once_with(
                model="anthropic/claude-sonnet-4-20250514", text="hello world",
            )

    def test_empty_string_returns_zero_or_low(self):
        """Empty string should return 0 or very low token count."""
        with patch("signalagent.prompts.tokens.litellm") as mock_litellm:
            mock_litellm.token_counter.return_value = 0
            result = count_tokens("", "test-model")
            assert result == 0


class TestGetContextWindow:
    def test_returns_max_input_tokens(self):
        """get_context_window returns the model's max_input_tokens."""
        with patch("signalagent.prompts.tokens.litellm") as mock_litellm:
            mock_litellm.get_model_info.return_value = {
                "max_input_tokens": 200000,
                "max_output_tokens": 4096,
            }
            result = get_context_window("anthropic/claude-sonnet-4-20250514")
            assert result == 200000
            mock_litellm.get_model_info.assert_called_once_with(
                "anthropic/claude-sonnet-4-20250514",
            )

    def test_raises_on_unknown_model(self):
        """Unknown model should propagate the LiteLLM error."""
        with patch("signalagent.prompts.tokens.litellm") as mock_litellm:
            mock_litellm.get_model_info.side_effect = Exception("Unknown model")
            with pytest.raises(Exception, match="Unknown model"):
                get_context_window("nonexistent/model")
