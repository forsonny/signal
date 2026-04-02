# Phase 7: Heartbeat Daemon Design

## Overview

The heartbeat is an in-process async scheduler that fires autonomous triggers into the existing MessageBus. It reads trigger definitions from the profile at bootstrap, runs an asyncio tick loop, and dispatches `Message(type=TRIGGER)` to target agents when triggers activate. Agents receive triggers through the same `_handle()` path as user tasks -- no new code path in PrimeAgent.

**Scope:** Clock triggers (cron-based) and file event triggers (polling-based). Condition triggers are deferred -- agents evaluate predicates themselves on clock ticks. Dynamic trigger registration and CLI management are future features that layer on top of the static trigger system built here.

**Execution model:** Single-process, in-process scheduler. The heartbeat fires while the Python process is running (`signal chat`, future `signal daemon`). Always-on autonomy requires the Docker/daemon infrastructure from Phase 10.

---

## Architecture

### Components

| Component | File | Responsibility |
|-----------|------|---------------|
| Trigger models | `heartbeat/models.py` | `TriggerGuards`, `ClockTrigger`, `FileEventTrigger`, `TriggerState` |
| Cron matcher | `heartbeat/cron.py` | `cron_match()`, `validate_cron()` -- pure functions |
| File detector | `heartbeat/detector.py` | `FileChangeDetector` -- git status / mtime polling |
| Scheduler | `heartbeat/scheduler.py` | `HeartbeatScheduler` -- async tick loop + dispatch |

### Message Flow

```
HeartbeatScheduler tick (every 1 second)
  -> evaluate each trigger: enabled? max_fires? cooldown? type-specific check?
  -> bus.send(Message(type=TRIGGER, sender="heartbeat", recipient=target, content=payload))
  -> PrimeAgent._handle() receives trigger via existing routing path
  -> Prime routes to micro-agent or handles directly (same as TASK)
  -> scheduler updates TriggerState (fire_count++, or consecutive_errors++)
```

### Integration Points

- **core/types.py:** `HEARTBEAT_SENDER = "heartbeat"` constant
- **comms/bus.py:** `_VIRTUAL_SENDERS = {USER_SENDER, HEARTBEAT_SENDER}` -- single set membership check replaces chained `!=` comparisons
- **runtime/bootstrap.py:** Creates scheduler after agent registration, validates cron, starts background task. Return type unchanged.
- **PrimeAgent:** Zero changes. Triggers flow through existing `_handle()` with `history=None`.

---

## Trigger Models

### TriggerGuards

Shared safety configuration for all trigger types.

```python
class TriggerGuards(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cooldown_seconds: int = Field(default=60, ge=0)
    max_fires: int = Field(default=0, ge=0)        # 0 = unlimited
    error_threshold: int = Field(default=3, ge=1)   # consecutive failures before disable
```

### ClockTrigger

Time-based trigger using standard 5-field cron expressions.

```python
class ClockTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    cron: str                    # "*/5 * * * *" (minute hour dom month dow)
    recipient: str               # target agent name
    payload: str = ""            # content sent in the TRIGGER message
    guards: TriggerGuards = Field(default_factory=TriggerGuards)
```

### FileEventTrigger

Polling-based file change trigger. Implemented as a specialized clock trigger that checks for file changes on each interval.

```python
class FileEventTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path: str = "."              # watched path (relative to instance workspace)
    interval_seconds: int = Field(default=30, ge=5)
    recipient: str
    payload: str = ""            # {changed_files} replaced via str.replace()
    guards: TriggerGuards = Field(default_factory=TriggerGuards)
```

Payload substitution uses `payload.replace("{changed_files}", file_list)` -- explicit replacement, not `str.format()`. Safe against filenames containing braces.

### TriggerState

Runtime-only mutable state per trigger. Not persisted -- resets on process restart. This is a deliberate design decision: fire_count, consecutive_errors, and last_fired all start fresh on restart.

```python
@dataclass
class TriggerState:
    last_fired: datetime | None = None
    fire_count: int = 0
    consecutive_errors: int = 0
    enabled: bool = True
    last_matched_minute: datetime | None = None  # cron dedup (clock triggers only)
```

### HeartbeatConfig (updated)

Replaces untyped `list[dict]` fields with typed trigger models. `condition_triggers` removed.

```python
class HeartbeatConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clock_triggers: list[ClockTrigger] = Field(default_factory=list)
    event_triggers: list[FileEventTrigger] = Field(default_factory=list)
```

### Profile YAML Example

```yaml
heartbeat:
  clock_triggers:
    - name: memory-consolidation
      cron: "0 * * * *"
      recipient: prime
      payload: "Review recent memories and consolidate duplicates."
      guards:
        cooldown_seconds: 3600
        max_fires: 0
        error_threshold: 3

  event_triggers:
    - name: code-review-on-change
      path: "."
      interval_seconds: 30
      recipient: prime
      payload: "Files changed: {changed_files}. Review the changes."
      guards:
        cooldown_seconds: 120
        max_fires: 50
        error_threshold: 5
```

---

## Cron Matching

Pure function in `heartbeat/cron.py`.

### cron_match(expression, dt) -> bool

Checks if a datetime matches a 5-field cron expression (minute, hour, day-of-month, month, day-of-week).

**Supported syntax:**
- `*` -- any value
- `N` -- exact value
- `N-M` -- range (inclusive)
- `*/N` -- step from 0
- `N,M,O` -- comma-separated list
- Combinations: `1-5,15,30` -- union of range and literals

**Day-of-week convention:** ISO 8601 (Monday=0, Sunday=6), matching Python's `datetime.weekday()`.

**Implementation:** Each field is parsed into a `set[int]` of matching values. Match is `dt.minute in minute_set and dt.hour in hour_set and ...` -- all five fields must match.

### validate_cron(expression) -> str | None

Returns an error message if the expression is malformed (wrong field count, out-of-range values, bad syntax). Returns `None` if valid. Called at bootstrap (fail fast, not at first tick).

**Field ranges:**
- Minute: 0-59
- Hour: 0-23
- Day-of-month: 1-31
- Month: 1-12
- Day-of-week: 0-6

---

## FileChangeDetector

Infrastructure code in `heartbeat/detector.py`. Calls `subprocess.run()` directly -- not through the tool/hook pipeline. This is scheduler-level infrastructure, not an agent action.

### API

Single method: `check() -> list[str]`

Returns the current dirty file set if it changed since the last check. Returns empty list if nothing changed. Resets internal state after returning changes.

**Semantics:**
- Runs `git status --porcelain`, parses into `current: set[str]`
- Compares `current` against `self._last_seen`
- If different AND current is non-empty: update `_last_seen`, return `list(current)`
- If different AND current is empty: update `_last_seen` silently, return `[]`
- If identical: return `[]`

Fires when the dirty state changes and there are dirty files. Stays quiet when the dirty set is stable. Stays quiet when everything is clean.

### Git Detection

On first `check()`, tests `(self._path / ".git").is_dir()`. Caches result in `_is_git`. Does not re-check -- if `git init` happens after scheduler starts, detector stays in mtime mode.

### Git Mode

`subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=self._path, timeout=10)`

Parses porcelain output: each line's `[3:]` strip is a file path.

### Non-Git Fallback (mtime)

Walks `self._path` recursively, collects `{relative_path: mtime}`. Compares against stored baseline. Skips `IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".signal"}`.

### Error Handling

If `subprocess.run()` fails (git not installed, timeout, non-zero exit), logs warning and returns empty list. Detection failure does not count against the trigger's `consecutive_errors` -- that counter is for dispatch failures only.

---

## HeartbeatScheduler

The core async loop in `heartbeat/scheduler.py`.

### Lifecycle

```python
class HeartbeatScheduler:
    def __init__(self, bus: MessageBus, triggers: list[ClockTrigger | FileEventTrigger]) -> None
    async def start(self) -> None    # creates background asyncio.Task
    async def stop(self) -> None     # cancels task, suppresses CancelledError
```

### Tick Loop

Ticks every 1 second (`TICK_INTERVAL_SECONDS = 1`). On each tick:

1. Get current time
2. For each trigger:
   - Skip if `not state.enabled`
   - Check guards and type-specific condition via `_should_fire()`
   - If should fire, dispatch via `_dispatch()`

### Guard Evaluation (_should_fire)

Order:
1. **max_fires** -- if `max_fires > 0 and state.fire_count >= max_fires`, disable trigger, return False
2. **cooldown** -- if `state.last_fired` and elapsed < `cooldown_seconds`, return False
3. **Type-specific:**
   - **ClockTrigger:** Check `last_matched_minute` -- if current minute == last_matched_minute, skip (cron dedup). Otherwise evaluate `cron_match()`. If matches, update `last_matched_minute`.
   - **FileEventTrigger:** Check if `interval_seconds` elapsed since last check. If yes, call `detector.check()`. Store result in `_pending_changes[trigger.name]`. Return True if non-empty.

### Dispatch (_dispatch)

```python
async def _dispatch(self, trigger, state, now):
    content = trigger.payload
    if isinstance(trigger, FileEventTrigger):
        file_list = ", ".join(self._pending_changes[trigger.name])
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
        state.consecutive_errors += 1
        if state.consecutive_errors >= trigger.guards.error_threshold:
            state.enabled = False
            logger.warning("Trigger '%s' disabled after %d consecutive errors",
                          trigger.name, state.consecutive_errors)
```

---

## Bootstrap Integration

### Changes to bootstrap()

After agent registration, before creating the executor:

```python
# Validate cron expressions (fail fast)
for t in profile.heartbeat.clock_triggers:
    err = validate_cron(t.cron)
    if err:
        raise ValueError(f"Invalid cron in trigger '{t.name}': {err}")

# Create and start scheduler if triggers exist
all_triggers = profile.heartbeat.clock_triggers + profile.heartbeat.event_triggers
if all_triggers:
    scheduler = HeartbeatScheduler(bus=bus, triggers=all_triggers)
    await scheduler.start()  # background asyncio.Task, fire-and-forget
```

- Scheduler created only when triggers are defined
- Created after agents are registered so recipients exist on bus
- Started as fire-and-forget background task
- Return type unchanged: `tuple[Executor, MessageBus, AgentHost]`

### Changes to bus.py

```python
from signalagent.core.types import HEARTBEAT_SENDER, USER_SENDER

_VIRTUAL_SENDERS = {USER_SENDER, HEARTBEAT_SENDER}

# In send():
if sender not in _VIRTUAL_SENDERS and sender not in self._handlers:
    raise RoutingError(f"Sender '{sender}' is not registered")
```

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/signalagent/heartbeat/__init__.py` | Package init |
| `src/signalagent/heartbeat/models.py` | `TriggerGuards`, `ClockTrigger`, `FileEventTrigger`, `TriggerState` |
| `src/signalagent/heartbeat/cron.py` | `cron_match()`, `validate_cron()` |
| `src/signalagent/heartbeat/detector.py` | `FileChangeDetector` |
| `src/signalagent/heartbeat/scheduler.py` | `HeartbeatScheduler` |
| `tests/unit/heartbeat/test_models.py` | Trigger model validation |
| `tests/unit/heartbeat/test_cron.py` | Cron matching |
| `tests/unit/heartbeat/test_detector.py` | File change detection |
| `tests/unit/heartbeat/test_scheduler.py` | Scheduler tick/dispatch/guards |

### Modified Files

| File | Change |
|------|--------|
| `src/signalagent/core/types.py` | Add `HEARTBEAT_SENDER` constant |
| `src/signalagent/core/models.py` | Replace `HeartbeatConfig` dict fields with typed triggers, remove `condition_triggers` |
| `src/signalagent/comms/bus.py` | `_VIRTUAL_SENDERS` set, single membership check |
| `src/signalagent/runtime/bootstrap.py` | Create scheduler, validate cron, start background task |
| `src/signalagent/profiles/builtins/blank.yaml` | Update heartbeat section to match new schema |

---

## Done-When Criteria

1. `ClockTrigger` and `FileEventTrigger` models validate with `extra="forbid"` and enforce field constraints
2. `TriggerGuards` defaults: `cooldown_seconds=60`, `max_fires=0` (unlimited), `error_threshold=3`
3. `HeartbeatConfig` uses typed trigger lists, `condition_triggers` removed
4. `cron_match()` handles `*`, exact, range, step, comma-list, and combinations
5. `validate_cron()` rejects malformed expressions and returns descriptive error
6. Day-of-week uses ISO convention (Monday=0, Sunday=6) matching `datetime.weekday()`
7. `FileChangeDetector.check()` returns current dirty set if changed since last check, empty list if unchanged; dirty-but-empty resets silently
8. Git mode uses `subprocess.run()` directly (infrastructure, not tool pipeline)
9. Non-git fallback uses mtime scanning with `IGNORE_DIRS` exclusion set
10. Detection failure (subprocess error, timeout) logs warning and returns empty list -- does not count against error threshold
11. `HeartbeatScheduler` ticks every 1 second, evaluates triggers per tick
12. Clock triggers track `last_matched_minute` -- cron evaluated once per minute transition regardless of cooldown
13. Guard evaluation order: enabled -> max_fires -> cooldown -> type-specific check
14. Dispatch sends `Message(type=TRIGGER, sender=HEARTBEAT_SENDER, recipient=target, metadata={"trigger_name": name})`
15. Dispatch success: `fire_count++`, `consecutive_errors=0`, `last_fired=now`
16. Dispatch failure: `consecutive_errors++`, disable trigger when threshold reached
17. File event payload uses `payload.replace("{changed_files}", file_list)` -- no format-string substitution
18. `HEARTBEAT_SENDER` constant in `core/types.py`
19. `_VIRTUAL_SENDERS = {USER_SENDER, HEARTBEAT_SENDER}` in `bus.py`, single set membership check
20. Bootstrap validates all cron expressions at startup (fail fast)
21. Scheduler created only when triggers exist, started after agent registration, fire-and-forget background task
22. Bootstrap return type unchanged: `tuple[Executor, MessageBus, AgentHost]`
23. Triggers route through existing `PrimeAgent._handle()` -- no new code path, no special TRIGGER case
24. Triggers have no conversation history (autonomous, not session-linked)
25. All existing tests continue to pass (no breaking changes)
26. `TriggerState` is runtime-only (not persisted) -- resets on process restart
