"""Unit tests for SessionManager -- file-based session persistence."""
import json
import pytest
from datetime import datetime, timezone

from signalagent.core.models import Turn
from signalagent.sessions.manager import SessionManager


class TestSessionCreate:
    def test_create_returns_session_id(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        assert sid.startswith("ses_")
        assert len(sid) == 12  # ses_ + 8 hex chars

    def test_create_creates_empty_file(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        path = tmp_path / f"{sid}.jsonl"
        assert path.exists()
        assert path.read_text() == ""

    def test_create_generates_unique_ids(self, tmp_path):
        sm = SessionManager(tmp_path)
        ids = {sm.create() for _ in range(10)}
        assert len(ids) == 10


class TestSessionAppendAndLoad:
    def test_append_and_load_single_turn(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        turn = Turn(role="user", content="hello", timestamp=datetime.now(timezone.utc))
        sm.append(sid, turn)
        turns = sm.load(sid)
        assert len(turns) == 1
        assert turns[0].role == "user"
        assert turns[0].content == "hello"

    def test_append_multiple_turns_preserves_order(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="first", timestamp=now))
        sm.append(sid, Turn(role="assistant", content="second", timestamp=now))
        sm.append(sid, Turn(role="user", content="third", timestamp=now))
        turns = sm.load(sid)
        assert len(turns) == 3
        assert [t.content for t in turns] == ["first", "second", "third"]

    def test_load_nonexistent_returns_empty(self, tmp_path):
        sm = SessionManager(tmp_path)
        turns = sm.load("ses_nonexist")
        assert turns == []

    def test_load_skips_corrupt_lines(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="good", timestamp=now))
        path = tmp_path / f"{sid}.jsonl"
        with open(path, "a") as f:
            f.write("NOT VALID JSON\n")
        sm.append(sid, Turn(role="assistant", content="also good", timestamp=now))
        turns = sm.load(sid)
        assert len(turns) == 2
        assert turns[0].content == "good"
        assert turns[1].content == "also good"


class TestSessionExists:
    def test_exists_true_for_created_session(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        assert sm.exists(sid) is True

    def test_exists_false_for_missing_session(self, tmp_path):
        sm = SessionManager(tmp_path)
        assert sm.exists("ses_nonexist") is False


class TestSessionList:
    def test_list_sessions_returns_summaries(self, tmp_path):
        sm = SessionManager(tmp_path)
        sid = sm.create()
        now = datetime.now(timezone.utc)
        sm.append(sid, Turn(role="user", content="hello world", timestamp=now))
        sm.append(sid, Turn(role="assistant", content="hi there", timestamp=now))
        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].id == sid
        assert sessions[0].turn_count == 2
        assert "hello world" in sessions[0].preview

    def test_list_sessions_empty_dir(self, tmp_path):
        sm = SessionManager(tmp_path)
        sessions = sm.list_sessions()
        assert sessions == []

    def test_list_sessions_respects_limit(self, tmp_path):
        sm = SessionManager(tmp_path)
        now = datetime.now(timezone.utc)
        for _ in range(5):
            sid = sm.create()
            sm.append(sid, Turn(role="user", content="msg", timestamp=now))
        sessions = sm.list_sessions(limit=3)
        assert len(sessions) == 3

    def test_list_sessions_sorted_by_recency(self, tmp_path):
        import time
        sm = SessionManager(tmp_path)
        now = datetime.now(timezone.utc)
        sid1 = sm.create()
        sm.append(sid1, Turn(role="user", content="older", timestamp=now))
        time.sleep(0.01)
        sid2 = sm.create()
        sm.append(sid2, Turn(role="user", content="newer", timestamp=now))
        sessions = sm.list_sessions()
        assert sessions[0].id == sid2
