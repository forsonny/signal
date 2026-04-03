"""Embedding layer -- wraps LiteLLM's embedding API."""

from __future__ import annotations

import litellm


class LiteLLMEmbedding:
    """Wraps litellm.aembedding() for vector embedding generation.

    Handles both attribute-style (item.embedding) and dict-style
    (item["embedding"]) responses, as LiteLLM's return type varies
    between versions.
    """

    def __init__(self, model: str) -> None:
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per input text."""
        response = await litellm.aembedding(model=self._model, input=texts)
        vectors: list[list[float]] = []
        for item in response.data:
            if isinstance(item, dict):
                vectors.append(item["embedding"])
            else:
                vectors.append(item.embedding)
        return vectors
