"""HookExecutor -- wraps a ToolExecutor with before/after hook lifecycle."""
from __future__ import annotations
import logging
from signalagent.core.models import ToolResult
from signalagent.core.protocols import ToolExecutor
from signalagent.hooks.registry import HookRegistry

logger = logging.getLogger(__name__)


class HookExecutor:
    """Wraps any ToolExecutor with before/after hook lifecycle.

    Implements the ToolExecutor protocol (async callable).

    Lifecycle:
    1. Run before_tool_call on each hook. If any returns a ToolResult,
       stop and use it (blocked). Set blocked=True.
    2. If not blocked: call inner executor. Set blocked=False.
    3. Run after_tool_call on all hooks. Always fires. Pass blocked flag.
    4. Return result.

    Failure modes:
    - fail-open (default): hook crash is logged and skipped.
    - fail-closed: hook crash blocks the call. Activated when a hook
      has a ``fail_closed`` property that returns True.
    """

    def __init__(
        self,
        inner: ToolExecutor,
        registry: HookRegistry,
        agent: str = "",
    ) -> None:
        """Initialise the hook executor.

        Args:
            inner: The underlying ToolExecutor to wrap.
            registry: HookRegistry containing the hooks to run.
            agent: Name of the owning agent, forwarded to each hook.
        """
        self._inner = inner
        self._registry = registry
        self._agent = agent

    async def __call__(self, tool_name: str, arguments: dict) -> ToolResult:
        """Run the before/after hook lifecycle around a tool call.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Arguments supplied by the LLM.

        Returns:
            ToolResult from the inner executor, or a blocking result
            from a before-hook.
        """
        hooks = self._registry.get_all()
        blocked = False
        result: ToolResult | None = None

        # Before hooks
        for hook in hooks:
            try:
                before_result = await hook.before_tool_call(
                    tool_name, arguments, agent=self._agent,
                )
            except Exception as e:
                if getattr(hook, 'fail_closed', False):
                    return ToolResult(
                        output="", error=f"Policy hook error: {e}",
                    )
                logger.warning(
                    "Hook '%s' before_tool_call raised (fail open): %s",
                    hook.name, e,
                )
                continue
            if before_result is not None:
                result = before_result
                blocked = True
                break

        # Execute tool if not blocked
        if not blocked:
            result = await self._inner(tool_name, arguments)

        assert result is not None

        # After hooks (always fire)
        for hook in hooks:
            try:
                await hook.after_tool_call(
                    tool_name, arguments, result, blocked,
                    agent=self._agent,
                )
            except Exception as e:
                if getattr(hook, 'fail_closed', False):
                    logger.error(
                        "Fail-closed hook '%s' after_tool_call raised: %s",
                        hook.name, e,
                    )
                else:
                    logger.warning(
                        "Hook '%s' after_tool_call raised: %s",
                        hook.name, e,
                    )

        return result
