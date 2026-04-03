"""Unit tests for ChatLog widget."""
from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from signalagent.tui.widgets.chat_log import ChatLog


class ChatLogApp(App):
    """Minimal app hosting a ChatLog for testing."""

    def compose(self) -> ComposeResult:
        yield ChatLog()


class TestChatLogWrite:
    @pytest.mark.asyncio
    async def test_write_user_adds_line(self):
        app = ChatLogApp()
        async with app.run_test():
            chat_log = app.query_one(ChatLog)
            chat_log.write_user("hello world")
            assert chat_log.line_count > 0

    @pytest.mark.asyncio
    async def test_write_agent_adds_line(self):
        app = ChatLogApp()
        async with app.run_test():
            chat_log = app.query_one(ChatLog)
            chat_log.write_agent("I can help with that.")
            assert chat_log.line_count > 0

    @pytest.mark.asyncio
    async def test_write_system_adds_line(self):
        app = ChatLogApp()
        async with app.run_test():
            chat_log = app.query_one(ChatLog)
            chat_log.write_system("New session: ses_test0001")
            assert chat_log.line_count > 0

    @pytest.mark.asyncio
    async def test_write_error_adds_line(self):
        app = ChatLogApp()
        async with app.run_test():
            chat_log = app.query_one(ChatLog)
            chat_log.write_error("Connection failed")
            assert chat_log.line_count > 0

    @pytest.mark.asyncio
    async def test_multiple_writes_accumulate(self):
        app = ChatLogApp()
        async with app.run_test():
            chat_log = app.query_one(ChatLog)
            chat_log.write_user("first")
            chat_log.write_agent("second")
            chat_log.write_system("third")
            assert chat_log.line_count >= 3

    @pytest.mark.asyncio
    async def test_write_user_empty_string(self):
        """Empty input should still render (echoes what user submitted)."""
        app = ChatLogApp()
        async with app.run_test():
            chat_log = app.query_one(ChatLog)
            chat_log.write_user("")
            assert chat_log.line_count > 0
