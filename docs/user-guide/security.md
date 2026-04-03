# Security

**What you'll learn:**

- How declarative policies control tool access per agent
- How memory access scoping restricts what an agent can read
- What the audit trail records and where to find it
- How the PolicyHook enforces fail-closed behavior
- How to configure security policies in profiles

---

## Declarative policies

Security policies are allow-list rules defined per agent in the profile's `security` section. Each policy entry names an agent and declares what that agent is allowed to do.

```yaml
security:
  policies:
    - agent: code-reviewer
      allow_tools: [file_system]
      allow_memory_read: [prime, code-reviewer, shared]
    - agent: test-runner
      allow_tools: [bash]
      allow_memory_read: [test-runner]
```

Policies are evaluated by the `PolicyEngine`, which is a pure-logic rules evaluator with no I/O. It is shared by the PolicyHook (for tool access) and the PolicyMemoryReader (for memory scoping).

### Tool access rules

The `allow_tools` field lists which tools an agent may invoke. When the agent attempts a tool call, the PolicyEngine checks the tool name against this list.

| `allow_tools` value | Behavior                                      |
|---------------------|-----------------------------------------------|
| `null` (or omitted) | Unrestricted -- agent can use any tool        |
| `[]` (empty list)   | No tool access -- all tool calls are blocked  |
| `[file_system, bash]`| Only these tools are allowed                 |

The distinction between `null` and `[]` is important. Omitting `allow_tools` means "no restriction." Setting it to an empty list means "block everything."

### Decision outcomes

When the PolicyEngine evaluates a tool access request, it returns one of:

| Decision         | Rule tag             | Meaning                                      |
|------------------|----------------------|----------------------------------------------|
| Allowed          | `no_policy`          | No policy entry exists for this agent        |
| Allowed          | `no_tool_rules`      | Agent has a policy but `allow_tools` is null  |
| Allowed          | `allow_tools:{name}` | Tool name is in the allow list               |
| Denied           | `deny:tool:{name}`   | Tool name is not in the allow list           |

When no policy entry exists at all for an agent, access is allowed by default and a deduplicated warning is logged to the audit trail.

---

## Memory access scoping

The `allow_memory_read` field controls which agent scopes a given agent can see when searching memories.

```yaml
- agent: code-reviewer
  allow_memory_read: [prime, code-reviewer, shared]
```

| `allow_memory_read` value | Behavior                                          |
|---------------------------|---------------------------------------------------|
| `null` (or omitted)       | Unrestricted -- agent can read all memories       |
| `[]` (empty list)         | No memory access -- all results are filtered out  |
| `[prime, shared]`         | Only memories owned by `prime` or with type `shared` |

The keyword `shared` in the list matches memories with `type=shared` (the shared memory pool), not an agent named "shared."

### How filtering works

The `PolicyMemoryReader` wraps the memory engine and applies post-retrieval filtering:

1. The inner memory engine performs the search and returns results.
2. For each result, the reader checks whether the memory's owning agent (or type `shared`) is in the policy's `allow_memory_read` set.
3. Unauthorized memories are silently removed from the result set, and a `policy_denial` event is logged to the audit trail.
4. The filtered list is returned to the agent.

This means the agent never sees memories it is not authorized to read, and every denied access is recorded for audit purposes.

---

## Audit trail

All policy decisions and tool executions are recorded in a JSONL audit file at `.signal/data/security/audit.jsonl`. Each line is a structured JSON event.

### Event types

| Event type       | When logged                                              |
|------------------|----------------------------------------------------------|
| `tool_call`      | After every tool call completes (allowed or blocked)     |
| `policy_denial`  | When a tool call or memory read is denied by policy      |
| `warning`        | When an agent has no policy entry (once per agent per process) |

### Event structure

Each audit event contains:

```json
{
  "timestamp": "2026-04-01T14:30:00+00:00",
  "event_type": "policy_denial",
  "agent": "code-reviewer",
  "detail": {
    "tool": "bash",
    "rule": "deny:tool:bash"
  }
}
```

| Field        | Description                                               |
|--------------|-----------------------------------------------------------|
| `timestamp`  | ISO-8601 UTC timestamp                                    |
| `event_type` | Category: `tool_call`, `policy_denial`, or `warning`      |
| `agent`      | Name of the agent associated with the event               |
| `detail`     | Event-specific key-value data                             |

### Tool call events

Every tool execution (regardless of whether it was blocked) produces a `tool_call` event with:

```json
{
  "tool": "file_system",
  "duration_ms": 42,
  "error": null,
  "blocked_by_other": false
}
```

- `duration_ms`: Wall-clock time of the tool execution in milliseconds.
- `error`: Error message from the tool result, or `null` on success.
- `blocked_by_other`: `true` if a different hook (not the PolicyHook) blocked the call.

### Viewing the audit trail

The audit file is plain JSONL, readable with standard tools:

```bash
# Show all policy denials
cat .signal/data/security/audit.jsonl | python -m json.tool --no-ensure-ascii | grep -A5 policy_denial

# Count events by type
cat .signal/data/security/audit.jsonl | python -c "
import sys, json, collections
counts = collections.Counter(json.loads(line)['event_type'] for line in sys.stdin)
for k, v in counts.most_common(): print(f'{k}: {v}')
"
```

---

## Fail-closed behavior

The PolicyHook operates in **fail-closed** mode. This means:

- If the hook itself raises an unexpected exception during `before_tool_call`, the tool call is **blocked** (not allowed through).
- If the hook raises during `after_tool_call`, the error is logged but does not retroactively affect the tool result.

This is the opposite of fail-open hooks, where an exception allows the call to proceed. The fail-closed design ensures that a bug in the security layer cannot accidentally grant unauthorized access.

The `fail_closed` property on the PolicyHook is checked by both the `HookExecutor` and the `WorktreeProxy`, ensuring consistent enforcement regardless of whether the agent is operating in passthrough or isolated worktree mode.

---

## Configuring policies in profiles

### Basic example

Allow `code-reviewer` to use only `file_system`, and restrict its memory access to its own memories plus the shared pool:

```yaml
security:
  policies:
    - agent: code-reviewer
      allow_tools: [file_system]
      allow_memory_read: [code-reviewer, shared]
```

### Restricting a micro-agent to a single tool

```yaml
security:
  policies:
    - agent: test-runner
      allow_tools: [bash]
      allow_memory_read: [test-runner]
```

### Unrestricted agent (explicit)

Omit `allow_tools` and `allow_memory_read` (or set them to `null`) for full access. This is the default when no policy entry exists for an agent:

```yaml
security:
  policies:
    - agent: trusted-agent
      allow_tools: null
      allow_memory_read: null
```

### Blocking all tool access

Set `allow_tools` to an empty list:

```yaml
security:
  policies:
    - agent: read-only-agent
      allow_tools: []
      allow_memory_read: [shared]
```

### Multiple agents

```yaml
security:
  policies:
    - agent: code-reviewer
      allow_tools: [file_system]
      allow_memory_read: [prime, code-reviewer, shared]
    - agent: test-runner
      allow_tools: [bash]
      allow_memory_read: [test-runner]
    - agent: research-agent
      allow_tools: [web_search]
      allow_memory_read: [prime, shared]
```

---

## PolicyHook integration

The PolicyHook plugs into Signal's hook pipeline, which runs before and after every tool call. It integrates as follows:

1. **Before tool call:** The hook checks `PolicyEngine.check_tool_access(agent, tool_name)`. If denied, it returns a `ToolResult` with an error message (`"Policy denied: {tool_name}"`), which prevents the tool from executing. If allowed, it records the start time for duration tracking and returns `None` to let the call proceed.

2. **After tool call:** The hook logs a `tool_call` audit event with the tool name, execution duration, error status, and whether another hook blocked the call.

3. **No-policy warning:** If the agent has no policy entry at all, a deduplicated `warning` event is logged once per agent per process lifetime. The tool call is still allowed (fail-open for missing policies, fail-closed for hook errors).

The hook is activated by listing `policy` in the profile's hooks section and configuring the security policies:

```yaml
hooks:
  active: [policy]

security:
  policies:
    - agent: code-reviewer
      allow_tools: [file_system]
```

---

## Next steps

- [Profiles](profiles.md) -- full YAML schema for the `security` section
- [Memory](memory.md) -- how memory scoping interacts with `allow_memory_read`
- [Worktrees & Forks](worktrees-and-forks.md) -- policy enforcement in worktree-isolated execution
- [Core Concepts](concepts.md) -- the hook pipeline that PolicyHook plugs into
