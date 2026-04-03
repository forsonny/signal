"""SignalApp -- Textual-based terminal UI for Signal."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.widgets import Footer, Input, Static
from textual import work

from signalagent.tui.widgets.chat_log import ChatLog
from signalagent.tui.widgets.chat_input import ChatInput

if TYPE_CHECKING:
    from signalagent.comms.bus import MessageBus
    from signalagent.agents.host import AgentHost
    from signalagent.runtime.executor import Executor
    from signalagent.sessions.manager import SessionManager


class SignalHeader(Static):
    """1-line header: app name (left), session + model (right)."""

    def update_info(self, session_id: str, model_name: str) -> None:
        """Update header with session and model information."""
        self.update(
            f"[bold]Signal[/bold]  {session_id} [dim]\u00b7[/dim] {model_name}"
        )


class SignalApp(App):
    """Textual TUI for the Signal agent runtime."""

    CSS_PATH = "app.tcss"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self,
        instance_dir: Path,
        session_id: str | None = None,
    ) -> None:
        super().__init__()
        self.instance_dir = instance_dir
        self._initial_session_id = session_id
        self.executor: Executor | None = None
        self.bus: MessageBus | None = None
        self.host: AgentHost | None = None
        self.session_manager: SessionManager | None = None
        self.session_id: str | None = None
        self.model_name: str = ""

    def compose(self) -> ComposeResult:
        yield SignalHeader(id="header")
        yield ChatLog()
        yield ChatInput()
        yield Footer()

    async def on_mount(self) -> None:
        """Bootstrap the runtime and set up the session."""
        chat_log = self.query_one(ChatLog)
        chat_input = self.query_one(ChatInput)
        chat_input.disabled = True
        chat_log.write_system("Starting...")

        try:
            from signalagent.core.config import load_config, load_profile
            from signalagent.runtime.bootstrap import bootstrap
            from signalagent.sessions.manager import SessionManager

            config = load_config(self.instance_dir / "config.yaml")
            profile = load_profile(config.profile_name)
            self.model_name = config.ai.default_model

            self.executor, self.bus, self.host = await bootstrap(
                self.instance_dir, config, profile,
            )
            self.session_manager = SessionManager(
                self.instance_dir / "data" / "sessions",
            )

            if (
                self._initial_session_id
                and self.session_manager.exists(self._initial_session_id)
            ):
                self.session_id = self._initial_session_id
                self._show_session_history()
            else:
                self.session_id = self.session_manager.create()
                chat_log.write_system(f"New session: {self.session_id}")

            self.query_one(SignalHeader).update_info(
                self.session_id, self.model_name,
            )
            chat_input.disabled = False
            chat_input.focus()

        except Exception as e:
            chat_log.write_error(f"Failed to start: {e}")

    def _show_session_history(self) -> None:
        """Display last 6 turns from a resumed session."""
        chat_log = self.query_one(ChatLog)
        chat_log.write_system(f"Resuming session {self.session_id}")

        turns = self.session_manager.load(self.session_id)
        for turn in turns[-6:]:
            label = "you" if turn.role == "user" else "agent"
            chat_log.write_system(f"  {label}: {turn.content[:120]}")

        if turns:
            chat_log.write_system("---")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle text submission from ChatInput.

        Note: The event type is Input.Submitted (from Textual's Input base class).
        ChatInput inherits from Input and does not define its own Submitted class.
        The handler name on_input_submitted matches Input.Submitted.
        """
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        if text.startswith("/"):
            self._handle_slash_command(text)
        else:
            event.input.disabled = True
            self._send_message(text)

    def _handle_slash_command(self, text: str) -> None:
        """Dispatch slash commands."""
        chat_log = self.query_one(ChatLog)

        if text in ("/quit", "/exit"):
            self.exit()
            return

        if self.session_manager is None:
            chat_log.write_error("Runtime not initialized")
            return

        if text == "/history":
            for turn in self.session_manager.load(self.session_id):
                label = "you" if turn.role == "user" else "agent"
                chat_log.write_system(f"{label}: {turn.content}")
        elif text == "/session":
            chat_log.write_system(f"Session: {self.session_id}")
        else:
            chat_log.write_system(f"Unknown command: {text}")

    @work(thread=False, exit_on_error=False)
    async def _send_message(self, text: str) -> None:
        """Send user message to executor and display response."""
        chat_log = self.query_one(ChatLog)

        if self.executor is None:
            chat_log.write_error("Runtime not initialized -- cannot send message")
            chat_input = self.query_one(ChatInput)
            chat_input.disabled = False
            chat_input.focus()
            return

        chat_log.write_user(text)
        result = await self.executor.run(text, session_id=self.session_id)

        if result.error:
            chat_log.write_error(result.error)
        else:
            chat_log.write_agent(result.content)

        chat_input = self.query_one(ChatInput)
        chat_input.disabled = False
        chat_input.focus()
