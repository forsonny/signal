"""Tests for SignalApp lifecycle, slash commands, and message flow."""
from __future__ import annotations

import pytest

from signalagent.tui.app import SignalApp
from signalagent.tui.widgets.chat_log import ChatLog
from signalagent.tui.widgets.chat_input import ChatInput
from signalagent.runtime.executor import ExecutorResult


class TestAppMount:
    @pytest.mark.asyncio
    async def test_app_mounts_with_new_session(
        self, tmp_instance_dir, patch_bootstrap,
    ):
        """App creates a new session when no session_id is provided."""
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test():
            assert app.session_id is not None
            assert app.session_id.startswith("ses_")

    @pytest.mark.asyncio
    async def test_app_mounts_with_existing_session(
        self, tmp_instance_dir, patch_bootstrap,
    ):
        """App resumes an existing session when a valid session_id is provided."""
        from signalagent.sessions.manager import SessionManager
        sm = SessionManager(tmp_instance_dir / "data" / "sessions")
        existing_id = sm.create()

        app = SignalApp(instance_dir=tmp_instance_dir, session_id=existing_id)
        async with app.run_test():
            assert app.session_id == existing_id

    @pytest.mark.asyncio
    async def test_app_creates_new_session_when_id_not_found(
        self, tmp_instance_dir, patch_bootstrap,
    ):
        """App creates a new session when provided session_id doesn't exist."""
        app = SignalApp(instance_dir=tmp_instance_dir, session_id="ses_nonexistent")
        async with app.run_test():
            assert app.session_id is not None
            assert app.session_id != "ses_nonexistent"

    @pytest.mark.asyncio
    async def test_app_has_chat_log(self, tmp_instance_dir, patch_bootstrap):
        """App composes a ChatLog widget."""
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test():
            chat_log = app.query_one(ChatLog)
            assert chat_log is not None

    @pytest.mark.asyncio
    async def test_app_has_chat_input(self, tmp_instance_dir, patch_bootstrap):
        """App composes a ChatInput widget."""
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test():
            chat_input = app.query_one(ChatInput)
            assert chat_input is not None

    @pytest.mark.asyncio
    async def test_chat_input_focused_after_mount(
        self, tmp_instance_dir, patch_bootstrap,
    ):
        """ChatInput is focused after app finishes mounting."""
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test():
            chat_input = app.query_one(ChatInput)
            assert chat_input.has_focus
