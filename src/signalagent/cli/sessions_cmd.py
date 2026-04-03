"""signal sessions -- session management commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from signalagent.core.errors import InstanceError

sessions_app = typer.Typer(
    name="sessions",
    help="Manage conversation sessions.",
    no_args_is_help=True,
)

console = Console()


@sessions_app.command("list")
def list_sessions(
    limit: int = typer.Option(20, "--limit", "-n", help="Max sessions to show"),
) -> None:
    """List recent conversation sessions.

    Args:
        limit: Maximum number of sessions to display.

    Raises:
        typer.Exit: If no Signal instance is found.
    """
    try:
        from signalagent.core.config import find_instance
        instance_dir = find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)

    from signalagent.sessions.manager import SessionManager

    sm = SessionManager(instance_dir / "data" / "sessions")
    sessions = sm.list_sessions(limit=limit)

    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Recent Sessions")
    table.add_column("ID", style="bold")
    table.add_column("Created")
    table.add_column("Preview")
    table.add_column("Turns", justify="right")

    for s in sessions:
        table.add_row(
            s.id,
            s.created.strftime("%Y-%m-%d %H:%M"),
            s.preview[:60] + ("..." if len(s.preview) > 60 else ""),
            str(s.turn_count),
        )

    console.print(table)
