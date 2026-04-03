# Phase 10b: Docker Packaging

## Overview

Phase 10b wraps the Signal runtime in a Docker container for deployment. The system is functionally complete (Phases 1-10a). This phase packages it: multi-stage Dockerfile, auto-init entrypoint, documentation.

**Depends on:** All prior phases (1-10a)

**Does not include:** Orchestration (Kubernetes, Compose), CI/CD pipelines, new CLI commands, health checks, or monitoring endpoints.

---

## 1. Dockerfile

Multi-stage build. Builder stage builds a wheel. Runtime stage installs it into a clean image.

```dockerfile
# -- Build stage --
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml VERSION ./
COPY src/ src/
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

# -- Runtime stage --
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
```

The runtime image contains only Python, the installed package, and the entrypoint script. No build tools (hatchling, build), no source code, no tests.

---

## 2. Entrypoint

`docker-entrypoint.sh` at the repo root:

```sh
#!/bin/sh
set -e
if [ ! -d /app/.signal ]; then
    signal init --profile blank
fi
exec signal "$@"
```

**Auto-init:** Checks for `/app/.signal`. If missing, runs `signal init --profile blank`. Runs once on first start, skips on subsequent runs.

**Exec passthrough:** `exec signal "$@"` replaces the shell with the `signal` CLI. Stdin, stdout, stderr pass through correctly. This matters for `signal chat` (interactive REPL).

**Custom profiles:** Users who want a non-blank profile run `docker run -v signal-data:/app/.signal signal init --profile devtools` first. The entrypoint sees `/app/.signal` already exists on the next run and skips auto-init.

---

## 3. .dockerignore

```
.git
.worktrees
worktrees
__pycache__
*.pyc
.pytest_cache
tests/
docs/
*.md
```

Keeps the build context small. Tests and docs do not go into the image.

---

## 4. Secrets & Environment

API keys are passed as environment variables. Docker handles this natively -- zero code changes.

```bash
# Direct
docker run -e ANTHROPIC_API_KEY=sk-... signal talk "hello"

# From .env file (multiple keys)
docker run --env-file .env signal talk "hello"
```

The `.env` file pattern supports users with multiple provider keys (Anthropic, OpenAI, Gemini, etc.). Docker's `--env-file` reads it at run time -- nothing is baked into the image.

---

## 5. Instance State & Persistence

The container writes to `/app/.signal`. State persists via Docker volumes:

```bash
# Named volume (simplest)
docker run -v signal-data:/app/.signal --env-file .env signal talk "hello"

# Bind mount (see the files)
docker run -v ./my-instance:/app/.signal --env-file .env signal talk "hello"
```

The Dockerfile does not declare a `VOLUME` directive. The user chooses their persistence strategy. Named volumes for "just works," bind mounts for "I want to see the files."

---

## 6. Documentation (README update)

Add a Docker section to README.md covering:

```bash
# Build
docker build -t signal .

# First run (auto-inits, then runs command)
docker run -e ANTHROPIC_API_KEY=sk-... signal talk "hello"

# Persistent state
docker run -v signal-data:/app/.signal -e ANTHROPIC_API_KEY=sk-... signal talk "hello"

# Environment file
docker run -v signal-data:/app/.signal --env-file .env signal talk "hello"

# Interactive chat (requires -it for stdin)
docker run -it -v signal-data:/app/.signal --env-file .env signal chat

# Custom profile
docker run -v signal-data:/app/.signal signal init --profile devtools
docker run -v signal-data:/app/.signal --env-file .env signal talk "hello"
```

**Note:** `signal chat` requires `docker run -it` (interactive + TTY). Without `-it`, the Rich console's `input()` call receives EOF immediately and the REPL exits.

---

## 7. File Structure

### New Files
- `Dockerfile` -- multi-stage build
- `docker-entrypoint.sh` -- auto-init + exec passthrough
- `.dockerignore` -- build context filter

### Modified Files
- `README.md` -- add Docker usage section
- `VERSION` -- bump to 0.15.0
- `docs/dev/roadmap.md` -- Phase 10b marked Complete

---

## 8. Success Criteria

### Dockerfile
1. Multi-stage build: builder stage builds wheel, runtime stage installs it
2. Runtime image has no build tools (hatchling, build)
3. Base image is `python:3.12-slim`
4. `WORKDIR /app`, entrypoint is `docker-entrypoint.sh`
5. `signal` CLI available on PATH in the container

### Entrypoint
6. Auto-initializes `/app/.signal` with `signal init --profile blank` if missing
7. Skips init when `/app/.signal` already exists
8. `exec signal "$@"` passes through user command
9. `set -e` fails fast on init errors

### Docker Ignore
10. Excludes `.git`, `worktrees`, `__pycache__`, `tests/`, `docs/`

### Documentation
11. README shows: build, basic run, persistent volume, .env file, interactive chat
12. Documents `-it` requirement for `signal chat`
13. Documents that custom profiles need manual `init` before the entrypoint auto-creates blank

### Regression
14. `docker build -t signal .` completes without error
15. `docker run signal --help` shows the CLI help
16. `docker run -e ANTHROPIC_API_KEY=test signal init --profile blank` creates instance
17. Existing local development workflow unchanged (no files modified that affect `uv sync` or `pytest`)

### End-to-End
18. `docker run signal talk "hello"` works on a fresh container (no pre-existing volume) -- auto-init + command execution in one step
