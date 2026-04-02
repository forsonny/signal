# Phase 7: Heartbeat Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-process async heartbeat scheduler that fires clock triggers (cron) and file event triggers (git-status polling) into the existing MessageBus, enabling autonomous agent behavior while the runtime is running.

**Architecture:** The scheduler is a background asyncio task created at bootstrap. It ticks every 1 second, evaluates trigger guard conditions, and dispatches `Message(type=TRIGGER)` through the bus. Agents receive triggers via their existing `_handle()` path -- zero changes to PrimeAgent. File change detection uses `subprocess.run()` directly (infrastructure code, not tool pipeline).

**Tech Stack:** Python 3.11+, Pydantic v2 (`extra="forbid"`), asyncio, subprocess, pytest + pytest-asyncio

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `src/signalagent/heartbeat/__init__.py` | Package init (empty) |
| `src/signalagent/heartbeat/models.py` | `TriggerGuards`, `ClockTrigger`, `FileEventTrigger`, `TriggerState` |
| `src/signalagent/heartbeat/cron.py` | `cron_match()`, `validate_cron()` pure functions |
| `src/signalagent/heartbeat/detector.py` | `FileChangeDetector` -- git status / mtime polling |
| `src/signalagent/heartbeat/scheduler.py` | `HeartbeatScheduler` -- async tick loop + dispatch |
| `tests/unit/heartbeat/__init__.py` | Test package init (empty) |
| `tests/unit/heartbeat/test_models.py` | Trigger model validation tests |
| `tests/unit/heartbeat/test_cron.py` | Cron matching + validation tests |
| `tests/unit/heartbeat/test_detector.py` | File change detection tests |
| `tests/unit/heartbeat/test_scheduler.py` | Scheduler tick/dispatch/guard tests |

### Modified Files

| File | Change |
|------|--------|
| `src/signalagent/core/types.py:79` | Add `HEARTBEAT_SENDER` constant |
| `src/signalagent/core/models.py:42-48` | Replace `HeartbeatConfig` dict fields with typed triggers |
| `src/signalagent/comms/bus.py:1-8,82-84` | Import `HEARTBEAT_SENDER`, add `_VIRTUAL_SENDERS` set |
| `src/signalagent/runtime/bootstrap.py:1-4,144-149` | Import heartbeat, validate cron, create + start scheduler |
| `src/signalagent/profiles/blank.yaml` | Add empty heartbeat section matching new schema |

---

### Task 1: Trigger Models

**Files:**
- Create: `src/signalagent/heartbeat/__init__.py`
- Create: `src/signalagent/heartbeat/models.py`
- Create: `tests/unit/heartbeat/__init__.py`
- Create: `tests/unit/heartbeat/test_models.py`

- [ ] **Step 1: Write the failing tests for TriggerGuards**

```python
# tests/unit/heartbeat/test_models.py
"""Unit tests for heartbeat trigger models."""

import pytest
from pydantic import ValidationError

from signalagent.heartbeat.models import TriggerGuards


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/heartbeat/test_models.py::TestTriggerGuards -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalagent.heartbeat'`

- [ ] **Step 3: Implement TriggerGuards**

```python
# src/signalagent/heartbeat/__init__.py
# (empty)
```

```python
# src/signalagent/heartbeat/models.py
"""Heartbeat trigger models and runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TriggerGuards(BaseModel):
    """Safety guards shared by all trigger types."""

    model_config = ConfigDict(extra="forbid")

    cooldown_seconds: int = Field(default=60, ge=0)
    max_fires: int = Field(default=0, ge=0)  # 0 = unlimited
    error_threshold: int = Field(default=3, ge=1)
```

```python
# tests/unit/heartbeat/__init__.py
# (empty)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/heartbeat/test_models.py::TestTriggerGuards -v`
Expected: All 6 PASS

- [ ] **Step 5: Write failing tests for ClockTrigger**

Add to `tests/unit/heartbeat/test_models.py`:

```python
from signalagent.heartbeat.models import TriggerGuards, ClockTrigger


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
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m pytest tests/unit/heartbeat/test_models.py::TestClockTrigger -v`
Expected: FAIL with `ImportError: cannot import name 'ClockTrigger'`

- [ ] **Step 7: Implement ClockTrigger**

Add to `src/signalagent/heartbeat/models.py`:

```python
class ClockTrigger(BaseModel):
    """Time-based trigger using cron expressions."""

    model_config = ConfigDict(extra="forbid")

    name: str
    cron: str
    recipient: str
    payload: str = ""
    guards: TriggerGuards = Field(default_factory=TriggerGuards)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/unit/heartbeat/test_models.py::TestClockTrigger -v`
Expected: All 3 PASS

- [ ] **Step 9: Write failing tests for FileEventTrigger**

Add to `tests/unit/heartbeat/test_models.py`:

```python
from signalagent.heartbeat.models import (
    TriggerGuards,
    ClockTrigger,
    FileEventTrigger,
)


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
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `python -m pytest tests/unit/heartbeat/test_models.py::TestFileEventTrigger -v`
Expected: FAIL with `ImportError: cannot import name 'FileEventTrigger'`

- [ ] **Step 11: Implement FileEventTrigger**

Add to `src/signalagent/heartbeat/models.py`:

```python
class FileEventTrigger(BaseModel):
    """Polling-based file change trigger."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str = "."
    interval_seconds: int = Field(default=30, ge=5)
    recipient: str
    payload: str = ""
    guards: TriggerGuards = Field(default_factory=TriggerGuards)
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `python -m pytest tests/unit/heartbeat/test_models.py::TestFileEventTrigger -v`
Expected: All 4 PASS

- [ ] **Step 13: Write failing test for TriggerState**

Add to `tests/unit/heartbeat/test_models.py`:

```python
from signalagent.heartbeat.models import (
    TriggerGuards,
    ClockTrigger,
    FileEventTrigger,
    TriggerState,
)


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
```

- [ ] **Step 14: Run tests to verify they fail**

Run: `python -m pytest tests/unit/heartbeat/test_models.py::TestTriggerState -v`
Expected: FAIL with `ImportError: cannot import name 'TriggerState'`

- [ ] **Step 15: Implement TriggerState**

Add to `src/signalagent/heartbeat/models.py`:

```python
@dataclass
class TriggerState:
    """Runtime-only mutable state per trigger.

    Not persisted -- resets on process restart. fire_count,
    consecutive_errors, and last_fired all start fresh.
    """

    last_fired: datetime | None = None
    fire_count: int = 0
    consecutive_errors: int = 0
    enabled: bool = True
    last_matched_minute: datetime | None = None
```

- [ ] **Step 16: Run all model tests**

Run: `python -m pytest tests/unit/heartbeat/test_models.py -v`
Expected: All 15 PASS

- [ ] **Step 17: Commit**

```bash
git add src/signalagent/heartbeat/__init__.py src/signalagent/heartbeat/models.py tests/unit/heartbeat/__init__.py tests/unit/heartbeat/test_models.py
git commit -m "feat(heartbeat): add trigger models -- TriggerGuards, ClockTrigger, FileEventTrigger, TriggerState"
```

---

### Task 2: Update HeartbeatConfig + HEARTBEAT_SENDER

**Files:**
- Modify: `src/signalagent/core/types.py:79-80`
- Modify: `src/signalagent/core/models.py:1-9,42-48`
- Modify: `tests/unit/core/test_models.py:8-22`

- [ ] **Step 1: Write failing test for HEARTBEAT_SENDER**

Add to `tests/unit/core/test_models.py` at the top imports:

```python
from signalagent.core.types import MemoryType, MessageType, HEARTBEAT_SENDER
```

Add new test class:

```python
class TestHeartbeatSender:
    def test_heartbeat_sender_value(self):
        from signalagent.core.types import HEARTBEAT_SENDER
        assert HEARTBEAT_SENDER == "heartbeat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/core/test_models.py::TestHeartbeatSender -v`
Expected: FAIL with `ImportError: cannot import name 'HEARTBEAT_SENDER'`

- [ ] **Step 3: Add HEARTBEAT_SENDER constant**

In `src/signalagent/core/types.py`, after line 79 (`USER_SENDER = "user"`), add:

```python
HEARTBEAT_SENDER = "heartbeat"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/core/test_models.py::TestHeartbeatSender -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for updated HeartbeatConfig**

Add to `tests/unit/core/test_models.py`:

```python
from signalagent.heartbeat.models import ClockTrigger, FileEventTrigger, TriggerGuards


class TestHeartbeatConfig:
    def test_defaults_empty(self):
        hc = HeartbeatConfig()
        assert hc.clock_triggers == []
        assert hc.event_triggers == []

    def test_with_clock_trigger(self):
        hc = HeartbeatConfig(
            clock_triggers=[
                ClockTrigger(name="test", cron="* * * * *", recipient="prime"),
            ],
        )
        assert len(hc.clock_triggers) == 1
        assert hc.clock_triggers[0].name == "test"

    def test_with_event_trigger(self):
        hc = HeartbeatConfig(
            event_triggers=[
                FileEventTrigger(name="watch", recipient="prime"),
            ],
        )
        assert len(hc.event_triggers) == 1

    def test_rejects_condition_triggers(self):
        """condition_triggers field removed -- extra fields forbidden."""
        with pytest.raises(ValidationError):
            HeartbeatConfig(condition_triggers=[])

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            HeartbeatConfig(bogus="x")
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m pytest tests/unit/core/test_models.py::TestHeartbeatConfig -v`
Expected: FAIL (current HeartbeatConfig still uses `list[dict]` and has `condition_triggers`)

- [ ] **Step 7: Update HeartbeatConfig in models.py**

Replace lines 42-48 of `src/signalagent/core/models.py`:

Old:
```python
class HeartbeatConfig(BaseModel):
    """Heartbeat trigger configuration from a profile."""
    model_config = ConfigDict(extra="forbid")

    clock_triggers: list[dict] = Field(default_factory=list)
    event_triggers: list[dict] = Field(default_factory=list)
    condition_triggers: list[dict] = Field(default_factory=list)
```

New:
```python
from signalagent.heartbeat.models import ClockTrigger, FileEventTrigger


class HeartbeatConfig(BaseModel):
    """Heartbeat trigger configuration from a profile."""
    model_config = ConfigDict(extra="forbid")

    clock_triggers: list[ClockTrigger] = Field(default_factory=list)
    event_triggers: list[FileEventTrigger] = Field(default_factory=list)
```

Note: The import `from signalagent.heartbeat.models import ClockTrigger, FileEventTrigger` should be placed with the other imports at the top of the file (after line 8). Use a `TYPE_CHECKING` guard if a circular import arises, but it should not -- heartbeat.models imports from pydantic only, not from core.models.

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/unit/core/test_models.py::TestHeartbeatConfig -v`
Expected: All 5 PASS

- [ ] **Step 9: Run full model test suite to check nothing broke**

Run: `python -m pytest tests/unit/core/test_models.py -v`
Expected: All PASS (existing tests that construct `HeartbeatConfig()` with defaults still work)

- [ ] **Step 10: Commit**

```bash
git add src/signalagent/core/types.py src/signalagent/core/models.py tests/unit/core/test_models.py
git commit -m "feat(heartbeat): add HEARTBEAT_SENDER, update HeartbeatConfig with typed triggers"
```

---

### Task 3: Cron Matching

**Files:**
- Create: `src/signalagent/heartbeat/cron.py`
- Create: `tests/unit/heartbeat/test_cron.py`

- [ ] **Step 1: Write failing tests for cron_match**

```python
# tests/unit/heartbeat/test_cron.py
"""Unit tests for cron matching -- pure function, no I/O."""

import pytest
from datetime import datetime

from signalagent.heartbeat.cron import cron_match, validate_cron


class TestCronMatchWildcard:
    def test_all_stars_matches_any_time(self):
        dt = datetime(2026, 4, 2, 14, 30)  # Wednesday
        assert cron_match("* * * * *", dt) is True

    def test_all_stars_matches_midnight(self):
        dt = datetime(2026, 1, 1, 0, 0)  # Thursday
        assert cron_match("* * * * *", dt) is True


class TestCronMatchExact:
    def test_exact_minute(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("30 * * * *", dt) is True
        assert cron_match("31 * * * *", dt) is False

    def test_exact_hour(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* 14 * * *", dt) is True
        assert cron_match("* 15 * * *", dt) is False

    def test_exact_day_of_month(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* * 2 * *", dt) is True
        assert cron_match("* * 3 * *", dt) is False

    def test_exact_month(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* * * 4 *", dt) is True
        assert cron_match("* * * 5 *", dt) is False

    def test_exact_day_of_week_iso(self):
        """2026-04-02 is Thursday = weekday() 3."""
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* * * * 3", dt) is True  # Thursday
        assert cron_match("* * * * 0", dt) is False  # Monday

    def test_all_fields_exact(self):
        dt = datetime(2026, 4, 2, 14, 30)  # Thursday
        assert cron_match("30 14 2 4 3", dt) is True
        assert cron_match("30 14 2 4 0", dt) is False  # wrong dow


class TestCronMatchRange:
    def test_minute_range(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("25-35 * * * *", dt) is True
        assert cron_match("0-10 * * * *", dt) is False

    def test_hour_range(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* 9-17 * * *", dt) is True
        assert cron_match("* 0-8 * * *", dt) is False


class TestCronMatchStep:
    def test_every_5_minutes(self):
        assert cron_match("*/5 * * * *", datetime(2026, 4, 2, 14, 0)) is True
        assert cron_match("*/5 * * * *", datetime(2026, 4, 2, 14, 5)) is True
        assert cron_match("*/5 * * * *", datetime(2026, 4, 2, 14, 3)) is False

    def test_every_2_hours(self):
        assert cron_match("* */2 * * *", datetime(2026, 4, 2, 0, 0)) is True
        assert cron_match("* */2 * * *", datetime(2026, 4, 2, 2, 0)) is True
        assert cron_match("* */2 * * *", datetime(2026, 4, 2, 1, 0)) is False


class TestCronMatchCommaList:
    def test_minute_list(self):
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("0,15,30,45 * * * *", dt) is True
        assert cron_match("0,15,45 * * * *", dt) is False

    def test_day_of_week_list(self):
        """Thursday = 3."""
        dt = datetime(2026, 4, 2, 14, 30)
        assert cron_match("* * * * 0,3,4", dt) is True  # Mon,Thu,Fri
        assert cron_match("* * * * 0,1,4", dt) is False  # Mon,Tue,Fri


class TestCronMatchCombination:
    def test_range_and_list(self):
        """1-5,15,30 should match 3, 15, 30 but not 10."""
        assert cron_match("1-5,15,30 * * * *", datetime(2026, 4, 2, 14, 3)) is True
        assert cron_match("1-5,15,30 * * * *", datetime(2026, 4, 2, 14, 15)) is True
        assert cron_match("1-5,15,30 * * * *", datetime(2026, 4, 2, 14, 10)) is False

    def test_realistic_business_hours(self):
        """Every 15 min during business hours (9-17) on weekdays (0-4)."""
        expr = "0,15,30,45 9-17 * * 0-4"
        # Thursday 10:15
        assert cron_match(expr, datetime(2026, 4, 2, 10, 15)) is True
        # Thursday 10:10
        assert cron_match(expr, datetime(2026, 4, 2, 10, 10)) is False
        # Saturday 10:15 (weekday 5)
        assert cron_match(expr, datetime(2026, 4, 4, 10, 15)) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/heartbeat/test_cron.py -v -k "not Validate"`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Implement cron_match**

```python
# src/signalagent/heartbeat/cron.py
"""Cron expression matching -- pure functions, no dependencies."""

from __future__ import annotations

from datetime import datetime

__all__ = ["cron_match", "validate_cron"]

# Field index -> (min_value, max_value)
_FIELD_RANGES: list[tuple[int, int]] = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week (ISO: Mon=0, Sun=6)
]


def _parse_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of matching integers.

    Supports: * (any), N (exact), N-M (range), */N (step), N,M (list),
    and combinations like 1-5,15,30.
    """
    values: set[int] = set()

    for part in field.split(","):
        part = part.strip()

        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif "/" in part:
            # Step: */N or N-M/N
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step must be positive: {part}")
            if base == "*":
                start = min_val
                end = max_val
            elif "-" in base:
                start_str, end_str = base.split("-", 1)
                start = int(start_str)
                end = int(end_str)
            else:
                start = int(base)
                end = max_val
            values.update(range(start, end + 1, step))
        elif "-" in part:
            # Range: N-M
            start_str, end_str = part.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            if start > end:
                raise ValueError(f"Invalid range: {part}")
            values.update(range(start, end + 1))
        else:
            # Exact value
            values.add(int(part))

    # Validate all values are in range
    for v in values:
        if v < min_val or v > max_val:
            raise ValueError(f"Value {v} out of range [{min_val}, {max_val}]")

    return values


def cron_match(expression: str, dt: datetime) -> bool:
    """Check if a datetime matches a 5-field cron expression.

    Fields: minute hour day-of-month month day-of-week
    Day-of-week uses ISO convention: Monday=0, Sunday=6
    (matches Python's datetime.weekday()).
    """
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}: {expression!r}")

    dt_values = [dt.minute, dt.hour, dt.day, dt.month, dt.weekday()]

    for field_str, (min_val, max_val), dt_val in zip(
        fields, _FIELD_RANGES, dt_values, strict=True,
    ):
        allowed = _parse_field(field_str, min_val, max_val)
        if dt_val not in allowed:
            return False

    return True


def validate_cron(expression: str) -> str | None:
    """Validate a cron expression. Returns error message or None if valid."""
    fields = expression.strip().split()
    if len(fields) != 5:
        return f"Expected 5 fields, got {len(fields)}"

    field_names = ["minute", "hour", "day-of-month", "month", "day-of-week"]
    for field_str, (min_val, max_val), name in zip(
        fields, _FIELD_RANGES, field_names, strict=True,
    ):
        try:
            _parse_field(field_str, min_val, max_val)
        except (ValueError, OverflowError) as e:
            return f"Invalid {name} field '{field_str}': {e}"

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/heartbeat/test_cron.py -v -k "not Validate"`
Expected: All PASS

- [ ] **Step 5: Write failing tests for validate_cron**

Add to `tests/unit/heartbeat/test_cron.py`:

```python
class TestValidateCron:
    def test_valid_expression(self):
        assert validate_cron("*/5 * * * *") is None

    def test_valid_complex(self):
        assert validate_cron("0,15,30,45 9-17 * * 0-4") is None

    def test_wrong_field_count(self):
        err = validate_cron("* * *")
        assert err is not None
        assert "5 fields" in err

    def test_too_many_fields(self):
        err = validate_cron("* * * * * *")
        assert err is not None
        assert "5 fields" in err

    def test_minute_out_of_range(self):
        err = validate_cron("60 * * * *")
        assert err is not None
        assert "minute" in err

    def test_hour_out_of_range(self):
        err = validate_cron("* 24 * * *")
        assert err is not None
        assert "hour" in err

    def test_day_of_month_zero(self):
        err = validate_cron("* * 0 * *")
        assert err is not None
        assert "day-of-month" in err

    def test_month_out_of_range(self):
        err = validate_cron("* * * 13 *")
        assert err is not None
        assert "month" in err

    def test_day_of_week_out_of_range(self):
        err = validate_cron("* * * * 7")
        assert err is not None
        assert "day-of-week" in err

    def test_invalid_syntax(self):
        err = validate_cron("abc * * * *")
        assert err is not None
        assert "minute" in err
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/heartbeat/test_cron.py::TestValidateCron -v`
Expected: All PASS (validate_cron is already implemented above)

- [ ] **Step 7: Run full cron test suite**

Run: `python -m pytest tests/unit/heartbeat/test_cron.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/signalagent/heartbeat/cron.py tests/unit/heartbeat/test_cron.py
git commit -m "feat(heartbeat): add cron_match() and validate_cron() pure functions"
```

---

### Task 4: FileChangeDetector

**Files:**
- Create: `src/signalagent/heartbeat/detector.py`
- Create: `tests/unit/heartbeat/test_detector.py`

- [ ] **Step 1: Write failing tests for git-mode detection**

```python
# tests/unit/heartbeat/test_detector.py
"""Unit tests for FileChangeDetector."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from signalagent.heartbeat.detector import FileChangeDetector


class TestGitDetection:
    def test_detects_git_repo(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)
        detector.check()  # triggers git detection
        assert detector._is_git is True

    def test_detects_non_git(self, tmp_path):
        detector = FileChangeDetector(tmp_path)
        detector.check()
        assert detector._is_git is False


class TestGitModeCheck:
    def test_returns_dirty_files_on_first_change(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            # First check: no dirty files (baseline)
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr="",
            )
            result = detector.check()
            assert result == []

            # Second check: two dirty files
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M src/main.py\n?? new_file.txt\n", stderr="",
            )
            result = detector.check()
            assert set(result) == {"src/main.py", "new_file.txt"}

    def test_returns_empty_when_dirty_set_unchanged(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            # First check: dirty
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M src/main.py\n", stderr="",
            )
            result = detector.check()
            assert result == ["src/main.py"]

            # Second check: same dirty set
            result = detector.check()
            assert result == []

    def test_resets_silently_when_dirty_becomes_clean(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            # First check: dirty
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M src/main.py\n", stderr="",
            )
            detector.check()

            # Second check: clean (files committed)
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr="",
            )
            result = detector.check()
            assert result == []  # silent reset, no trigger

    def test_new_dirty_file_triggers_again(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            # First: one dirty file
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M a.py\n", stderr="",
            )
            detector.check()

            # Second: different dirty file
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=" M b.py\n", stderr="",
            )
            result = detector.check()
            assert result == ["b.py"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/heartbeat/test_detector.py -v -k "Git"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement FileChangeDetector (git mode)**

```python
# src/signalagent/heartbeat/detector.py
"""FileChangeDetector -- git status / mtime polling for file changes.

Infrastructure code. Calls subprocess.run() directly -- not through
the tool/hook pipeline. This is scheduler-level infrastructure.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".signal", ".venv", "venv"}


class FileChangeDetector:
    """Detects file changes via git status or mtime scanning.

    API: check() -> list[str]
    Returns the current dirty file set if it changed since last check.
    Returns empty list if nothing changed.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._is_git: bool | None = None
        self._last_seen: set[str] = set()
        self._mtime_baseline: dict[str, float] = {}

    def check(self) -> list[str]:
        """Return changed files since last check, or empty list."""
        if self._is_git is None:
            self._is_git = (self._path / ".git").is_dir()

        if self._is_git:
            return self._check_git()
        return self._check_mtime()

    def _check_git(self) -> list[str]:
        """Git-mode: parse git status --porcelain output."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self._path,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(
                    "git status failed (rc=%d): %s", result.returncode, result.stderr,
                )
                return []
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("git status error: %s", e)
            return []

        # Parse porcelain output: each line is "XY filename"
        current: set[str] = set()
        for line in result.stdout.splitlines():
            if len(line) > 3:
                current.add(line[3:].strip())

        if current != self._last_seen:
            self._last_seen = current
            if current:
                return sorted(current)
        return []

    def _check_mtime(self) -> list[str]:
        """Non-git fallback: mtime-based scanning."""
        current: dict[str, float] = {}
        try:
            for child in self._path.rglob("*"):
                if child.is_file():
                    # Skip ignored directories
                    parts = child.relative_to(self._path).parts
                    if any(p in IGNORE_DIRS for p in parts):
                        continue
                    rel = str(child.relative_to(self._path))
                    current[rel] = child.stat().st_mtime
        except OSError as e:
            logger.warning("mtime scan error: %s", e)
            return []

        current_keys = set(current.keys())
        baseline_keys = set(self._mtime_baseline.keys())

        changed: set[str] = set()
        # New or modified files
        for path, mtime in current.items():
            if path not in self._mtime_baseline or self._mtime_baseline[path] != mtime:
                changed.add(path)
        # Deleted files
        changed.update(baseline_keys - current_keys)

        self._mtime_baseline = current

        if changed:
            return sorted(changed)
        return []
```

- [ ] **Step 4: Run git-mode tests to verify they pass**

Run: `python -m pytest tests/unit/heartbeat/test_detector.py -v -k "Git"`
Expected: All PASS

- [ ] **Step 5: Write failing tests for mtime fallback**

Add to `tests/unit/heartbeat/test_detector.py`:

```python
class TestMtimeMode:
    def test_detects_new_file(self, tmp_path):
        detector = FileChangeDetector(tmp_path)

        # Baseline: empty
        result = detector.check()
        assert result == []

        # Add a file
        (tmp_path / "hello.txt").write_text("hi")
        result = detector.check()
        assert "hello.txt" in result

    def test_returns_empty_when_unchanged(self, tmp_path):
        (tmp_path / "hello.txt").write_text("hi")
        detector = FileChangeDetector(tmp_path)

        # First check: baseline
        detector.check()

        # Second check: no changes
        result = detector.check()
        assert result == []

    def test_skips_ignored_dirs(self, tmp_path):
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.pyc").write_text("bytecode")

        detector = FileChangeDetector(tmp_path)
        result = detector.check()
        assert result == []


class TestErrorHandling:
    def test_git_subprocess_failure_returns_empty(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            mock_sub.run.side_effect = FileNotFoundError("git not found")
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = detector.check()
            assert result == []

    def test_git_timeout_returns_empty(self, tmp_path):
        (tmp_path / ".git").mkdir()
        detector = FileChangeDetector(tmp_path)

        with patch("signalagent.heartbeat.detector.subprocess") as mock_sub:
            mock_sub.run.side_effect = subprocess.TimeoutExpired("git", 10)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = detector.check()
            assert result == []
```

- [ ] **Step 6: Run all detector tests**

Run: `python -m pytest tests/unit/heartbeat/test_detector.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/signalagent/heartbeat/detector.py tests/unit/heartbeat/test_detector.py
git commit -m "feat(heartbeat): add FileChangeDetector with git-status and mtime modes"
```

---

### Task 5: HeartbeatScheduler

**Files:**
- Create: `src/signalagent/heartbeat/scheduler.py`
- Create: `tests/unit/heartbeat/test_scheduler.py`

- [ ] **Step 1: Write failing tests for guard evaluation**

```python
# tests/unit/heartbeat/test_scheduler.py
"""Unit tests for HeartbeatScheduler."""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signalagent.comms.bus import MessageBus
from signalagent.core.models import Message
from signalagent.core.types import MessageType, HEARTBEAT_SENDER
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
            name="t", cron="* * * * *", recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        state = TriggerState(enabled=False)
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        assert scheduler._should_fire(trigger, state, now) is False

    def test_max_fires_disables_trigger(self):
        trigger = ClockTrigger(
            name="t", cron="* * * * *", recipient="prime",
            guards=TriggerGuards(max_fires=5, cooldown_seconds=0),
        )
        state = TriggerState(fire_count=5, enabled=True)
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        assert scheduler._should_fire(trigger, state, now) is False
        assert state.enabled is False

    def test_cooldown_blocks_fire(self):
        trigger = ClockTrigger(
            name="t", cron="* * * * *", recipient="prime",
            guards=TriggerGuards(cooldown_seconds=60),
        )
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        state = TriggerState(last_fired=now - timedelta(seconds=30))
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is False

    def test_cooldown_expired_allows_fire(self):
        trigger = ClockTrigger(
            name="t", cron="* * * * *", recipient="prime",
            guards=TriggerGuards(cooldown_seconds=60),
        )
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        state = TriggerState(last_fired=now - timedelta(seconds=61))
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is True


class TestClockTriggerDedup:
    def test_same_minute_does_not_refire(self):
        trigger = ClockTrigger(
            name="t", cron="* * * * *", recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        now = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        state = TriggerState(last_matched_minute=now.replace(second=0, microsecond=0))
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is False

    def test_new_minute_allows_fire(self):
        trigger = ClockTrigger(
            name="t", cron="* * * * *", recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        now = datetime(2026, 4, 2, 14, 31, tzinfo=timezone.utc)
        prev = datetime(2026, 4, 2, 14, 30, tzinfo=timezone.utc)
        state = TriggerState(last_matched_minute=prev)
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is True

    def test_cron_mismatch_returns_false(self):
        trigger = ClockTrigger(
            name="t", cron="0 * * * *", recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        now = datetime(2026, 4, 2, 14, 15, tzinfo=timezone.utc)
        state = TriggerState()
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        assert scheduler._should_fire(trigger, state, now) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/heartbeat/test_scheduler.py -v -k "Guard or Dedup"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement HeartbeatScheduler (structure + _should_fire)**

```python
# src/signalagent/heartbeat/scheduler.py
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
from signalagent.core.types import MessageType, HEARTBEAT_SENDER
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

    def _should_fire(self, trigger: Trigger, state: TriggerState, now: datetime) -> bool:
        """Evaluate guards and type-specific condition."""
        if not state.enabled:
            return False

        # Guard: max_fires
        if trigger.guards.max_fires > 0 and state.fire_count >= trigger.guards.max_fires:
            state.enabled = False
            logger.info("Trigger '%s' disabled: reached max_fires (%d)", trigger.name, trigger.guards.max_fires)
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

    def _check_clock(self, trigger: ClockTrigger, state: TriggerState, now: datetime) -> bool:
        """Cron dedup + match. Evaluates once per minute transition."""
        current_minute = now.replace(second=0, microsecond=0)
        if state.last_matched_minute == current_minute:
            return False

        if cron_match(trigger.cron, now):
            state.last_matched_minute = current_minute
            return True
        return False

    def _check_file_event(self, trigger: FileEventTrigger, state: TriggerState, now: datetime) -> bool:
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

    async def _dispatch(self, trigger: Trigger, state: TriggerState, now: datetime) -> None:
        """Send trigger message via bus, update state."""
        content = trigger.payload
        if isinstance(trigger, FileEventTrigger) and trigger.name in self._pending_changes:
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
            logger.error("Trigger '%s' dispatch failed", trigger.name, exc_info=True)
            state.consecutive_errors += 1
            if state.consecutive_errors >= trigger.guards.error_threshold:
                state.enabled = False
                logger.warning(
                    "Trigger '%s' disabled after %d consecutive errors",
                    trigger.name, state.consecutive_errors,
                )
```

- [ ] **Step 4: Run guard + dedup tests to verify they pass**

Run: `python -m pytest tests/unit/heartbeat/test_scheduler.py -v -k "Guard or Dedup"`
Expected: All PASS

- [ ] **Step 5: Write failing tests for file event trigger evaluation**

Add to `tests/unit/heartbeat/test_scheduler.py`:

```python
class TestFileEventTriggerCheck:
    def test_respects_interval(self):
        trigger = FileEventTrigger(
            name="watch", recipient="prime", interval_seconds=30,
            guards=TriggerGuards(cooldown_seconds=0),
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        # Initialize detector
        scheduler._detectors["watch"] = MagicMock()
        scheduler._detectors["watch"].check.return_value = ["a.py"]

        now = datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc)

        # First check: fires (no last_check)
        assert scheduler._should_fire(trigger, scheduler._state["watch"], now) is True

        # Second check at +10s: interval not elapsed
        now2 = now + timedelta(seconds=10)
        assert scheduler._should_fire(trigger, scheduler._state["watch"], now2) is False

        # Third check at +31s: interval elapsed
        now3 = now + timedelta(seconds=31)
        assert scheduler._should_fire(trigger, scheduler._state["watch"], now3) is True

    def test_no_changes_returns_false(self):
        trigger = FileEventTrigger(
            name="watch", recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        scheduler._detectors["watch"] = MagicMock()
        scheduler._detectors["watch"].check.return_value = []

        now = datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc)
        assert scheduler._should_fire(trigger, scheduler._state["watch"], now) is False

    def test_stores_pending_changes(self):
        trigger = FileEventTrigger(
            name="watch", recipient="prime",
            guards=TriggerGuards(cooldown_seconds=0),
        )
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        scheduler._detectors["watch"] = MagicMock()
        scheduler._detectors["watch"].check.return_value = ["a.py", "b.py"]

        now = datetime(2026, 4, 2, 14, 30, 0, tzinfo=timezone.utc)
        scheduler._should_fire(trigger, scheduler._state["watch"], now)
        assert scheduler._pending_changes["watch"] == ["a.py", "b.py"]
```

- [ ] **Step 6: Run file event tests to verify they pass**

Run: `python -m pytest tests/unit/heartbeat/test_scheduler.py::TestFileEventTriggerCheck -v`
Expected: All PASS

- [ ] **Step 7: Write failing tests for dispatch**

Add to `tests/unit/heartbeat/test_scheduler.py`:

```python
class TestDispatch:
    @pytest.mark.asyncio
    async def test_sends_trigger_message(self):
        mock_bus = AsyncMock()
        mock_bus.send = AsyncMock(return_value=None)

        trigger = ClockTrigger(
            name="test", cron="* * * * *", recipient="prime",
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

        trigger = ClockTrigger(name="test", cron="* * * * *", recipient="prime")
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
            name="test", cron="* * * * *", recipient="prime",
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
            name="test", cron="* * * * *", recipient="prime",
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
            name="watch", recipient="prime",
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
```

- [ ] **Step 8: Run dispatch tests**

Run: `python -m pytest tests/unit/heartbeat/test_scheduler.py::TestDispatch -v`
Expected: All PASS

- [ ] **Step 9: Write failing tests for scheduler lifecycle**

Add to `tests/unit/heartbeat/test_scheduler.py`:

```python
class TestSchedulerLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        trigger = ClockTrigger(name="t", cron="* * * * *", recipient="prime")
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        await scheduler.start()
        assert scheduler._task is not None
        assert not scheduler._task.done()
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        trigger = ClockTrigger(name="t", cron="* * * * *", recipient="prime")
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        await scheduler.start()
        await scheduler.stop()
        assert scheduler._task.done()

    @pytest.mark.asyncio
    async def test_start_initializes_file_detectors(self):
        trigger = FileEventTrigger(name="watch", recipient="prime", path=".")
        scheduler = HeartbeatScheduler(bus=MagicMock(), triggers=[trigger])
        await scheduler.start()
        assert "watch" in scheduler._detectors
        await scheduler.stop()
```

- [ ] **Step 10: Run lifecycle tests**

Run: `python -m pytest tests/unit/heartbeat/test_scheduler.py::TestSchedulerLifecycle -v`
Expected: All PASS

- [ ] **Step 11: Run full scheduler test suite**

Run: `python -m pytest tests/unit/heartbeat/test_scheduler.py -v`
Expected: All PASS

- [ ] **Step 12: Commit**

```bash
git add src/signalagent/heartbeat/scheduler.py tests/unit/heartbeat/test_scheduler.py
git commit -m "feat(heartbeat): add HeartbeatScheduler with guards, cron dedup, file event polling, dispatch"
```

---

### Task 6: Virtual Sender Set in MessageBus

**Files:**
- Modify: `src/signalagent/comms/bus.py:1-8,82-84`
- Modify: `tests/unit/comms/test_bus.py`

- [ ] **Step 1: Write failing test for heartbeat sender**

Add to `tests/unit/comms/test_bus.py` imports:

```python
from signalagent.core.types import (
    MessageType,
    PRIME_AGENT,
    USER_SENDER,
    HEARTBEAT_SENDER,
)
```

Add new test class:

```python
class TestVirtualSenders:
    @pytest.mark.asyncio
    async def test_heartbeat_sender_allowed_without_registration(self):
        bus = MessageBus()
        handler_prime = AsyncMock(return_value=None)
        bus.register(PRIME_AGENT, handler_prime, talks_to=None)

        msg = _make_message(sender=HEARTBEAT_SENDER, recipient=PRIME_AGENT,
                            msg_type=MessageType.TRIGGER)
        await bus.send(msg)

        handler_prime.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_sender_still_works(self):
        """Existing USER_SENDER bypass not broken by virtual sender refactor."""
        bus = MessageBus()
        handler_prime = AsyncMock(return_value=None)
        bus.register(PRIME_AGENT, handler_prime, talks_to=None)

        msg = _make_message(sender=USER_SENDER, recipient=PRIME_AGENT)
        await bus.send(msg)

        handler_prime.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_virtual_unregistered_sender_rejected(self):
        """Non-virtual senders still require registration."""
        bus = MessageBus()
        bus.register(PRIME_AGENT, AsyncMock(), talks_to=None)

        msg = _make_message(sender="rogue-agent", recipient=PRIME_AGENT)
        with pytest.raises(RoutingError, match="not registered"):
            await bus.send(msg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/comms/test_bus.py::TestVirtualSenders -v`
Expected: FAIL (HEARTBEAT_SENDER not allowed as sender)

- [ ] **Step 3: Implement _VIRTUAL_SENDERS in bus.py**

In `src/signalagent/comms/bus.py`, update imports (line 8):

```python
from signalagent.core.types import HEARTBEAT_SENDER, USER_SENDER
```

Add after imports (before `MessageHandler` typedef):

```python
_VIRTUAL_SENDERS = frozenset({USER_SENDER, HEARTBEAT_SENDER})
```

Replace the sender validation check in `send()` (currently around line 83):

Old:
```python
        if sender != USER_SENDER and sender not in self._handlers:
            raise RoutingError(f"Sender '{sender}' is not registered")
```

New:
```python
        if sender not in _VIRTUAL_SENDERS and sender not in self._handlers:
            raise RoutingError(f"Sender '{sender}' is not registered")
```

Also in `send()`, update the talks_to bypass check (currently around line 91):

Old:
```python
        if sender != USER_SENDER:
```

New:
```python
        if sender not in _VIRTUAL_SENDERS:
```

- [ ] **Step 4: Run virtual sender tests**

Run: `python -m pytest tests/unit/comms/test_bus.py::TestVirtualSenders -v`
Expected: All 3 PASS

- [ ] **Step 5: Run full bus test suite**

Run: `python -m pytest tests/unit/comms/test_bus.py -v`
Expected: All PASS (existing tests unchanged -- USER_SENDER tests still work via the set)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/comms/bus.py tests/unit/comms/test_bus.py
git commit -m "refactor(bus): replace chained sender checks with _VIRTUAL_SENDERS set"
```

---

### Task 7: Bootstrap Integration

**Files:**
- Modify: `src/signalagent/runtime/bootstrap.py:1-4,144-149`
- Modify: `tests/unit/runtime/test_bootstrap.py`

- [ ] **Step 1: Write failing test for scheduler creation with triggers**

Add to `tests/unit/runtime/test_bootstrap.py` imports:

```python
from signalagent.core.models import (
    Profile,
    PrimeConfig,
    MicroAgentConfig,
    PluginsConfig,
    HooksConfig,
    HeartbeatConfig,
    ToolCallRequest,
)
from signalagent.heartbeat.models import ClockTrigger, TriggerGuards
```

Add fixture and test class:

```python
@pytest.fixture
def profile_with_heartbeat():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        heartbeat=HeartbeatConfig(
            clock_triggers=[
                ClockTrigger(
                    name="test-trigger",
                    cron="*/5 * * * *",
                    recipient="prime",
                    payload="tick",
                    guards=TriggerGuards(cooldown_seconds=60),
                ),
            ],
        ),
    )

@pytest.fixture
def profile_with_invalid_cron():
    return Profile(
        name="test",
        prime=PrimeConfig(identity="You are a test prime."),
        heartbeat=HeartbeatConfig(
            clock_triggers=[
                ClockTrigger(name="bad", cron="bad cron", recipient="prime"),
            ],
        ),
    )


class TestHeartbeatBootstrap:
    @pytest.mark.asyncio
    async def test_scheduler_not_created_without_triggers(self, tmp_path, config, profile_no_micros, monkeypatch):
        """No triggers in profile means no scheduler created."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        executor, bus, host = await bootstrap(tmp_path, config, profile_no_micros)
        # Bootstrap completes without error -- scheduler not created
        assert executor is not None

    @pytest.mark.asyncio
    async def test_scheduler_created_with_triggers(self, tmp_path, config, profile_with_heartbeat, monkeypatch):
        """Clock triggers in profile cause scheduler to be created and started."""
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=_make_ai_response("done"))
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        # Patch HeartbeatScheduler to verify it's created
        mock_scheduler_cls = MagicMock()
        mock_scheduler_instance = MagicMock()
        mock_scheduler_instance.start = AsyncMock()
        mock_scheduler_cls.return_value = mock_scheduler_instance
        monkeypatch.setattr("signalagent.runtime.bootstrap.HeartbeatScheduler", mock_scheduler_cls)

        executor, bus, host = await bootstrap(tmp_path, config, profile_with_heartbeat)

        mock_scheduler_cls.assert_called_once()
        mock_scheduler_instance.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_cron_fails_at_bootstrap(self, tmp_path, config, profile_with_invalid_cron, monkeypatch):
        """Invalid cron expression raises ValueError at bootstrap."""
        mock_ai = AsyncMock()
        monkeypatch.setattr("signalagent.runtime.bootstrap.AILayer", lambda config: mock_ai)

        with pytest.raises(ValueError, match="Invalid cron"):
            await bootstrap(tmp_path, config, profile_with_invalid_cron)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/runtime/test_bootstrap.py::TestHeartbeatBootstrap -v`
Expected: FAIL (bootstrap doesn't create scheduler yet)

- [ ] **Step 3: Implement bootstrap heartbeat integration**

In `src/signalagent/runtime/bootstrap.py`, add import after line 10:

```python
from signalagent.heartbeat.cron import validate_cron
from signalagent.heartbeat.scheduler import HeartbeatScheduler
```

After the session manager creation (line 146: `session_manager = ...`) and before `executor = ...`, add:

```python
    # Heartbeat scheduler -- validate and start after agents are registered
    for t in profile.heartbeat.clock_triggers:
        err = validate_cron(t.cron)
        if err:
            raise ValueError(f"Invalid cron in trigger '{t.name}': {err}")

    all_triggers = list(profile.heartbeat.clock_triggers) + list(profile.heartbeat.event_triggers)
    if all_triggers:
        scheduler = HeartbeatScheduler(bus=bus, triggers=all_triggers)
        await scheduler.start()
```

- [ ] **Step 4: Run heartbeat bootstrap tests**

Run: `python -m pytest tests/unit/runtime/test_bootstrap.py::TestHeartbeatBootstrap -v`
Expected: All 3 PASS

- [ ] **Step 5: Run full bootstrap test suite**

Run: `python -m pytest tests/unit/runtime/test_bootstrap.py -v`
Expected: All PASS (existing tests unaffected -- empty heartbeat config means no scheduler)

- [ ] **Step 6: Commit**

```bash
git add src/signalagent/runtime/bootstrap.py tests/unit/runtime/test_bootstrap.py
git commit -m "feat(heartbeat): wire scheduler into bootstrap -- validate cron, start background task"
```

---

### Task 8: Update Blank Profile + Full Test Suite

**Files:**
- Modify: `src/signalagent/profiles/blank.yaml`
- All test files

- [ ] **Step 1: Update blank.yaml**

The blank profile currently has no `heartbeat` section. Add it for schema consistency. Replace `src/signalagent/profiles/blank.yaml` with:

```yaml
name: blank
description: Empty Signal instance -- build your own
version: 1.0.0

prime:
  identity: >
    You are a helpful AI assistant. The user will define
    your purpose and add specialist agents over time.

micro_agents: []

plugins:
  available: [file_system, bash, web_search]

heartbeat:
  clock_triggers: []
  event_triggers: []
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS. No existing tests broken.

If any existing tests that construct `HeartbeatConfig()` with `condition_triggers` fail, remove the `condition_triggers` argument from those tests (it was removed from the model in Task 2).

- [ ] **Step 3: Run just the heartbeat tests as a focused check**

Run: `python -m pytest tests/unit/heartbeat/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/signalagent/profiles/blank.yaml
git commit -m "chore: update blank profile with typed heartbeat config"
```

- [ ] **Step 5: Run the full test suite one final time**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All PASS. This is the final verification.

---

### Task 9: Version Bump, CHANGELOG, Roadmap

**Files:**
- Modify: `VERSION`
- Modify: `CHANGELOG.md`
- Modify: `docs/dev/roadmap.md`

- [ ] **Step 1: Bump version**

Update `VERSION` from `0.8.0` to `0.9.0`.

- [ ] **Step 2: Update CHANGELOG.md**

Add a new section at the top (after the header, before `## [0.8.0]`):

```markdown
## [0.9.0] - 2026-04-02

### Added
- HeartbeatScheduler: in-process async trigger loop with 1-second tick interval
- ClockTrigger model with 5-field cron expression matching (ISO day-of-week)
- FileEventTrigger model with git-status polling and mtime fallback
- TriggerGuards: cooldown, max_fires, and consecutive error threshold
- FileChangeDetector: git status --porcelain diffing with silent baseline reset
- Pure-function cron matcher and validator (heartbeat/cron.py)
- HEARTBEAT_SENDER virtual sender constant
- Cron validation at bootstrap (fail-fast on invalid expressions)

### Changed
- HeartbeatConfig uses typed trigger models (ClockTrigger, FileEventTrigger) instead of list[dict]
- HeartbeatConfig.condition_triggers removed (deferred -- agents evaluate predicates on clock ticks)
- MessageBus uses _VIRTUAL_SENDERS set instead of chained sender checks
- Bootstrap creates and starts HeartbeatScheduler as background asyncio task when triggers are defined
```

- [ ] **Step 3: Update roadmap**

In `docs/dev/roadmap.md`, change Phase 7 row:

Old:
```
| 7 | Heartbeat Daemon | Planned | Autonomous triggers (cron, events, conditions) |
```

New:
```
| 7 | Heartbeat Daemon | Complete | In-process async scheduler, clock triggers (cron), file event triggers (git-status polling), safety guards |
```

- [ ] **Step 4: Commit**

```bash
git add VERSION CHANGELOG.md docs/dev/roadmap.md
git commit -m "chore: bump to 0.9.0, update CHANGELOG and roadmap for Phase 7"
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Trigger models | `heartbeat/models.py` | ~15 |
| 2 | HeartbeatConfig + HEARTBEAT_SENDER | `core/types.py`, `core/models.py` | ~6 |
| 3 | Cron matching | `heartbeat/cron.py` | ~21 |
| 4 | FileChangeDetector | `heartbeat/detector.py` | ~9 |
| 5 | HeartbeatScheduler | `heartbeat/scheduler.py` | ~15 |
| 6 | Virtual sender set | `comms/bus.py` | ~3 |
| 7 | Bootstrap integration | `runtime/bootstrap.py` | ~3 |
| 8 | Profile update + full suite | `profiles/blank.yaml` | Full regression |
| 9 | Version bump + docs | `VERSION`, `CHANGELOG.md`, `roadmap.md` | -- |
