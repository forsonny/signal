# Docker

**What you'll learn:**

- How to build the Signal Docker image
- How first-run auto-initialization works
- How to persist state with named volumes
- How to pass API keys via environment variables
- How to run interactive chat in a container
- How to use custom profiles in Docker

---

## Building the image

Build the Docker image from the project root:

```bash
docker build -t signal .
```

The build uses a two-stage Dockerfile:

1. **Builder stage:** Installs build tools and creates a wheel from the source in a `python:3.12-slim` image.
2. **Runtime stage:** Installs the wheel into a clean `python:3.12-slim` image, copies the entrypoint script, and sets it as the container entrypoint.

The `.dockerignore` excludes `.git`, `tests/`, `docs/`, `__pycache__`, and other non-runtime files from the build context.

---

## First run

The entrypoint script (`docker-entrypoint.sh`) handles automatic initialization:

```bash
docker run signal talk "Hello"
```

On first run, if `/app/.signal` does not exist, the entrypoint runs `signal init --profile blank` to create a fresh instance directory. Subsequent runs skip initialization because the directory already exists.

The entrypoint then executes `signal` with whatever arguments you pass to `docker run`.

---

## Persistent state

By default, container state is lost when the container exits. To keep your instance directory (memories, sessions, config) across runs, mount a named volume:

```bash
docker run -v signal-data:/app/.signal signal talk "Hello"
```

This maps the named volume `signal-data` to `/app/.signal` inside the container. The volume persists across container restarts and removals.

To inspect the volume contents:

```bash
docker volume inspect signal-data
```

---

## API keys

Signal uses LiteLLM for LLM access, which reads API keys from environment variables. Pass them at run time:

```bash
docker run -e OPENAI_API_KEY=sk-... signal talk "Hello"
```

For multiple keys, use an `.env` file:

```bash
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

```bash
docker run --env-file .env signal talk "Hello"
```

Combine with a volume for persistent state:

```bash
docker run --env-file .env -v signal-data:/app/.signal signal talk "Summarize recent work"
```

---

## Interactive chat

The `signal chat` command requires an interactive terminal. Use `-it` flags:

```bash
docker run -it --env-file .env -v signal-data:/app/.signal signal chat
```

Without `-it`, the REPL cannot read input and will exit immediately.

To resume a previous session:

```bash
docker run -it --env-file .env -v signal-data:/app/.signal signal chat --session ses_a1b2c3d4
```

---

## Custom profiles

To use a custom profile YAML file inside Docker, bind-mount it into the container:

```bash
docker run -v ./my-profile.yaml:/app/my-profile.yaml \
  --env-file .env \
  signal init --profile /app/my-profile.yaml
```

After initialization, subsequent runs use the stored profile reference:

```bash
docker run -v signal-data:/app/.signal --env-file .env signal talk "Hello"
```

Alternatively, build a derived image with the profile baked in:

```dockerfile
FROM signal
COPY my-profile.yaml /app/my-profile.yaml
RUN signal init --profile /app/my-profile.yaml
```

---

## Entrypoint behavior

The entrypoint script (`docker-entrypoint.sh`) does two things in sequence:

1. **Auto-init:** If `/app/.signal` does not exist, runs `signal init --profile blank`.
2. **Exec:** Replaces itself with `signal "$@"`, passing through all arguments.

This means:

- `docker run signal talk "Hello"` runs `signal talk "Hello"`.
- `docker run signal sessions list` runs `signal sessions list`.
- `docker run signal fork "A" "B"` runs `signal fork "A" "B"`.

The `set -e` directive ensures the container exits immediately if `signal init` fails (e.g., due to a missing volume or permissions error).

---

## Quick reference

| Task                         | Command                                                             |
|------------------------------|---------------------------------------------------------------------|
| Build image                  | `docker build -t signal .`                                          |
| One-shot query               | `docker run --env-file .env signal talk "Hello"`                    |
| Persistent state             | `docker run -v signal-data:/app/.signal --env-file .env signal talk "Hello"` |
| Interactive chat             | `docker run -it -v signal-data:/app/.signal --env-file .env signal chat` |
| Resume session               | `docker run -it -v signal-data:/app/.signal --env-file .env signal chat --session ses_...` |
| Custom profile init          | `docker run -v ./p.yaml:/app/p.yaml signal init --profile /app/p.yaml` |
| List sessions                | `docker run -v signal-data:/app/.signal signal sessions list`       |

---

## Next steps

- [Configuration](configuration.md) -- instance-level config.yaml that Docker auto-generates
- [Profiles](profiles.md) -- writing custom profiles for Docker deployments
- [Sessions](sessions.md) -- managing conversations that persist across container runs
