"""Signal CLI -- entry point for all commands."""

import typer

app = typer.Typer(
    name="signal",
    help="Signal -- AI agent runtime framework",
    no_args_is_help=True,
)


def _register_commands() -> None:
    """Import command modules so their @app.command() decorators execute.

    Safe to call at module level because `app` is already defined above.
    The command modules import `app` from this module -- Python resolves
    this correctly since `app` is assigned before this function runs.
    """
    import signalagent.cli.init_cmd  # noqa: F401
    import signalagent.cli.talk_cmd  # noqa: F401
    import signalagent.cli.chat_cmd  # noqa: F401
    import signalagent.cli.fork_cmd  # noqa: F401
    from signalagent.cli.memory_cmd import memory_app
    from signalagent.cli.sessions_cmd import sessions_app
    from signalagent.cli.worktree_cmd import worktree_app

    app.add_typer(memory_app, name="memory")
    app.add_typer(sessions_app, name="sessions")
    app.add_typer(worktree_app, name="worktree")


_register_commands()


def main() -> None:
    """Entry point for the signal CLI."""
    app()
