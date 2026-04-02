"""Tests for MemoryKeeperAgent."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from signalagent.ai.layer import AIResponse
from signalagent.core.models import Memory, MemoryKeeperConfig, Message
from signalagent.core.types import MemoryType, MessageType, HEARTBEAT_SENDER
from signalagent.memory.engine import MemoryEngine
from signalagent.memory.keeper import MemoryKeeperAgent


def _make_ai_response(content: str) -> AIResponse:
    return AIResponse(
        content=content,
        model="test",
        provider="test",
        input_tokens=10,
        output_tokens=20,
    )


def _heartbeat_message() -> Message:
    return Message(
        type=MessageType.TRIGGER,
        sender=HEARTBEAT_SENDER,
        recipient="memory-keeper",
        content="Run memory maintenance",
    )


@pytest.fixture
async def engine(tmp_path):
    eng = MemoryEngine(tmp_path)
    await eng.initialize()
    yield eng
    await eng.close()


@pytest.fixture
def config():
    return MemoryKeeperConfig(
        staleness_threshold_days=90,
        min_confidence=0.1,
        max_candidates_per_run=20,
    )


class TestMemoryKeeperAgent:
    async def test_empty_maintenance_pass(self, engine, config):
        """No memories -> summary with zero counts."""
        mock_ai = AsyncMock()
        keeper = MemoryKeeperAgent(
            ai=mock_ai, engine=engine, config=config, model="test-model",
        )
        result = await keeper.handle(_heartbeat_message())
        assert result is not None
        assert "Archived 0" in result.content
        assert "consolidated 0" in result.content

    async def test_archives_stale_memory(self, engine, config):
        """Stale memory gets archived."""
        mem = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="old lesson",
            confidence=0.05,
        )
        mem.accessed = datetime.now(timezone.utc) - timedelta(days=100)
        await engine.store(mem)

        mock_ai = AsyncMock()
        keeper = MemoryKeeperAgent(
            ai=mock_ai, engine=engine, config=config, model="test-model",
        )
        result = await keeper.handle(_heartbeat_message())
        assert "Archived 1" in result.content
        row = await engine._index.get(mem.id)
        assert row["is_archived"] == 1

    async def test_classifies_and_consolidates(self, engine, config):
        """Two duplicate memories get consolidated via LLM classification."""
        m1 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="lesson about python",
        )
        m2 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="python lesson duplicate",
        )
        await engine.store(m1)
        await engine.store(m2)

        classification_json = json.dumps({
            "classification": "duplication",
            "reasoning": "same topic",
            "action": {
                "type": "consolidate",
                "consolidate_ids": [m1.id, m2.id],
            },
        })
        consolidation_json = json.dumps({
            "content": "Unified python lesson",
            "tags": ["python"],
        })

        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            side_effect=[
                _make_ai_response(classification_json),
                _make_ai_response(consolidation_json),
            ]
        )

        keeper = MemoryKeeperAgent(
            ai=mock_ai, engine=engine, config=config, model="test-model",
        )
        result = await keeper.handle(_heartbeat_message())
        assert "consolidated 1" in result.content
        row1 = await engine._index.get(m1.id)
        row2 = await engine._index.get(m2.id)
        assert row1["is_archived"] == 1
        assert row2["is_archived"] == 1

    async def test_classifies_and_archives_contradiction(self, engine, config):
        """Contradictory memory gets archived."""
        m1 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="python 2 is best",
        )
        m2 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="python 3 is best",
        )
        await engine.store(m1)
        await engine.store(m2)

        classification_json = json.dumps({
            "classification": "contradiction",
            "reasoning": "python 2 is outdated",
            "action": {
                "type": "archive",
                "archive_ids": [m1.id],
                "archive_reason": "outdated: python 2 is no longer best practice",
            },
        })

        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response(classification_json),
        )

        keeper = MemoryKeeperAgent(
            ai=mock_ai, engine=engine, config=config, model="test-model",
        )
        result = await keeper.handle(_heartbeat_message())
        assert "Archived 1" in result.content

    async def test_skips_on_parse_error(self, engine, config):
        """Unparseable LLM response skips the group."""
        m1 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="lesson 1",
        )
        m2 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="lesson 2",
        )
        await engine.store(m1)
        await engine.store(m2)

        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response("I can't produce JSON sorry"),
        )

        keeper = MemoryKeeperAgent(
            ai=mock_ai, engine=engine, config=config, model="test-model",
        )
        result = await keeper.handle(_heartbeat_message())
        assert "skipped 1" in result.content

    async def test_skips_distinct_classification(self, engine, config):
        """Distinct classification means no action."""
        m1 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="lesson 1",
        )
        m2 = engine.create_memory(
            agent="prime",
            memory_type=MemoryType.LEARNING,
            tags=["python"],
            content="lesson 2",
        )
        await engine.store(m1)
        await engine.store(m2)

        classification_json = json.dumps({
            "classification": "distinct",
            "reasoning": "different topics",
            "action": {"type": "skip"},
        })

        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response(classification_json),
        )

        keeper = MemoryKeeperAgent(
            ai=mock_ai, engine=engine, config=config, model="test-model",
        )
        result = await keeper.handle(_heartbeat_message())
        assert "Archived 0" in result.content
        assert "consolidated 0" in result.content

    async def test_skill_property(self, engine, config):
        """MemoryKeeperAgent exposes a skill for Prime routing."""
        mock_ai = AsyncMock()
        keeper = MemoryKeeperAgent(
            ai=mock_ai, engine=engine, config=config, model="test-model",
        )
        assert "maintenance" in keeper.skill.lower()

    async def test_respects_max_candidates(self, engine, config):
        """Only processes up to max_candidates_per_run groups."""
        limited_config = MemoryKeeperConfig(max_candidates_per_run=1)

        for i in range(4):
            mem = engine.create_memory(
                agent="prime",
                memory_type=MemoryType.LEARNING,
                tags=["python"],
                content=f"learning {i}",
            )
            await engine.store(mem)

        classification_json = json.dumps({
            "classification": "distinct",
            "reasoning": "different",
            "action": {"type": "skip"},
        })

        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(
            return_value=_make_ai_response(classification_json),
        )

        keeper = MemoryKeeperAgent(
            ai=mock_ai, engine=engine, config=limited_config, model="test-model",
        )
        await keeper.handle(_heartbeat_message())
        assert mock_ai.complete.call_count == 1
