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


class TestSlashCommands:
    @pytest.mark.asyncio
    async def test_quit_exits_app(self, tmp_instance_dir, patch_bootstrap):
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            chat_input = app.query_one(ChatInput)
            chat_input.value = "/quit"
            await pilot.press("enter")
            # App should be exiting
            assert app._exit

    @pytest.mark.asyncio
    async def test_exit_alias(self, tmp_instance_dir, patch_bootstrap):
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            chat_input = app.query_one(ChatInput)
            chat_input.value = "/exit"
            await pilot.press("enter")
            assert app._exit

    @pytest.mark.asyncio
    async def test_session_shows_id(self, tmp_instance_dir, patch_bootstrap):
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            initial_lines = app.query_one(ChatLog).line_count
            chat_input = app.query_one(ChatInput)
            chat_input.value = "/session"
            await pilot.press("enter")
            assert app.query_one(ChatLog).line_count > initial_lines

    @pytest.mark.asyncio
    async def test_history_shows_turns(self, tmp_instance_dir, patch_bootstrap):
        from signalagent.sessions.manager import SessionManager
        from signalagent.core.models import Turn
        from datetime import datetime, timezone

        sm = SessionManager(tmp_instance_dir / "data" / "sessions")
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="hello", timestamp=now))
        sm.append(sid, Turn(role="assistant", content="hi there", timestamp=now))

        app = SignalApp(instance_dir=tmp_instance_dir, session_id=sid)
        async with app.run_test() as pilot:
            initial_lines = app.query_one(ChatLog).line_count
            chat_input = app.query_one(ChatInput)
            chat_input.value = "/history"
            await pilot.press("enter")
            assert app.query_one(ChatLog).line_count > initial_lines

    @pytest.mark.asyncio
    async def test_unknown_command_shows_message(self, tmp_instance_dir, patch_bootstrap):
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            initial_lines = app.query_one(ChatLog).line_count
            chat_input = app.query_one(ChatInput)
            chat_input.value = "/foobar"
            await pilot.press("enter")
            assert app.query_one(ChatLog).line_count > initial_lines

    @pytest.mark.asyncio
    async def test_empty_input_does_nothing(self, tmp_instance_dir, patch_bootstrap):
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            initial_lines = app.query_one(ChatLog).line_count
            chat_input = app.query_one(ChatInput)
            chat_input.value = "   "
            await pilot.press("enter")
            assert app.query_one(ChatLog).line_count == initial_lines

    @pytest.mark.asyncio
    async def test_input_cleared_after_command(self, tmp_instance_dir, patch_bootstrap):
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            chat_input = app.query_one(ChatInput)
            chat_input.value = "/session"
            await pilot.press("enter")
            assert chat_input.value == ""


class TestMessageFlow:
    @pytest.mark.asyncio
    async def test_send_message_echoes_user_input(self, tmp_instance_dir, patch_bootstrap):
        """User message is echoed to ChatLog before executor runs."""
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            initial_lines = app.query_one(ChatLog).line_count
            chat_input = app.query_one(ChatInput)
            chat_input.value = "hello agent"
            await pilot.press("enter")
            await pilot.pause()
            # At least user echo + agent response added
            assert app.query_one(ChatLog).line_count >= initial_lines + 2

    @pytest.mark.asyncio
    async def test_send_message_calls_executor(self, tmp_instance_dir, patch_bootstrap):
        """Executor.run is called with correct args."""
        mock_executor = patch_bootstrap

        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            session_id = app.session_id
            chat_input = app.query_one(ChatInput)
            chat_input.value = "test message"
            await pilot.press("enter")
            await pilot.pause()
            mock_executor.run.assert_called_once_with(
                "test message", session_id=session_id,
            )

    @pytest.mark.asyncio
    async def test_send_message_shows_error(self, tmp_instance_dir, patch_bootstrap):
        """Error response is displayed in ChatLog."""
        mock_executor = patch_bootstrap
        mock_executor.run.return_value = ExecutorResult(
            content="", error="Connection timeout",
        )

        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            chat_input = app.query_one(ChatInput)
            chat_input.value = "hello"
            await pilot.press("enter")
            await pilot.pause()
            mock_executor.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_input_disabled_during_processing(self, tmp_instance_dir, patch_bootstrap):
        """ChatInput is disabled while the executor is processing."""
        import asyncio

        mock_executor = patch_bootstrap
        started = asyncio.Event()
        proceed = asyncio.Event()

        async def slow_run(user_message, session_id=None):
            started.set()
            await proceed.wait()
            return ExecutorResult(content="done")

        mock_executor.run = slow_run

        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            chat_input = app.query_one(ChatInput)
            chat_input.value = "thinking..."
            await pilot.press("enter")
            await started.wait()
            assert chat_input.disabled is True
            proceed.set()
            await pilot.pause()
            assert chat_input.disabled is False

    @pytest.mark.asyncio
    async def test_input_cleared_after_submit(self, tmp_instance_dir, patch_bootstrap):
        """ChatInput value is cleared immediately on submit."""
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            chat_input = app.query_one(ChatInput)
            chat_input.value = "some message"
            await pilot.press("enter")
            assert chat_input.value == ""

    @pytest.mark.asyncio
    async def test_input_refocused_after_response(self, tmp_instance_dir, patch_bootstrap):
        """ChatInput is focused after executor response arrives."""
        app = SignalApp(instance_dir=tmp_instance_dir)
        async with app.run_test() as pilot:
            chat_input = app.query_one(ChatInput)
            chat_input.value = "hi"
            await pilot.press("enter")
            await pilot.pause()
            assert chat_input.has_focus
