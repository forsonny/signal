"""Tests for LiteLLMEmbedding."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from signalagent.ai.embedding import LiteLLMEmbedding
from signalagent.core.protocols import EmbeddingProtocol


class TestLiteLLMEmbedding:
    async def test_returns_vectors(self):
        mock_response = MagicMock()
        item1 = MagicMock()
        item1.embedding = [0.1, 0.2, 0.3]
        item2 = MagicMock()
        item2.embedding = [0.4, 0.5, 0.6]
        mock_response.data = [item1, item2]

        with patch("signalagent.ai.embedding.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)
            embedder = LiteLLMEmbedding(model="openai/text-embedding-3-small")
            result = await embedder.embed(["hello", "world"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    async def test_passes_model_to_litellm(self):
        mock_response = MagicMock()
        item = MagicMock()
        item.embedding = [0.1]
        mock_response.data = [item]

        with patch("signalagent.ai.embedding.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)
            embedder = LiteLLMEmbedding(model="openai/text-embedding-3-small")
            await embedder.embed(["test"])

            mock_litellm.aembedding.assert_called_once_with(
                model="openai/text-embedding-3-small", input=["test"],
            )

    async def test_handles_dict_response(self):
        """LiteLLM may return dicts instead of objects depending on version."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2]}]

        with patch("signalagent.ai.embedding.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)
            embedder = LiteLLMEmbedding(model="test-model")
            result = await embedder.embed(["test"])

        assert result[0] == [0.1, 0.2]

    async def test_satisfies_embedding_protocol(self):
        embedder = LiteLLMEmbedding(model="test")
        assert isinstance(embedder, EmbeddingProtocol)
