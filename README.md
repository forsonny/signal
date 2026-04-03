# Signal

AI agent runtime framework -- one interface, many specialists, running continuously.

## What Signal Does

- **One interface, many specialists** -- talk to Prime, it routes to the right micro-agent
- **Persistent memory** -- agents learn and remember across conversations
- **Autonomous heartbeat** -- triggers fire on schedules and events without user prompts
- **Profile-driven** -- YAML manifests define what an instance becomes
- **Extensible** -- add agents, tools, and hooks without modifying core code

## Quickstart

```bash
git clone https://github.com/forsonny/signal.git
cd signal
uv sync --dev
export ANTHROPIC_API_KEY=your-key
uv run signal init --profile blank
uv run signal talk "hello"
```

## Documentation

Full documentation: [docs/](docs/index.md)

- [Installation](docs/getting-started/installation.md)
- [Quickstart](docs/getting-started/quickstart.md)
- [CLI Reference](docs/user-guide/cli-reference.md)
- [Architecture](docs/developer-guide/architecture.md)
- [API Reference](docs/api/index.md)

## License

Apache 2.0 -- see [LICENSE](LICENSE).
