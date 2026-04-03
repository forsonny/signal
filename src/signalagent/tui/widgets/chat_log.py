"""ChatLog -- RichLog wrapper with typed write methods."""
from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog


class ChatLog(RichLog):
    """Message log with typed write methods for user, agent, system, and error."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._message_count: int = 0

    @property
    def line_count(self) -> int:
        """Number of messages written to the log."""
        return self._message_count

    def write_user(self, text: str) -> None:
        """Write a user message with purple 'you:' prefix."""
        line = Text()
        line.append("you: ", style="bold magenta")
        line.append(text)
        self.write(line)
        self._message_count += 1

    def write_agent(self, text: str) -> None:
        """Write an agent response with blue 'agent:' prefix."""
        line = Text()
        line.append("agent: ", style="bold blue")
        line.append(text)
        self.write(line)
        self._message_count += 1

    def write_system(self, text: str) -> None:
        """Write a system message in dim style."""
        self.write(Text(text, style="dim"))
        self._message_count += 1

    def write_error(self, text: str) -> None:
        """Write an error message in red."""
        line = Text()
        line.append("Error: ", style="bold red")
        line.append(text, style="red")
        self.write(line)
        self._message_count += 1
