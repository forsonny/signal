# src/signalagent/cli/worktree_cmd.py
"""signal worktree -- manage agent worktrees."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from signalagent.core.errors import InstanceError

worktree_app = typer.Typer(
    name="worktree",
    help="Manage agent worktrees.",
    no_args_is_help=True,
)

console = Console()


def _get_instance_dir() -> Path:
    """Locate the nearest ``.signal/`` instance directory.

    Returns:
        Absolute path to the instance directory.

    Raises:
        typer.Exit: If no instance is found in the directory tree.
    """
    from signalagent.core.config import find_instance
    try:
        return find_instance(Path.cwd())
    except InstanceError:
        console.print("[red]No Signal instance found. Run 'signal init' first.[/red]")
        raise typer.Exit(1)


@worktree_app.command("list")
def list_worktrees() -> None:
    """List pending worktrees awaiting review."""
    instance_dir = _get_instance_dir()

    from signalagent.worktrees.manifest import WorktreeManifest

    manifest = WorktreeManifest(instance_dir / "data" / "worktrees")
    pending = manifest.list_pending()

    if not pending:
        console.print("[dim]No pending worktrees.[/dim]")
        return

    table = Table(title="Pending Worktrees")
    table.add_column("ID", style="bold")
    table.add_column("Agent")
    table.add_column("Created")
    table.add_column("Files", justify="right")
    table.add_column("Git", justify="center")

    from signalagent.worktrees.manager import WorktreeManager

    manager = WorktreeManager(
        instance_dir=instance_dir, workspace_root=instance_dir,
    )

    for r in pending:
        file_count = "?"
        if r.worktree_path.exists():
            try:
                files = manager.changed_files(r.worktree_path)
                file_count = str(len(files))
            except Exception:
                pass

        table.add_row(
            r.id,
            r.agent_name,
            r.created.strftime("%Y-%m-%d %H:%M"),
            file_count,
            "Y" if r.is_git else "N",
        )

    console.print(table)


@worktree_app.command("merge")
def merge_worktree(
    worktree_id: str = typer.Argument(..., help="Worktree ID to merge"),
) -> None:
    """Merge worktree changes into the workspace.

    Copies changed files from the worktree back to the original workspace
    and marks the worktree record as ``"merged"``.

    Args:
        worktree_id: The unique worktree identifier to merge.

    Raises:
        typer.Exit: If the worktree is not found or not in pending state.
    """
    instance_dir = _get_instance_dir()

    from signalagent.worktrees.manifest import WorktreeManifest
    from signalagent.worktrees.manager import WorktreeManager

    manifest = WorktreeManifest(instance_dir / "data" / "worktrees")
    record = manifest.get(worktree_id)

    if record is None or record.status != "pending":
        console.print(f"[red]Worktree not found or not pending: {worktree_id}[/red]")
        raise typer.Exit(1)

    manager = WorktreeManager(
        instance_dir=instance_dir, workspace_root=record.workspace_root,
    )

    manager.merge(record.worktree_path)
    manager.cleanup(record.worktree_path, branch_name=record.branch_name)

    updated = record.model_copy(update={"status": "merged"})
    manifest.append(updated)

    console.print(f"[green]Merged worktree {worktree_id} into workspace.[/green]")


@worktree_app.command("discard")
def discard_worktree(
    worktree_id: str = typer.Argument(..., help="Worktree ID to discard"),
) -> None:
    """Discard worktree changes without merging.

    Removes the worktree directory and marks the record as ``"discarded"``.

    Args:
        worktree_id: The unique worktree identifier to discard.

    Raises:
        typer.Exit: If the worktree is not found or not in pending state.
    """
    instance_dir = _get_instance_dir()

    from signalagent.worktrees.manifest import WorktreeManifest
    from signalagent.worktrees.manager import WorktreeManager

    manifest = WorktreeManifest(instance_dir / "data" / "worktrees")
    record = manifest.get(worktree_id)

    if record is None or record.status != "pending":
        console.print(f"[red]Worktree not found or not pending: {worktree_id}[/red]")
        raise typer.Exit(1)

    manager = WorktreeManager(
        instance_dir=instance_dir, workspace_root=record.workspace_root,
    )

    manager.cleanup(record.worktree_path, branch_name=record.branch_name)

    updated = record.model_copy(update={"status": "discarded"})
    manifest.append(updated)

    console.print(f"[yellow]Discarded worktree {worktree_id}.[/yellow]")
