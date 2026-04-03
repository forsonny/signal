"""Cosine similarity for memory embedding vectors.

Pure math, no dependencies. Separated from the index so it's
independently testable.
"""

from __future__ import annotations


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector (must be same length as ``a``).

    Returns:
        Value between -1.0 and 1.0. Returns 0.0 if either vector is
        zero (undefined case, handled gracefully).
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
