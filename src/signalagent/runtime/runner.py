"""AgenticRunner -- agentic loop with tool calling."""
from __future__ import annotations
import json
import logging
from pydantic import BaseModel, ConfigDict
from signalagent.core.models import ToolResult
from signalagent.core.protocols import AILayerProtocol, ToolExecutor

logger = logging.getLogger(__name__)


class RunnerResult(BaseModel):
    """Result of an agentic runner execution."""
    model_config = ConfigDict(extra="forbid")
    content: str
    iterations: int
    tool_calls_made: int
    truncated: bool = False


class AgenticRunner:
    """Agentic loop: call AI, execute tools, feed results back, repeat."""

    def __init__(
        self,
        ai: AILayerProtocol,
        tool_executor: ToolExecutor,
        tool_schemas: list[dict],
        max_iterations: int,
    ) -> None:
        self._ai = ai
        self._tool_executor = tool_executor
        self._tool_schemas = tool_schemas
        self._max_iterations = max_iterations

    async def run(self, system_prompt: str, user_content: str) -> RunnerResult:
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
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
