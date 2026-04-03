"""Unit tests for ChatInput widget."""
from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from signalagent.tui.widgets.chat_input import ChatInput


class ChatInputApp(App):
    """Minimal app hosting a ChatInput for testing."""

    def compose(self) -> ComposeResult:
        yield ChatInput()


class TestChatInput:
    @pytest.mark.asyncio
    async def test_input_has_placeholder(self):
        app = ChatInputApp()
        async with app.run_test():
            chat_input = app.query_one(ChatInput)
            assert chat_input.placeholder == "Type a message..."

    @pytest.mark.asyncio
    async def test_input_can_be_disabled(self):
        app = ChatInputApp()
        async with app.run_test():
            chat_input = app.query_one(ChatInput)
            chat_input.disabled = True
            assert chat_input.disabled is True

    @pytest.mark.asyncio
    async def test_input_starts_enabled(self):
        app = ChatInputApp()
        async with app.run_test():
            chat_input = app.query_one(ChatInput)
            assert chat_input.disabled is False
