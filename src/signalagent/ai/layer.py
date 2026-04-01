"""AI layer -- unified interface to LLM providers via LiteLLM."""

from __future__ import annotations

import json
from typing import Optional

import litellm
from pydantic import BaseModel, ConfigDict, Field

from signalagent.core.config import SignalConfig
from signalagent.core.errors import AIError
from signalagent.core.models import ToolCallRequest

# Suppress LiteLLM's verbose logging (attribute may not exist in all versions)
try:
    litellm.suppress_debug_info = True
except AttributeError:
    pass


class AIResponse(BaseModel):
    """Unified response from any LLM provider."""
    model_config = ConfigDict(extra="forbid")

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)


class AILayer:
    """Wraps LiteLLM to provide a unified LLM interface for all agents."""

    def __init__(self, config: SignalConfig) -> None:
        self._config = config

    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: list[dict] | None = None,
    ) -> AIResponse:
        """Send a completion request to an LLM provider.

        Args:
            messages: Chat messages in OpenAI format.
            model: Model identifier. Falls back to config default.

        Returns:
            Unified AIResponse regardless of provider.

        Raises:
            AIError: If the LLM call fails for any reason.
        """
        model = model or self._config.ai.default_model
        try:
            kwargs: dict = {"model": model, "messages": messages}
            if tools is not None:
                kwargs["tools"] = tools
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            raise AIError(f"LLM call failed: {e}") from e

        choice = response.choices[0]
        usage = response.usage

        provider = model.split("/")[0] if "/" in model else "unknown"

        cost = 0.0
        try:
            cost = litellm.completion_cost(completion_response=response) or 0.0
        except Exception:
            pass

        parsed_tool_calls: list[ToolCallRequest] = []
        raw_tool_calls = choice.message.tool_calls
        if raw_tool_calls:
            for tc in raw_tool_calls:
                arguments = tc.function.arguments
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                parsed_tool_calls.append(
                    ToolCallRequest(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    )
                )

        return AIResponse(
            content=choice.message.content or "",
            model=response.model or model,
            provider=provider,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cost=cost,
            tool_calls=parsed_tool_calls,
        )
