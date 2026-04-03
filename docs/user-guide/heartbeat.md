# Heartbeat

**What you'll learn:**

- What the heartbeat scheduler is and how it works
- How to configure clock triggers with cron expressions
- How to configure file event triggers for change detection
- How trigger guards prevent runaway behavior
- How triggers fire agent actions through the message bus

---

## What the heartbeat is

The heartbeat is an in-process async scheduler that runs as a background task inside the Signal runtime. It ticks every second, evaluates each registered trigger, and dispatches messages into the MessageBus when conditions are met.

The heartbeat supports two trigger types:

- **Clock triggers** fire based on cron expressions (time-based scheduling).
- **File event triggers** fire when files change in a watched directory (polling-based detection).

Both types share a common set of safety guards that prevent runaway behavior. Triggers are configured in the `heartbeat` section of a profile.

---

## Clock triggers

A clock trigger fires when the current time matches a 5-field cron expression. Signal evaluates the expression against UTC time on every tick, with deduplication that ensures at most one fire per minute transition.

### Cron syntax

The cron expression uses five fields separated by whitespace:

```
minute  hour  day-of-month  month  day-of-week
```

| Field        | Range  | Note                                   |
|--------------|--------|----------------------------------------|
| minute       | 0--59  |                                        |
| hour         | 0--23  |                                        |
| day-of-month | 1--31  |                                        |
| month        | 1--12  |                                        |
| day-of-week  | 0--6   | ISO convention: Monday=0, Sunday=6     |

Supported syntax per field:

| Syntax   | Meaning                           | Example      |
|----------|-----------------------------------|--------------|
| `*`      | Any value                         | `*`          |
| `N`      | Exact value                       | `30`         |
| `N-M`    | Range (inclusive)                  | `9-17`       |
| `*/N`    | Step from minimum                 | `*/15`       |
| `N-M/S`  | Step within range                 | `0-30/10`    |
| `N,M,O`  | Comma-separated list              | `1,15,30`    |

### Configuration

```yaml
heartbeat:
  clock_triggers:
    - name: daily-standup
      cron: "0 9 * * 0-4"
      recipient: prime
      payload: "Run the daily standup routine."
      guards:
        cooldown_seconds: 60
        max_fires: 0
        error_threshold: 3
```

| Field       | Type   | Default | Description                                         |
|-------------|--------|---------|-----------------------------------------------------|
| `name`      | string | required| Unique trigger identifier                           |
| `cron`      | string | required| 5-field cron expression                             |
| `recipient` | string | required| Agent name to receive the trigger message           |
| `payload`   | string | `""`    | Message content sent when the trigger fires         |
| `guards`    | object | defaults| Safety guards (see [Trigger guards](#trigger-guards))|

### Examples

Run every weekday at 9:00 AM UTC:

```yaml
- name: weekday-morning
  cron: "0 9 * * 0-4"
  recipient: prime
  payload: "Good morning. Check for new issues."
```

Run every 15 minutes:

```yaml
- name: frequent-check
  cron: "*/15 * * * *"
  recipient: monitor-agent
  payload: "Perform health check."
```

Run every Sunday at 3:00 AM UTC (default MemoryKeeper schedule):

```yaml
- name: memory-maintenance
  cron: "0 3 * * 6"
  recipient: memory-keeper
  payload: "Run maintenance pass."
```

---

## File event triggers

A file event trigger watches a directory for changes by polling at a configurable interval. It uses git status when the directory is a git repository and falls back to mtime-based scanning otherwise.

When the trigger fires, the `{changed_files}` placeholder in the payload is replaced with a comma-separated list of changed file paths.

### Configuration

```yaml
heartbeat:
  event_triggers:
    - name: src-watcher
      path: "./src"
      interval_seconds: 30
      recipient: code-reviewer
      payload: "Files changed: {changed_files}"
      guards:
        cooldown_seconds: 120
        max_fires: 0
        error_threshold: 3
```

| Field              | Type   | Default | Description                                              |
|--------------------|--------|---------|----------------------------------------------------------|
| `name`             | string | required| Unique trigger identifier                                |
| `path`             | string | `"."`   | Directory to watch for changes                           |
| `interval_seconds` | int    | `30`    | Seconds between polling checks (minimum: 5)              |
| `recipient`        | string | required| Agent name to receive the trigger message                |
| `payload`          | string | `""`    | Message content; `{changed_files}` is replaced on fire   |
| `guards`           | object | defaults| Safety guards (see [Trigger guards](#trigger-guards))    |

### Detection modes

- **Git mode:** When a `.git` directory exists in the watched path, the detector runs `git status --porcelain` and parses the output. This captures staged, unstaged, and untracked file changes.
- **Mtime mode:** When git is unavailable, the detector walks the directory tree and compares file modification times against a baseline from the previous check. New, modified, and deleted files are all detected. Directories listed in the project's ignore list (e.g., `__pycache__`, `.git`) are skipped.

### Examples

Watch the docs directory every 60 seconds:

```yaml
- name: docs-watcher
  path: "./docs"
  interval_seconds: 60
  recipient: docs-agent
  payload: "Documentation files changed: {changed_files}"
```

Watch the project root with a short interval:

```yaml
- name: fast-watcher
  path: "."
  interval_seconds: 10
  recipient: prime
  payload: "Changes detected: {changed_files}"
  guards:
    cooldown_seconds: 30
```

---

## Trigger guards

Both clock and file event triggers share a set of safety guards that prevent runaway behavior.

```yaml
guards:
  cooldown_seconds: 60
  max_fires: 0
  error_threshold: 3
```

| Field              | Type | Default | Description                                              |
|--------------------|------|---------|----------------------------------------------------------|
| `cooldown_seconds` | int  | `60`    | Minimum seconds between consecutive fires (0 = no cooldown) |
| `max_fires`        | int  | `0`     | Maximum total fires before the trigger auto-disables (0 = unlimited) |
| `error_threshold`  | int  | `3`     | Consecutive dispatch errors before the trigger auto-disables |

### How guards work

1. **Cooldown:** After a trigger fires, it will not fire again until `cooldown_seconds` have elapsed, even if the trigger condition matches on every tick. This prevents rapid-fire dispatch during burst conditions.

2. **Max fires:** When `max_fires` is set to a positive integer, the trigger automatically disables itself after reaching that count. This is useful for one-shot or limited-run triggers. Set to `0` for unlimited fires.

3. **Error threshold:** If `error_threshold` consecutive dispatch errors occur (e.g., the target agent is unreachable), the trigger auto-disables with a warning log. This prevents a broken trigger from generating unbounded error noise.

---

## How triggers fire agents

When a trigger condition matches and guards allow it, the scheduler sends a `Message` through the MessageBus:

1. The scheduler constructs a `Message` with `type=trigger`, `sender=heartbeat`, and `recipient` set to the trigger's target agent.
2. For file event triggers, `{changed_files}` in the payload is replaced with the actual file list.
3. The message is sent via `bus.send()`, which routes it to the target agent.
4. The target agent handles the message like any other incoming message -- the Prime agent or a micro-agent processes the payload text through its normal task handling.
5. On successful dispatch, the trigger state is updated: `fire_count` increments, `last_fired` is set to the current time, and `consecutive_errors` resets to zero.

Trigger state (fire count, last-fired time, error count) is held in memory and resets when the process restarts. There is no persistent trigger state between Signal invocations.

---

## Next steps

- [Profiles](profiles.md) -- full YAML schema for heartbeat and all other profile sections
- [Memory](memory.md) -- how the MemoryKeeper agent uses heartbeat scheduling for maintenance
- [Security](security.md) -- policy enforcement for agents triggered by the heartbeat
- [Core Concepts](concepts.md) -- the message bus that heartbeat dispatches into
