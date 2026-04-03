# Sessions

**What you'll learn:**

- What sessions are and how they persist conversations
- How to start and use interactive chat mode
- REPL commands available during a chat session
- How to list and resume previous sessions
- How conversation history is injected into agent prompts

---

## What sessions are

A session is a persisted multi-turn conversation between the user and the Prime agent. Each session is stored as a single JSONL file (one JSON line per turn) in `.signal/data/sessions/`. Sessions are append-only: every user message and assistant response is written immediately, so conversation state survives process exits and crashes.

A session file looks like this:

```
.signal/data/sessions/ses_a1b2c3d4.jsonl
```

Each line is a serialized `Turn` object:

```json
{"role":"user","content":"Explain Python decorators","timestamp":"2026-04-01T14:30:00+00:00"}
{"role":"assistant","content":"A decorator is a function that...","timestamp":"2026-04-01T14:30:02+00:00"}
```

Session IDs follow the format `ses_` plus 8 hex characters (e.g., `ses_a1b2c3d4`).

---

## Interactive chat mode

Start a new interactive conversation:

```bash
signal chat
```

This creates a new session, prints its ID, and drops you into a REPL where you type messages and receive responses from the Prime agent.

```
New session: ses_a1b2c3d4
Type /quit to exit, /history to show conversation, /session to show ID

you> What files are in the project?
The project contains the following files...

you> Summarize the main module.
The main module handles...

you>
```

The session is saved automatically -- each user message and assistant response is appended to the JSONL file immediately after the exchange completes.

---

## REPL commands

Inside the chat REPL, commands start with `/`:

| Command    | Description                                      |
|------------|--------------------------------------------------|
| `/quit`    | Exit the chat session                            |
| `/exit`    | Exit the chat session (alias for `/quit`)        |
| `/history` | Print the full conversation history              |
| `/session` | Print the current session ID                     |

Any unrecognized `/` command prints an "Unknown command" message. Regular text (without a leading `/`) is sent to the Prime agent as a user message.

You can also exit with `Ctrl+C` or `Ctrl+D` (EOF). In all cases, the session ID is printed on exit so you can resume later.

---

## Listing sessions

View recent sessions sorted by most recent first:

```bash
signal sessions list
```

Output is a table with four columns:

```
           Recent Sessions
 ID              Created           Preview           Turns
 ses_a1b2c3d4    2026-04-01 14:30  Explain Python...     4
 ses_e5f6a7b8    2026-03-28 09:15  How do I set up...    12
```

| Option         | Description                               |
|----------------|-------------------------------------------|
| `--limit`, `-n`| Maximum sessions to display (default: 20) |

Example with a custom limit:

```bash
signal sessions list --limit 5
```

---

## Resuming a session

To continue a previous conversation, pass the session ID with `--session`:

```bash
signal chat --session ses_a1b2c3d4
```

When resuming, the CLI loads the session file and displays the last few turns for context:

```
Resuming session ses_a1b2c3d4
  you: Explain Python decorators
  agent: A decorator is a function that...
  you: Show me an example
  agent: Here is an example using @wraps...

you>
```

New messages are appended to the same JSONL file, continuing the conversation seamlessly.

---

## How conversation history is injected

When a session ID is active (either from `signal chat` or passed programmatically), the Executor loads all turns from the session file and attaches them to the outgoing message as a `history` field. This history is a list of `{"role": "...", "content": "..."}` dicts that the Prime agent receives alongside the new user message.

The flow works like this:

1. The Executor calls `SessionManager.load(session_id)` to read all prior turns.
2. The turns are converted to a list of role/content dicts and set on `Message.history`.
3. The message (with full history) is sent to the Prime agent via the MessageBus.
4. The Prime agent's AI layer includes the history as conversation context in the LLM prompt.
5. After the response arrives, both the user turn and assistant turn are appended to the session file.

This means conversation context is rebuilt from disk on every invocation. There is no in-memory session cache -- the JSONL file is the single source of truth. Corrupt lines in the session file are logged and skipped during loading, so a single malformed line does not break the entire session.

---

## Next steps

- [CLI Reference](cli-reference.md) -- full list of all `signal` commands
- [Core Concepts](concepts.md) -- how Prime, micro-agents, and the message bus interact
- [Profiles](profiles.md) -- configuring the Prime agent's identity and behavior
