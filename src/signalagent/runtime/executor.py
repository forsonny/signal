"""Single-agent executor -- the minimal agentic loop for Phase 1."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

from signalagent.core.models import Profile

logger = logging.getLogger(__name__)


@runtime_checkable
class AILayerProtocol(Protocol):
    """Protocol for the AI layer so executor doesn't depend on concrete class."""
    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
    ) -> Any: ...


@dataclass
class ExecutorResult:
    """Result of an executor run."""
    content: str
    error: Optional[str] = None
    error_type: Optional[str] = None  # Exception class name, e.g. "AIError"
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class Executor:
    """Minimal executor: takes a user message, builds a prompt, calls the AI layer, returns a result.

    Error boundary: exceptions from the AI layer are caught, logged,
    and returned as an ExecutorResult with error set. The caller never
    sees an unhandled exception from here.
    """

    def __init__(self, ai: AILayerProtocol, profile: Profile) -> None:
        self._ai = ai
        self._profile = profile

    async def run(self, user_message: str) -> ExecutorResult:
        """Execute a single message through the AI layer.

        Args:
            user_message: The user's input text.

        Returns:
            ExecutorResult with content or error. Never raises.
        """
        messages = [
            {"role": "system", "content": self._profile.prime.identity},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await self._ai.complete(messages=messages)
            return ExecutorResult(
                content=response.content,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost=response.cost,
            )
        except Exception as e:
            logger.error("Executor error: %s", e, exc_info=True)
            return ExecutorResult(
                content="",
                error=str(e),
                error_type=type(e).__name__,
            )
