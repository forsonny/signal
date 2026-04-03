"""Unit tests for AuditLogger -- JSONL append + deduplication."""

import json

import pytest

from signalagent.security.audit import AuditEvent, AuditLogger


class TestAuditEvent:
    def test_construction(self):
        event = AuditEvent(
            timestamp="2026-04-03T12:00:00+00:00",
            event_type="tool_call",
            agent="researcher",
            detail={"tool": "web_search"},
        )
        assert event.event_type == "tool_call"
        assert event.agent == "researcher"

    def test_rejects_extra_fields(self):
        with pytest.raises(Exception):
            AuditEvent(
                timestamp="2026-04-03T12:00:00+00:00",
                event_type="tool_call",
                agent="researcher",
                detail={},
                bogus="bad",
            )


class TestAuditLoggerLog:
    def test_creates_audit_file(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.log(AuditEvent(
            timestamp="2026-04-03T12:00:00+00:00",
            event_type="tool_call",
            agent="researcher",
            detail={"tool": "web_search"},
        ))
        audit_file = tmp_path / "logs" / "audit.jsonl"
        assert audit_file.exists()

    def test_appends_jsonl(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.log(AuditEvent(
            timestamp="2026-04-03T12:00:00+00:00",
            event_type="tool_call",
            agent="researcher",
            detail={"tool": "web_search"},
        ))
        logger.log(AuditEvent(
            timestamp="2026-04-03T12:01:00+00:00",
            event_type="policy_denial",
            agent="researcher",
            detail={"tool": "bash"},
        ))
        lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event_type"] == "tool_call"
        assert json.loads(lines[1])["event_type"] == "policy_denial"

    def test_detail_preserved(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.log(AuditEvent(
            timestamp="2026-04-03T12:00:00+00:00",
            event_type="policy_denial",
            agent="coder",
            detail={"tool": "bash", "rule": "deny:tool:bash"},
        ))
        entry = json.loads(
            (tmp_path / "logs" / "audit.jsonl").read_text().strip(),
        )
        assert entry["detail"]["rule"] == "deny:tool:bash"


class TestAuditLoggerWarningDedup:
    def test_warn_no_policy_logs_once(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.warn_no_policy("researcher")
        logger.warn_no_policy("researcher")
        logger.warn_no_policy("researcher")
        lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event_type"] == "warning"
        assert "researcher" in entry["detail"]["message"]

    def test_warn_different_agents(self, tmp_path):
        logger = AuditLogger(audit_dir=tmp_path / "logs")
        logger.warn_no_policy("researcher")
        logger.warn_no_policy("coder")
        lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
