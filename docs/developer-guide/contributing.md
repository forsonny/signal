# Contributing

## What you'll learn

- How to set up a local development environment for Signal
- How to run the test suite (full, filtered, single test)
- Code style conventions and architectural rules
- The TDD workflow used in this project
- Commit message format (Conventional Commits)

---

## Development setup

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) (dependency management)
- Git

### Clone and install

```bash
git clone https://github.com/forsonny/signal.git
cd signal
uv sync --all-groups
```

`uv sync --all-groups` installs both the `dev` and `docs` dependency
groups. If you only need to run tests:

```bash
uv sync --group dev
```

### Verify the installation

```bash
uv run signal --help
uv run pytest --co -q    # list collected tests without running them
```

---

## Running tests

### Full suite

```bash
uv run pytest
```

### Single file

```bash
uv run pytest tests/unit/runtime/test_runner.py
```

### Single test by name

```bash
uv run pytest tests/unit/runtime/test_runner.py::TestRunnerWithTools::test_single_tool_call_then_final
```

### Filter by keyword

```bash
uv run pytest -k "routing"
```

### Verbose output

```bash
uv run pytest -v
```

### Show print output

```bash
uv run pytest -s
```

All async tests run under `asyncio_mode = "auto"` (configured in
`pyproject.toml`), so `@pytest.mark.asyncio` is handled automatically.

---

## Code style

### Type annotations

Every function signature has full type annotations. Use `from __future__
import annotations` for deferred evaluation. Prefer `X | None` over
`Optional[X]`.

```python
from __future__ import annotations

async def search(
    self,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[Memory]:
    ...
```

### Pydantic strict mode

All Pydantic models use `ConfigDict(extra="forbid")`. This catches
typos and unexpected fields at construction time:

```python
class MicroAgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique agent name.")
    skill: str = Field(description="One-line skill description.")
```

### Async only

All I/O-touching code must be async. Exceptions: `SessionManager` (sync
file I/O where latency is negligible), `MemoryStorage` (single-file
reads), `WorktreeManager` (subprocess calls).

### Docstrings

Use Google-style docstrings on all public classes, methods, and functions:

```python
async def store(self, memory: Memory) -> Memory:
    """Write memory to disk, then upsert index, then embed.

    File-first ordering: if index or embedding fails, the file is
    still on disk and rebuild_index()/rebuild_embeddings() can recover.

    Args:
        memory: Memory object to persist.

    Returns:
        The same Memory instance (unchanged).
    """
```

### Import ordering

1. Standard library
2. Third-party packages (`pydantic`, `litellm`, etc.)
3. Internal imports (`signalagent.*`)

Use `from __future__ import annotations` as the first import in every
module.

---

## Architectural rules

### Error boundaries

Every layer must catch its own exceptions and provide meaningful
fallback behavior. The runner catches tool errors and feeds them back
to the LLM. The executor catches bus/agent errors and returns
`ExecutorResult(error=...)`. Never let an exception propagate to a
layer that does not know how to handle it.

### Protocol-based dependency injection

Agents depend on protocols (`AILayerProtocol`, `RunnerProtocol`, etc.),
never on concrete classes. Bootstrap wires the concrete implementations.
Tests inject mocks. No monkey-patching, no `@patch` on module-level
imports.

### YAGNI

Do not add abstractions, interfaces, or features that are not required
by the current implementation. If a future need is anticipated, leave a
comment -- do not write the code.

### No circular imports

The dependency graph flows strictly downward: `cli -> runtime -> agents
-> tools/hooks/memory -> ai -> core`. If you find yourself importing
upward, restructure.

---

## TDD workflow

This project follows a strict test-driven development cycle:

### 1. Write the test first

Write a failing test that defines the expected behavior:

```python
class TestMyFeature:
    @pytest.mark.asyncio
    async def test_expected_behavior(self):
        # Arrange
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value=...)

        # Act
        result = await my_function(ai=mock_ai)

        # Assert
        assert result.content == "expected"
```

### 2. Minimum implementation

Write the minimum code that makes the test pass. Resist the urge to
add extra functionality.

### 3. Verify

```bash
uv run pytest tests/unit/path/to/test_file.py -v
```

### 4. Refactor

Clean up the implementation while keeping tests green. Run the full
suite to check for regressions:

```bash
uv run pytest
```

### 5. Commit

Commit the test and implementation together.

---

## Commit conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/).

### Format

```
<type>: <description>
```

### Types

| Type | When to use |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `chore` | Build, CI, dependency updates |
| `test` | Adding or updating tests |
| `refactor` | Code restructure with no behavior change |

### Examples

```
feat: add semantic search to memory engine
fix: handle empty tool_calls in AILayer response parsing
docs: write developer-guide architecture doc
test: add hook executor fail-closed coverage
chore: update litellm dependency to 1.45
refactor: extract scoring formula into memory.scoring module
```

### Rules

- Use imperative mood ("add", not "added" or "adds").
- Keep the first line under 72 characters.
- No period at the end of the subject line.
- Reference issue numbers in the body when applicable.

---

## Next steps

- [Testing](testing.md) -- test patterns and fixtures in detail
- [Architecture](architecture.md) -- system design and module relationships
- [Project Structure](project-structure.md) -- full source tree reference
