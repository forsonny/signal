"""MemoryKeeperAgent -- purpose-built agent for memory maintenance.

Not a MicroAgent. It's an agent in the bus/lifecycle sense (registered in
AgentHost, receives messages, BUSY/IDLE transitions) but purpose-built
for its job. No runner, no tools, no hooks, no worktree proxy.

Direct MemoryEngine dependency: this is the documented exception to the
protocol pattern. The MemoryKeeper is the one agent whose purpose is
infrastructure maintenance. A MemoryWriterProtocol that mirrors the
full engine write API adds abstraction without value.

Hook bypass accepted: The MemoryKeeper calls MemoryEngine methods
directly, so its actions bypass the hook pipeline. Observability comes
from changelog entries on memory files and the summary response through
the message bus. If observability of memory maintenance becomes important,
the engine operations should be wrapped as tools (archive_memory,
consolidate_memories) so hooks can intercept them.
"""

from __future__ import annotations

import logging

from signalagent.agents.base import BaseAgent
from signalagent.core.models import Memory, MemoryKeeperConfig, Message
from signalagent.core.protocols import AILayerProtocol
from signalagent.core.types import AgentType, MessageType
from signalagent.memory.engine import MemoryEngine
from signalagent.memory.prompts import (
    build_classification_prompt,
    build_consolidation_prompt,
    parse_json_response,
    validate_classification,
    validate_consolidation,
)

logger = logging.getLogger(__name__)

MEMORY_KEEPER_AGENT = "memory-keeper"


class MemoryKeeperAgent(BaseAgent):
    """Maintains memory health: consolidation, contradiction detection,
    staleness archival. Runs on heartbeat schedule or on-demand via Prime."""

    def __init__(
        self,
        ai: AILayerProtocol,
        engine: MemoryEngine,
        config: MemoryKeeperConfig,
        model: str,
    ) -> None:
        super().__init__(name=MEMORY_KEEPER_AGENT, agent_type=AgentType.MEMORY_KEEPER)
        self._ai = ai
        self._engine = engine
        self._config = config
        self._model = model

    @property
    def skill(self) -> str:
        return (
            "memory system maintenance: consolidation, "
            "contradiction detection, staleness archival"
        )

    async def _handle(self, message: Message) -> Message | None:
        """Run a full maintenance pass."""
        stats = {"archived": 0, "consolidated": 0, "skipped": 0}

        # Phase 1: classify memory groups
        groups = await self._engine.find_groups()
        groups = groups[: self._config.max_candidates_per_run]

        for group in groups:
            classification = await self._classify_group(group)
            if classification is None:
                stats["skipped"] += 1
                continue

            action_type = classification["action"]["type"]
            if action_type == "archive":
                archive_ids = classification["action"].get("archive_ids", [])
                reason = classification["action"].get(
                    "archive_reason",
                    "contradiction detected",
                )
                for mid in archive_ids:
                    await self._engine.archive(mid, reason=reason)
                    stats["archived"] += 1
            elif action_type == "consolidate":
                consolidate_ids = classification["action"].get(
                    "consolidate_ids",
                    [],
                )
                if len(consolidate_ids) >= 2:
                    merged = await self._merge_group(group, consolidate_ids)
                    if merged is not None:
                        stats["consolidated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    stats["skipped"] += 1
            # "skip" action: no counter increment (expected for distinct)

        # Phase 2: stale detection
        stale = await self._engine.find_stale(
            threshold_days=self._config.staleness_threshold_days,
            min_confidence=self._config.min_confidence,
        )
        for memory_id, reason in stale:
            await self._engine.archive(memory_id, reason=reason)
            stats["archived"] += 1

        summary = (
            f"Archived {stats['archived']} memories, "
            f"consolidated {stats['consolidated']} groups, "
            f"skipped {stats['skipped']} groups."
        )
        logger.info("MemoryKeeper: %s", summary)

        return Message(
            type=MessageType.RESULT,
            sender=self.name,
            recipient=message.sender,
            content=summary,
            parent_id=message.id,
        )

    async def _classify_group(self, group: list[Memory]) -> dict | None:
        """Send group to LLM for classification. Returns parsed dict or None."""
        prompt = build_classification_prompt(group)
        try:
            response = await self._ai.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
            )
        except Exception:
            logger.warning("Classification LLM call failed, skipping group")
            return None

        result = parse_json_response(response.content)
        if result is None or not validate_classification(result):
            return None
        return result

    async def _merge_group(
        self,
        group: list[Memory],
        consolidate_ids: list[str],
    ) -> Memory | None:
        """Consolidate memories via LLM-generated merged content."""
        sources = [m for m in group if m.id in consolidate_ids]
        if len(sources) < 2:
            return None

        prompt = build_consolidation_prompt(sources)
        try:
            response = await self._ai.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
            )
        except Exception:
            logger.warning("Consolidation LLM call failed, skipping group")
            return None

        result = parse_json_response(response.content)
        if result is None or not validate_consolidation(result):
            return None

        return await self._engine.consolidate(
            source_ids=consolidate_ids,
            new_content=result["content"],
            new_tags=result["tags"],
            agent=sources[0].agent,
            memory_type=sources[0].type,
        )
