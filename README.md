# Signal

An AI agent runtime framework -- one interface, many specialists, running continuously.

## What Signal Is

Signal gives you a single agent, Prime, that you talk to directly. Behind Prime sits a network of specialist micro-agents, each scoped to a specific skill or domain. A heartbeat daemon keeps the system alive between conversations, firing triggers on schedules and events. Profiles are YAML manifests that define what an instance becomes -- its identity, its agents, its capabilities.

## Current Status

**All 10 phases complete.** The system is functionally complete and containerized. See the [roadmap](docs/dev/roadmap.md) for the full phase history.

## Quickstart

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), an LLM API key (Anthropic recommended)

```bash
git clone https://github.com/forsonny/signal.git
cd signal
uv sync --dev
```

```bash
export ANTHROPIC_API_KEY=your-key
uv run signal init --profile blank
uv run signal talk "hello"
```

## Docker

```bash
# Build the image
docker build -t signal .

# First run (auto-initializes, then runs your command)
docker run -e ANTHROPIC_API_KEY=sk-... signal talk "hello"

# Persistent state with a named volume
docker run -v signal-data:/app/.signal -e ANTHROPIC_API_KEY=sk-... signal talk "hello"

# Multiple API keys via .env file
docker run -v signal-data:/app/.signal --env-file .env signal talk "hello"

# Interactive chat (requires -it for stdin)
docker run -it -v signal-data:/app/.signal --env-file .env signal chat

# Custom profile (manual init, then use)
docker run -v signal-data:/app/.signal signal init --profile devtools
docker run -v signal-data:/app/.signal --env-file .env signal talk "hello"
```

**Notes:**
- `signal chat` requires `docker run -it` (interactive + TTY) or the REPL exits immediately on EOF.
- The entrypoint auto-initializes with the `blank` profile on first run. For a different profile, run `init` manually first -- the entrypoint skips init when `/app/.signal` already exists.
- State (memory, sessions, config) lives in `/app/.signal`. Mount a volume to persist it across container restarts.

## Documentation

- [Installation](docs/user/installation.md)
- [Quickstart guide](docs/user/quickstart.md)
- [CLI reference](docs/user/cli-reference.md)
- [Configuration](docs/user/configuration.md)
- [Profiles](docs/user/profiles.md)

## License

Apache 2.0 -- see [LICENSE](LICENSE).
