"""Pure functions for memory maintenance prompts and response parsing.

Separated from keeper.py so prompt text and parsing logic are
independently testable without agent infrastructure.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from signalagent.core.models import Memory

_VALID_CLASSIFICATIONS = frozenset({
    "contradiction", "duplication", "complementary", "distinct",
})
_VALID_ACTION_TYPES = frozenset({"archive", "consolidate", "skip"})


def build_classification_prompt(memories: list[Memory]) -> str:
    """Build a prompt asking the LLM to classify a group of memories."""
    now = datetime.now(timezone.utc)
    blocks: list[str] = []
    for i, mem in enumerate(memories, 1):
        accessed = mem.accessed
        if accessed.tzinfo is None:
            accessed = accessed.replace(tzinfo=timezone.utc)
        days_ago = max(int((now - accessed).total_seconds() / 86400), 0)
        blocks.append(
            f"Memory {i}:\n"
            f"- ID: {mem.id}\n"
            f"- Tags: {mem.tags}\n"
            f"- Confidence: {mem.confidence}\n"
            f"- Last accessed: {days_ago} days ago\n"
            f"- Content: {mem.content}"
        )

    memory_text = "\n\n".join(blocks)

    return (
        "You are a memory maintenance agent. Analyze the following group "
        "of memories and classify their relationship.\n\n"
        f"Memories in this group:\n\n{memory_text}\n\n"
        "Classify the relationship as one of:\n"
        '- "contradiction": The memories assert conflicting facts. '
        "One is wrong or outdated.\n"
        '- "duplication": The memories say essentially the same thing.\n'
        '- "complementary": The memories cover different aspects of the '
        "same topic and should be merged.\n"
        '- "distinct": The memories are about different concerns despite '
        "sharing tags.\n\n"
        "Respond with a JSON object:\n"
        "{\n"
        '  "classification": "contradiction|duplication|complementary|distinct",\n'
        '  "reasoning": "Brief explanation",\n'
        '  "action": {\n'
        '    "type": "archive|consolidate|skip",\n'
        '    "archive_ids": ["IDs to archive (for contradictions)"],\n'
        '    "archive_reason": "Why these should be archived",\n'
        '    "consolidate_ids": ["IDs to consolidate"]\n'
        "  }\n"
        "}\n\n"
        "For contradictions: archive the incorrect/outdated memory.\n"
        "For duplications/complementary: consolidate all memories.\n"
        "For distinct: skip (no action).\n\n"
        "Respond with ONLY the JSON object, no other text."
    )


def build_consolidation_prompt(memories: list[Memory]) -> str:
    """Build a prompt asking the LLM to merge memories into one."""
    blocks: list[str] = []
    for i, mem in enumerate(memories, 1):
        blocks.append(
            f"Memory {i}:\n"
            f"- Tags: {mem.tags}\n"
            f"- Content: {mem.content}"
        )

    memory_text = "\n\n".join(blocks)

    return (
        "Merge the following memories into a single consolidated memory. "
        "Preserve all important information. Remove redundancy.\n\n"
        f"Source memories:\n\n{memory_text}\n\n"
        "Respond with a JSON object:\n"
        "{\n"
        '  "content": "The merged memory text",\n'
        '  "tags": ["union", "of", "relevant", "tags"]\n'
        "}\n\n"
        "The merged content should be concise and capture all unique "
        "information. The tags should be the union of relevant tags.\n\n"
        "Respond with ONLY the JSON object, no other text."
    )


def parse_json_response(text: str) -> dict | None:
    """Parse JSON from LLM response, handling common formatting issues.

    Strips markdown code fences, then attempts json.loads().
    Returns None on any parse failure.
    """
    text = text.strip()
    if not text:
        return None
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def validate_classification(data: dict) -> bool:
    """Check that a classification response has required fields and valid values."""
    if data.get("classification") not in _VALID_CLASSIFICATIONS:
        return False
    action = data.get("action")
    if not isinstance(action, dict):
        return False
    if action.get("type") not in _VALID_ACTION_TYPES:
        return False
    return True


def validate_consolidation(data: dict) -> bool:
    """Check that a consolidation response has required fields."""
    if "content" not in data:
        return False
    if not isinstance(data.get("tags"), list):
        return False
    return True
