"""Tests for memory maintenance prompt builders and JSON parsing."""

from datetime import datetime, timezone

from signalagent.core.models import Memory
from signalagent.core.types import MemoryType
from signalagent.memory.prompts import (
    build_classification_prompt,
    build_consolidation_prompt,
    parse_json_response,
    validate_classification,
    validate_consolidation,
)


def _make_memory(**overrides) -> Memory:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="mem_test1234", agent="prime", type=MemoryType.LEARNING,
        tags=["python", "errors"], content="User prefers explicit error handling.",
        confidence=0.8, version=1, created=now, updated=now, accessed=now,
    )
    defaults.update(overrides)
    return Memory(**defaults)


class TestBuildClassificationPrompt:
    def test_includes_all_memory_ids(self):
        m1 = _make_memory(id="mem_11111111")
        m2 = _make_memory(id="mem_22222222")
        prompt = build_classification_prompt([m1, m2])
        assert "mem_11111111" in prompt
        assert "mem_22222222" in prompt

    def test_includes_content(self):
        m1 = _make_memory(content="first lesson")
        prompt = build_classification_prompt([m1])
        assert "first lesson" in prompt

    def test_includes_tags(self):
        m1 = _make_memory(tags=["python", "errors"])
        prompt = build_classification_prompt([m1])
        assert "python" in prompt
        assert "errors" in prompt


class TestBuildConsolidationPrompt:
    def test_includes_all_content(self):
        m1 = _make_memory(id="mem_11111111", content="lesson one")
        m2 = _make_memory(id="mem_22222222", content="lesson two")
        prompt = build_consolidation_prompt([m1, m2])
        assert "lesson one" in prompt
        assert "lesson two" in prompt


class TestParseJsonResponse:
    def test_parses_clean_json(self):
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_strips_markdown_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = parse_json_response(text)
        assert result == {"key": "value"}

    def test_strips_code_fence_without_language(self):
        text = '```\n{"key": "value"}\n```'
        result = parse_json_response(text)
        assert result == {"key": "value"}

    def test_returns_none_on_invalid_json(self):
        result = parse_json_response("not json at all")
        assert result is None

    def test_returns_none_on_empty_string(self):
        result = parse_json_response("")
        assert result is None


class TestValidateClassification:
    def test_valid_classification(self):
        data = {
            "classification": "contradiction",
            "reasoning": "they conflict",
            "action": {
                "type": "archive",
                "archive_ids": ["mem_11111111"],
                "archive_reason": "outdated",
            },
        }
        assert validate_classification(data) is True

    def test_missing_classification(self):
        data = {"reasoning": "test", "action": {"type": "skip"}}
        assert validate_classification(data) is False

    def test_invalid_classification_value(self):
        data = {
            "classification": "unknown_type",
            "reasoning": "test",
            "action": {"type": "skip"},
        }
        assert validate_classification(data) is False

    def test_missing_action(self):
        data = {"classification": "distinct", "reasoning": "test"}
        assert validate_classification(data) is False


class TestValidateConsolidation:
    def test_valid_consolidation(self):
        data = {"content": "merged text", "tags": ["python"]}
        assert validate_consolidation(data) is True

    def test_missing_content(self):
        data = {"tags": ["python"]}
        assert validate_consolidation(data) is False

    def test_tags_not_a_list(self):
        data = {"content": "text", "tags": "python"}
        assert validate_consolidation(data) is False
