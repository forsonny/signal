"""AgenticRunner -- agentic loop with tool calling."""
from __future__ import annotations
import json
import logging
from pydantic import BaseModel, ConfigDict
from signalagent.core.models import ToolResult
from signalagent.core.protocols import AILayerProtocol, ToolExecutor

logger = logging.getLogger(__name__)


class RunnerResult(BaseModel):
    """Result of an agentic runner execution.

    Attributes:
        content: The final assistant response text from the last LLM call.
        iterations: Total number of LLM round-trips performed.
        tool_calls_made: Cumulative count of individual tool invocations.
        truncated: ``True`` when the loop was stopped because
            *max_iterations* was reached before the model finished
            naturally.
    """

    model_config = ConfigDict(extra="forbid")
    content: str
    iterations: int
    tool_calls_made: int
    truncated: bool = False


class AgenticRunner:
    """Agentic loop: call AI, execute tools, feed results back, repeat.

    Each iteration sends the accumulated message history to the LLM.  If
    the response contains tool calls they are executed via *tool_executor*
    and the results are appended as ``tool`` messages.  The loop
    continues until the model produces a response with no tool calls or
    *max_iterations* is reached.

    Error boundary: exceptions raised by a tool executor are caught,
    converted into a :class:`~signalagent.core.models.ToolResult` with
    the error field set, and fed back to the model so it can recover.
    """

    def __init__(
        self,
        ai: AILayerProtocol,
        tool_executor: ToolExecutor,
        tool_schemas: list[dict],
        max_iterations: int,
    ) -> None:
        """Initialise the runner.

        Args:
            ai: The AI layer used for LLM completions.
            tool_executor: Callable that executes a named tool with the
                given arguments and returns a
                :class:`~signalagent.core.models.ToolResult`.
            tool_schemas: OpenAI-compatible tool/function schemas passed
                to the LLM on every call.
            max_iterations: Hard cap on LLM round-trips.  When reached
                the runner returns a :class:`RunnerResult` with
                ``truncated=True``.
        """
        self._ai = ai
        self._tool_executor = tool_executor
        self._tool_schemas = tool_schemas
        self._max_iterations = max_iterations

    async def run(
        self,
        system_prompt: str,
        user_content: str,
        history: list[dict] | None = None,
    ) -> RunnerResult:
        """Execute the agentic loop until completion or iteration limit.

        Args:
            system_prompt: System-level instruction prepended to the
                message history.
            user_content: The user message that initiates this run.
            history: Optional list of prior ``{"role": ..., "content": ...}``
                dicts inserted between the system prompt and the user
                message for multi-turn context.

        Returns:
            A :class:`RunnerResult` containing the final assistant text,
            iteration and tool-call counts, and whether the run was
            truncated.
        """
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        tools = self._tool_schemas if self._tool_schemas else None
        iterations = 0
        total_tool_calls = 0
        last_content = ""

        while iterations < self._max_iterations:
            iterations += 1
            response = await self._ai.complete(messages=messages, tools=tools)
            last_content = response.content or ""

            if not response.tool_calls:
                return RunnerResult(
                    content=last_content,
                    iterations=iterations,
                    tool_calls_made=total_tool_calls,
                )

            # Append assistant message with tool calls (LiteLLM format)
            messages.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ],
            })

            # Execute each tool call and append results
            for tc in response.tool_calls:
                total_tool_calls += 1
                try:
                    result = await self._tool_executor(tc.name, tc.arguments)
                except Exception as e:
                    logger.warning("Tool executor raised: %s", e)
                    result = ToolResult(output="", error=str(e))

                if result.error:
                    content = f"Error: {result.error}"
                else:
                    content = result.output

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })

        # Hit iteration limit
        return RunnerResult(
            content=last_content,
            iterations=iterations,
            tool_calls_made=total_tool_calls,
            truncated=True,
        )
