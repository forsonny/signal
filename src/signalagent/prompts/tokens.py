"""Token counting utilities -- thin wrapper around LiteLLM.

Isolates LiteLLM's token API so callers don't depend on it directly.
If LiteLLM's interface changes, only this file needs updating.
"""

from __future__ import annotations

import litellm


def count_tokens(text: str, model: str) -> int:
    """Count tokens for *text* using the model's tokenizer.

    Args:
        text: The string to tokenize.
        model: LiteLLM model identifier (e.g. ``"gpt-4"``).

    Returns:
        Number of tokens in *text*.
    """
    return litellm.token_counter(model=model, text=text)


def get_context_window(model: str) -> int:
    """Get the model's maximum input token limit.

    Uses ``max_input_tokens`` (the input context window), **not**
    ``get_max_tokens()`` which returns max output tokens.

    Args:
        model: LiteLLM model identifier.

    Returns:
        Maximum number of input tokens the model accepts.

    Raises:
        ValueError: If the model has no known input context window.
    """
    info = litellm.get_model_info(model)
    value = info["max_input_tokens"]
    if value is None:
        raise ValueError(
            f"Model '{model}' does not have a known input context window."
        )
    return value
