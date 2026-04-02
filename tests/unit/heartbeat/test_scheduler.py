"""Unit tests for HeartbeatScheduler."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalagent.comms.bus import MessageBus
from signalagent.core.models import Message
from signalagent.core.types import HEARTBEAT_SENDER, MessageType
from signalagent.heartbeat.models import (
    ClockTrigger,
    FileEventTrigger,
    TriggerGuards,
    TriggerState,
)
from signalagent.heartbeat.scheduler import HeartbeatScheduler


class TestGuardEvaluation:
    def test_disabled_trigger_does_not_fire(self):
        trigger = ClockTrigger(
            name="t",
            cron="* * * * *",
            recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        state = TriggerState(enabled=False)
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        assert scheduler._should_fire(trigger, state, now) is False

    def test_max_fires_disables_trigger(self):
        trigger = ClockTrigger(
            name="t",
            cron="* * * * *",
            recipient="prime",
            guards=TriggerGuards(max_fires=5, cooldown_seconds=0),
        )
        state = TriggerState(fire_count=5, enabled=True)
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        assert scheduler._should_fire(trigger, state, now) is False
        assert state.enabled is False

    def test_cooldown_blocks_fire(self):
        trigger = ClockTrigger(
            name="t",
            cron="* * * * *",
            recipient="prime",
            guards=TriggerGuards(cooldown_seconds=60),
        )
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        state = TriggerState(last_fired=now - timedelta(seconds=30))
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is False

    def test_cooldown_expired_allows_fire(self):
        trigger = ClockTrigger(
            name="t",
            cron="* * * * *",
            recipient="prime",
            guards=TriggerGuards(cooldown_seconds=60),
        )
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        state = TriggerState(last_fired=now - timedelta(seconds=61))
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is True


class TestClockTriggerDedup:
    def test_same_minute_does_not_refire(self):
        trigger = ClockTrigger(
            name="t",
            cron="* * * * *",
            recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        state = TriggerState(
            last_matched_minute=now.replace(second=0, microsecond=0)
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is False

    def test_new_minute_allows_fire(self):
        trigger = ClockTrigger(
            name="t",
            cron="* * * * *",
            recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        now = datetime(2026, 4, 2, 14, 31, tzinfo=timezone.utc)
        prev = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        state = TriggerState(last_matched_minute=prev)
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is True

    def test_cron_mismatch_returns_false(self):
        trigger = ClockTrigger(
            name="t",
            cron="0 * * * *",
            recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        now = datetime(2026, 4, 2, 14, 15, tzinfo=timezone.utc)
        state = TriggerState()
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is False


class TestFileEventTriggerCheck:
    def test_respects_interval(self):
        trigger = FileEventTrigger(
            name="watch",
            recipient="prime",
            interval_seconds=30,
            guards=TriggerGuards(cooldown_seconds=0),
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        scheduler._detectors["watch"] = MagicMock()
        scheduler._detectors["watch"].check.return_value = ["a.py"]

        now = datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc)

        # First check: fires (no last_check)
        assert (
            scheduler._should_fire(trigger, scheduler._state["watch"], now)
            is True
        )

        # Second check at +10s: interval not elapsed
        now2 = now + timedelta(seconds=10)
        assert (
            scheduler._should_fire(trigger, scheduler._state["watch"], now2)
            is False
        )

        # Third check at +31s: interval elapsed
        now3 = now + timedelta(seconds=31)
        assert (
            scheduler._should_fire(trigger, scheduler._state["watch"], now3)
            is True
        )

    def test_no_changes_returns_false(self):
        trigger = FileEventTrigger(
            name="watch",
            recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        scheduler._detectors["watch"] = MagicMock()
        scheduler._detectors["watch"].check.return_value = []

        now = datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc)
        assert (
            scheduler._should_fire(trigger, scheduler._state["watch"], now)
            is False
        )

    def test_stores_pending_changes(self):
        trigger = FileEventTrigger(
            name="watch",
            recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        scheduler._detectors["watch"] = MagicMock()
        scheduler._detectors["watch"].check.return_value = ["a.py", "b.py"]

        now = datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc)
        scheduler._should_fire(trigger, scheduler._state["watch"], now)
        assert scheduler._pending_changes["watch"] == ["a.py", "b.py"]


class TestDispatch:
    @pytest.mark.asyncio
    async def test_sends_trigger_message(self):
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=None)

        trigger = ClockTrigger(
            name="test",
            cron="* * * * *",
            recipient="prime",
            payload="Do a check.",
        )
        scheduler = HeartbeatScheduler(bus=mock_bus, triggers=[trigger])
        state = scheduler._state["test"]
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)

        await scheduler._dispatch(trigger, state, now)

        mock_bus.send.assert_called_once()
        msg = mock_bus.send.call_args[0][0]
        assert msg.type == MessageType.TRIGGER
        assert msg.sender == HEARTBEAT_SENDER
        assert msg.recipient == "prime"
        assert msg.content == "Do a check."
        assert msg.metadata["trigger_name"] == "test"

    @pytest.mark.asyncio
    async def test_updates_state_on_success(self):
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=None)

        trigger = ClockTrigger(
            name="test", cron="* * * * *", recipient="prime"
        )
        scheduler = HeartbeatScheduler(bus=mock_bus, triggers=[trigger])
        state = scheduler._state["test"]
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)

        await scheduler._dispatch(trigger, state, now)

        assert state.fire_count == 1
        assert state.last_fired == now
        assert state.consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_increments_errors_on_failure(self):
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(side_effect=Exception("bus down"))

        trigger = ClockTrigger(
            name="test",
            cron="* * * * *",
            recipient="prime",
            guards=TriggerGuards(error_threshold=3),
        )
        scheduler = HeartbeatScheduler(bus=mock_bus, triggers=[trigger])
        state = scheduler._state["test"]
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)

        await scheduler._dispatch(trigger, state, now)
        assert state.consecutive_errors == 1
        assert state.enabled is True

    @pytest.mark.asyncio
    async def test_disables_on_error_threshold(self):
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(side_effect=Exception("bus down"))

        trigger = ClockTrigger(
            name="test",
            cron="* * * * *",
            recipient="prime",
            guards=TriggerGuards(error_threshold=2),
        )
        scheduler = HeartbeatScheduler(bus=mock_bus, triggers=[trigger])
        state = scheduler._state["test"]
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)

        await scheduler._dispatch(trigger, state, now)
        await scheduler._dispatch(trigger, state, now)

        assert state.consecutive_errors == 2
        assert state.enabled is False

    @pytest.mark.asyncio
    async def test_file_event_payload_substitution(self):
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=None)

        trigger = FileEventTrigger(
            name="watch",
            recipient="prime",
            payload="Changed: {changed_files}",
        )
        scheduler = HeartbeatScheduler(bus=mock_bus, triggers=[trigger])
        scheduler._pending_changes["watch"] = ["a.py", "b.py"]
        state = scheduler._state["watch"]
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)

        await scheduler._dispatch(trigger, state, now)

        msg = mock_bus.send.call_args[0][0]
        assert msg.content == "Changed: a.py, b.py"
        assert "watch" not in scheduler._pending_changes  # consumed


class TestSchedulerLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        trigger = ClockTrigger(
            name="t", cron="* * * * *", recipient="prime"
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        await scheduler.start()
        assert scheduler._task is not None
        assert not scheduler._task.done()
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        trigger = ClockTrigger(
            name="t", cron="* * * * *", recipient="prime"
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        await scheduler.start()
        await scheduler.stop()
        assert scheduler._task.done()

    @pytest.mark.asyncio
    async def test_start_initializes_file_detectors(self):
        trigger = FileEventTrigger(
            name="watch", recipient="prime", path="."
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        await scheduler.start()
        assert "watch" in scheduler._detectors
        await scheduler.stop()
