"""Shared scoring formula for memory retrieval.

Single source of truth for the scoring weights and decay calculation.
Used by both MemoryIndex.search() (tag-only path) and
MemoryEngine._search_semantic() (two-phase path).
"""

from __future__ import annotations

import math

# Scoring weights
RELEVANCE_WEIGHT = 0.5
FREQUENCY_WEIGHT = 0.25
CONFIDENCE_WEIGHT = 0.25


def compute_frequency_score(access_count: int) -> float:
    """Compute frequency score from access count. Capped at 1.0."""
    return min(math.log(access_count + 1) / 10.0, 1.0)


def compute_score(
    relevance: float,
    frequency_score: float,
    confidence: float,
    days_since_access: float,
    decay_half_life_days: int,
) -> float:
    """Compute the effective score for a memory.

    base_score = relevance * 0.5 + frequency * 0.25 + confidence * 0.25
    effective_score = base_score * decay_factor

    Args:
        relevance: Tag match proportion or embedding similarity (0.0-1.0).
        frequency_score: Pre-computed from access_count via compute_frequency_score().
        confidence: Memory's confidence value (0.0-1.0).
        days_since_access: Days since last access.
        decay_half_life_days: Days after which score is halved.
    """
    base_score = (
        relevance * RELEVANCE_WEIGHT
        + frequency_score * FREQUENCY_WEIGHT
        + confidence * CONFIDENCE_WEIGHT
    )
    decay_factor = 1.0 / (1.0 + days_since_access / decay_half_life_days)
    return base_score * decay_factor
