# Contributing

## Development Setup

```bash
git clone <repo-url>
cd signal
uv sync --dev
uv run pytest
```

All tests should pass on a clean checkout. If they do not, that is a bug -- open an issue before doing anything else.

Python version: 3.11 or later. `uv` handles the virtual environment. Do not use `pip` or `venv` directly.

---

## Running Tests

```bash
# Run the full suite
uv run pytest

# Verbose output (shows each test name)
uv run pytest -v

# Quiet output (dots only)
uv run pytest -q

# Stop on first failure
uv run pytest -x

# Run a specific directory
uv run pytest tests/unit/core/

# Run tests matching a keyword
uv run pytest -k "config"
```

---

## Code Style

There is no formatter or linter enforced by CI yet. Follow the patterns already in the codebase:

- 4-space indentation, no tabs
- Type annotations on all function signatures
- Docstrings on public classes and functions (one-line summary is sufficient)
- Imports ordered: stdlib, third-party, local -- with a blank line between groups
- No wildcard imports (`from module import *`)

When in doubt, match the existing style in the file you are editing.

---

## Commit Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add memory retrieval to executor
fix: handle missing profile gracefully in init_cmd
chore: update litellm to 1.x
docs: add contributing guide
refactor: extract message construction into helper
test: add edge cases for config load
```

Keep the subject line under 72 characters. Add a body if the change needs explanation. Reference issue numbers when relevant (`closes #42`).

---

## TDD Workflow

Signal is developed test-first. The sequence for every change:

1. Write the test. It must fail (`uv run pytest -x -k "your_test_name"`).
2. Write the minimum implementation to make it pass.
3. Verify the test passes and no other tests regressed.
4. Commit both the test and the implementation together.

Do not commit implementations without tests. Do not commit failing tests unless they are explicitly marked `xfail` with a reason.

---

## Key Rules

**All Pydantic models use `extra="forbid"`.**
Unknown fields raise a `ValidationError` at parse time. This is intentional. If you add a field to a YAML config, add it to the model first.

**All async code uses `asyncio`. No threads.**
Do not use `threading`, `concurrent.futures.ThreadPoolExecutor`, or `asyncio.to_thread` for new async work. If you need to bridge sync code, document why and keep it isolated.

**Error boundaries: agent execution must never crash the runtime.**
Any exception raised inside an agent's execution path must be caught and returned as a structured error result. The runtime process must keep running. If you add a new execution path, wrap it.

**Protocol-based DI: use Protocols, not concrete imports, for cross-module dependencies.**
If module A needs to call module B, define a `typing.Protocol` in A describing what it needs, and have B satisfy it. A does not import B directly. This keeps the dependency graph clean and tests easy to write.

**YAGNI: only build what the current phase requires.**
Do not add abstractions, extension points, or placeholder modules for future phases. Build the thing the current phase needs. Future phases will define their own requirements.
