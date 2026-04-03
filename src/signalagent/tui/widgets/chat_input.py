"""ChatInput -- thin Input subclass with styled prompt."""
from __future__ import annotations

from textual.widgets import Input


class ChatInput(Input):
    """User text entry with placeholder. Styling is CSS-only."""

    def __init__(self) -> None:
        super().__init__(placeholder="Type a message...")
