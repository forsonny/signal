# Signal

An AI agent runtime framework -- one interface, many specialists, running continuously.

## What Signal Is

Signal gives you a single agent, Prime, that you talk to directly. Behind Prime sits a network of specialist micro-agents, each scoped to a specific skill or domain. A heartbeat daemon keeps the system alive between conversations, firing triggers on schedules and events. Profiles are YAML manifests that define what an instance becomes -- its identity, its agents, its capabilities.

## Current Status

**Phase 4a of 10 complete.** Agents can now call tools via an agentic loop -- the runner calls AI, executes tool calls, feeds results back, and repeats until the task is complete or the iteration limit is reached. The first built-in tool is `file_system` (read/write/list, scoped to workspace). Two-tier iteration limits (global ceiling + per-agent config) prevent runaway loops. Prime still routes to specialist micro-agents via the message bus.

See the [roadmap](docs/dev/roadmap.md) for what is coming.

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

## Documentation

- [Installation](docs/user/installation.md)
- [Quickstart guide](docs/user/quickstart.md)
- [CLI reference](docs/user/cli-reference.md)
- [Configuration](docs/user/configuration.md)
- [Profiles](docs/user/profiles.md)

## License

Apache 2.0 -- see [LICENSE](LICENSE).
