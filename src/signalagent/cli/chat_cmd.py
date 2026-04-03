"""signal chat -- interactive multi-turn conversation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from signalagent.cli.app import app
from signalagent.core.errors import InstanceError

console = Console()


async def _async_chat(session_id: str | None, instance_dir: Path) -> None:
    """Async REPL loop for interactive conversation.

    Imports are deferred to avoid pulling in heavyweight modules
    at CLI startup -- same pattern as ``talk_cmd.py``.

    Args:
        session_id: Existing session ID to resume, or ``None`` to start
            a new session.
        instance_dir: Path to the ``.signal/`` instance directory.
    """
    from signalagent.core.config import load_config, load_profile
    from signalagent.runtime.bootstrap import bootstrap
    from signalagent.sessions.manager import SessionManager

    config = load_config(instance_dir / "config.yaml")
    profile = load_profile(config.profile_name)
    executor, _bus, _host = await bootstrap(instance_dir, config, profile)

    # CLI creates its own SessionManager (same directory, stateless file I/O)
    sm = SessionManager(instance_dir / "data" / "sessions")

    if session_id and sm.exists(session_id):
        console.print(f"Resuming session [bold]{session_id}[/bold]")
        turns = sm.load(session_id)
        for turn in turns[-6:]:
            label = "[dim]you:[/dim]" if turn.role == "user" else "[dim]agent:[/dim]"
            console.print(f"  {label} {turn.content[:120]}")
        if turns:
            console.print()
    else:
        session_id = sm.create()
        console.print(f"New session: [bold]{session_id}[/bold]")

    console.print("[dim]Type /quit to exit, /history to show conversation, /session to show ID[/dim]\n")

    try:
        while True:
            try:
                user_input = console.input("[bold]you>[/bold] ")
            except EOFError:
                break

            stripped = user_input.strip()
            if not stripped:
                continue

            if stripped.startswith("/"):
                if stripped in ("/quit", "/exit"):
                    break
                elif stripped == "/history":
                    for turn in sm.load(session_id):
                        label = "you" if turn.role == "user" else "agent"
                        console.print(f"[dim]{label}:[/dim] {turn.content}")
                    continue
                elif stripped == "/session":
                    console.print(f"Session: {session_id}")
                    continue
                else:
                    console.print(f"[dim]Unknown command: {stripped}[/dim]")
                    continue

            result = await executor.run(user_input, session_id=session_id)
            if result.error:
                console.print(f"[red]Error: {result.error}[/red]")
            else:
                console.print(result.content)
            console.print()
    except KeyboardInterrupt:
        pass

    console.print(f"\nSession: [bold]{session_id}[/bold]")


@app.command()
def chat(
    session: str | None = typer.Option(None, "--session", "-s", help="Resume a session by ID"),
    simple: bool = typer.Option(False, "--simple", help="Use simple Rich REPL instead of TUI"),
) -> None:
    """Start an interactive multi-turn conversation.

    Args:
        session: Optional session ID to resume. When ``None``, a new
            session is created automatically.
        simple: When ``True``, use the plain Rich REPL instead of
            the Textual TUI.

    Raises:
        typer.Exit: If no Signal instance is found in the directory tree.
    """
    import sys

    try:
        from signalagent.core.config import find_instance
        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)

    if simple or not sys.stdin.isatty() or not sys.stdout.isatty():
        asyncio.run(_async_chat(session, instance_dir))
    else:
        from signalagent.tui.app import SignalApp
        tui = SignalApp(instance_dir=instance_dir, session_id=session)
        tui.run()
