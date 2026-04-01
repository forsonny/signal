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
    """

    # NOTE: Fail-open is correct for observer hooks (log_tool_calls)
    # where a logging failure should not block work. When safety-gate
    # hooks land, this should become configurable -- a gate hook that
    # crashes may indicate a dangerous edge case, and fail-closed
    # would be safer. For now, all hooks fail open.

    def __init__(self, inner: ToolExecutor, registry: HookRegistry) -> None:
        self._inner = inner
        self._registry = registry

    async def __call__(self, tool_name: str, arguments: dict) -> ToolResult:
        hooks = self._registry.get_all()
        blocked = False
        result: ToolResult | None = None

        # Before hooks
        for hook in hooks:
            try:
                before_result = await hook.before_tool_call(tool_name, arguments)
            except Exception as e:
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
                await hook.after_tool_call(tool_name, arguments, result, blocked)
            except Exception as e:
                logger.warning("Hook '%s' after_tool_call raised: %s", hook.name, e)

        return result
