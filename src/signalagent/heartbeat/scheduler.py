"""HeartbeatScheduler -- in-process async trigger loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from signalagent.comms.bus import MessageBus

from signalagent.core.models import Message
from signalagent.core.types import HEARTBEAT_SENDER, MessageType
from signalagent.heartbeat.cron import cron_match
from signalagent.heartbeat.detector import FileChangeDetector
from signalagent.heartbeat.models import (
    ClockTrigger,
    FileEventTrigger,
    TriggerState,
)

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 1

Trigger = Union[ClockTrigger, FileEventTrigger]


class HeartbeatScheduler:
    """In-process async scheduler for clock and file event triggers.

    Ticks every TICK_INTERVAL_SECONDS, evaluates each trigger's guards
    and type-specific condition, dispatches via MessageBus on match.
    """

    def __init__(self, bus: MessageBus, triggers: list[Trigger]) -> None:
        self._bus = bus
        self._triggers = triggers
        self._state: dict[str, TriggerState] = {
            t.name: TriggerState() for t in triggers
        }
        self._detectors: dict[str, FileChangeDetector] = {}
        self._pending_changes: dict[str, list[str]] = {}
        self._last_check: dict[str, datetime] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the scheduler as a background asyncio task."""
        for t in self._triggers:
            if isinstance(t, FileEventTrigger):
                self._detectors[t.name] = FileChangeDetector(t.path)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the background task and wait for clean exit."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        """Main tick loop."""
        while True:
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
            now = datetime.now(timezone.utc)
            for trigger in self._triggers:
                state = self._state[trigger.name]
                if not state.enabled:
                    continue
                if self._should_fire(trigger, state, now):
                    await self._dispatch(trigger, state, now)

    def _should_fire(
        self, trigger: Trigger, state: TriggerState, now: datetime
    ) -> bool:
        """Evaluate guards and type-specific condition."""
        if not state.enabled:
            return False

        # Guard: max_fires
        if (
            trigger.guards.max_fires > 0
            and state.fire_count >= trigger.guards.max_fires
        ):
            state.enabled = False
            logger.info(
                "Trigger '%s' disabled: reached max_fires (%d)",
                trigger.name,
                trigger.guards.max_fires,
            )
            return False

        # Guard: cooldown
        if state.last_fired:
            elapsed = (now - state.last_fired).total_seconds()
            if elapsed < trigger.guards.cooldown_seconds:
                return False

        # Type-specific check
        if isinstance(trigger, ClockTrigger):
            return self._check_clock(trigger, state, now)
        if isinstance(trigger, FileEventTrigger):
            return self._check_file_event(trigger, state, now)
        return False

    def _check_clock(
        self, trigger: ClockTrigger, state: TriggerState, now: datetime
    ) -> bool:
        """Cron dedup + match. Evaluates once per minute transition."""
        current_minute = now.replace(second=0, microsecond=0)
        if state.last_matched_minute == current_minute:
            return False

        if cron_match(trigger.cron, now):
            state.last_matched_minute = current_minute
            return True
        return False

    def _check_file_event(
        self, trigger: FileEventTrigger, state: TriggerState, now: datetime
    ) -> bool:
        """Polling interval + file change check."""
        last = self._last_check.get(trigger.name)
        if last and (now - last).total_seconds() < trigger.interval_seconds:
            return False

        self._last_check[trigger.name] = now
        detector = self._detectors.get(trigger.name)
        if detector is None:
            return False

        changed = detector.check()
        if changed:
            self._pending_changes[trigger.name] = changed
            return True
        return False

    async def _dispatch(
        self, trigger: Trigger, state: TriggerState, now: datetime
    ) -> None:
        """Send trigger message via bus, update state."""
        content = trigger.payload
        if (
            isinstance(trigger, FileEventTrigger)
            and trigger.name in self._pending_changes
        ):
            file_list = ", ".join(self._pending_changes.pop(trigger.name))
            content = content.replace("{changed_files}", file_list)

        message = Message(
            type=MessageType.TRIGGER,
            sender=HEARTBEAT_SENDER,
            recipient=trigger.recipient,
            content=content,
            metadata={"trigger_name": trigger.name},
        )

        try:
            await self._bus.send(message)
            state.last_fired = now
            state.fire_count += 1
            state.consecutive_errors = 0
        except Exception:
            logger.error(
                "Trigger '%s' dispatch failed", trigger.name, exc_info=True
            )
            state.consecutive_errors += 1
            if state.consecutive_errors >= trigger.guards.error_threshold:
                state.enabled = False
                logger.warning(
                    "Trigger '%s' disabled after %d consecutive errors",
                    trigger.name,
                    state.consecutive_errors,
                )
