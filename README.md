# Signal

An AI agent runtime framework -- one interface, many specialists, running continuously.

## What Signal Is

Signal gives you a single agent, Prime, that you talk to directly. Behind Prime sits a network of specialist micro-agents, each scoped to a specific skill or domain. A heartbeat daemon keeps the system alive between conversations, firing triggers on schedules and events. Profiles are YAML manifests that define what an instance becomes -- its identity, its agents, its capabilities.

## Current Status

**Phase 1 of 10 complete.** The minimal skeleton is in place: `signal init` and `signal talk` work end-to-end. No memory, no heartbeat, no sessions yet -- just the foundation everything else builds on.

See the [roadmap](docs/superpowers/plans/2026-03-31-phase1-skeleton.md) for what is coming.

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

MIT
