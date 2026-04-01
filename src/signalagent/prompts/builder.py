"""Prompt builder -- pure function for token-budgeted system prompt assembly.

Takes an identity string and pre-retrieved memories, assembles them into
a system prompt that fits within the model's context window. No I/O,
no engine dependency, no state.
"""

from __future__ import annotations

from signalagent.core.models import Memory
from signalagent.prompts.tokens import count_tokens, get_context_window

DEFAULT_MEMORY_LIMIT = 20


def _format_memory(memory: Memory) -> str:
    """Format a single memory as a prompt block."""
    if memory.tags:
        heading = f"### {memory.type.value}: {memory.tags[0]}"
    else:
        heading = f"### {memory.type.value}"
    return f"{heading}\n{memory.content}"


def build_system_prompt(
    identity: str,
    memories: list[Memory],
    model: str,
    response_reserve: int = 500,
) -> str:
    """Assemble a token-budgeted system prompt from identity + memories.

    Args:
        identity: The agent's static identity string (name, skill, instructions).
        memories: Pre-retrieved memories, sorted by relevance score (from engine).
        model: LiteLLM model string for token counting.
        response_reserve: Tokens reserved for user message + LLM response.

    Returns:
        Assembled system prompt: identity first, then context section with
        memories that fit within budget. If no memories fit, returns identity
        unchanged.
    """
    if not memories:
        return identity

    context_window = get_context_window(model)
    identity_tokens = count_tokens(identity, model)
    budget = context_window - identity_tokens - response_reserve

    if budget <= 0:
        return identity

    included: list[str] = []
    for memory in memories:
        block = _format_memory(memory)
        block_tokens = count_tokens(block, model)
        if block_tokens > budget:
            continue
        included.append(block)
        budget -= block_tokens

    if not included:
        return identity

    context_section = "\n\n## Context\n\n" + "\n\n".join(included)
    return identity + context_section
