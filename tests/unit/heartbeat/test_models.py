"""Unit tests for heartbeat trigger models."""

import pytest
from pydantic import ValidationError

from signalagent.heartbeat.models import (
    TriggerGuards,
    ClockTrigger,
    FileEventTrigger,
    TriggerState,
)


class TestTriggerGuards:
    def test_defaults(self):
        guards = TriggerGuards()
        assert guards.cooldown_seconds == 60
        assert guards.max_fires == 0
        assert guards.error_threshold == 3

    def test_custom_values(self):
        guards = TriggerGuards(cooldown_seconds=120, max_fires=10, error_threshold=5)
        assert guards.cooldown_seconds == 120
        assert guards.max_fires == 10
        assert guards.error_threshold == 5

    def test_cooldown_rejects_negative(self):
        with pytest.raises(ValidationError):
            TriggerGuards(cooldown_seconds=-1)

    def test_max_fires_rejects_negative(self):
        with pytest.raises(ValidationError):
            TriggerGuards(max_fires=-1)

    def test_error_threshold_rejects_zero(self):
        with pytest.raises(ValidationError):
            TriggerGuards(error_threshold=0)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            TriggerGuards(bogus="field")


class TestClockTrigger:
    def test_minimal(self):
        t = ClockTrigger(name="test", cron="*/5 * * * *", recipient="prime")
        assert t.name == "test"
        assert t.cron == "*/5 * * * *"
        assert t.recipient == "prime"
        assert t.payload == ""
        assert t.guards.cooldown_seconds == 60

    def test_full(self):
        t = ClockTrigger(
            name="hourly-check",
            cron="0 * * * *",
            recipient="code-review",
            payload="Do a review.",
            guards=TriggerGuards(cooldown_seconds=3600, max_fires=24),
        )
        assert t.payload == "Do a review."
        assert t.guards.max_fires == 24

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ClockTrigger(name="t", cron="* * * * *", recipient="prime", bogus="x")


class TestFileEventTrigger:
    def test_minimal(self):
        t = FileEventTrigger(name="watch", recipient="prime")
        assert t.path == "."
        assert t.interval_seconds == 30
        assert t.payload == ""

    def test_full(self):
        t = FileEventTrigger(
            name="code-watch",
            path="src",
            interval_seconds=60,
            recipient="code-review",
            payload="Changed: {changed_files}",
            guards=TriggerGuards(cooldown_seconds=120),
        )
        assert t.path == "src"
        assert t.interval_seconds == 60

    def test_interval_rejects_below_5(self):
        with pytest.raises(ValidationError):
            FileEventTrigger(name="t", recipient="p", interval_seconds=4)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            FileEventTrigger(name="t", recipient="p", bogus="x")


class TestTriggerState:
    def test_defaults(self):
        state = TriggerState()
        assert state.last_fired is None
        assert state.fire_count == 0
        assert state.consecutive_errors == 0
        assert state.enabled is True
        assert state.last_matched_minute is None

    def test_mutable(self):
        """TriggerState is a mutable dataclass, not a frozen Pydantic model."""
        state = TriggerState()
        state.fire_count = 5
        state.enabled = False
        assert state.fire_count == 5
        assert state.enabled is False
