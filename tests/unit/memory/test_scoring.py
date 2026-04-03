"""Tests for shared scoring function."""

import pytest


class TestComputeScore:
    def test_full_relevance_high_confidence(self):
        from signalagent.memory.scoring import compute_score
        score = compute_score(
            relevance=1.0, frequency_score=0.0,
            confidence=0.8, days_since_access=0, decay_half_life_days=30,
        )
        # relevance(1.0)*0.5 + freq(0.0)*0.25 + conf(0.8)*0.25 = 0.7
        # decay = 1.0 / (1 + 0/30) = 1.0
        assert score == pytest.approx(0.7)

    def test_zero_relevance(self):
        from signalagent.memory.scoring import compute_score
        score = compute_score(
            relevance=0.0, frequency_score=0.0,
            confidence=0.5, days_since_access=0, decay_half_life_days=30,
        )
        assert score == pytest.approx(0.125)

    def test_decay_halves_at_half_life(self):
        from signalagent.memory.scoring import compute_score
        fresh = compute_score(
            relevance=1.0, frequency_score=0.0,
            confidence=1.0, days_since_access=0, decay_half_life_days=30,
        )
        stale = compute_score(
            relevance=1.0, frequency_score=0.0,
            confidence=1.0, days_since_access=30, decay_half_life_days=30,
        )
        assert stale == pytest.approx(fresh / 2.0)

    def test_frequency_contributes(self):
        from signalagent.memory.scoring import compute_score
        no_freq = compute_score(
            relevance=0.5, frequency_score=0.0,
            confidence=0.5, days_since_access=0, decay_half_life_days=30,
        )
        with_freq = compute_score(
            relevance=0.5, frequency_score=0.5,
            confidence=0.5, days_since_access=0, decay_half_life_days=30,
        )
        assert with_freq > no_freq


class TestComputeFrequencyScore:
    def test_zero_access(self):
        from signalagent.memory.scoring import compute_frequency_score
        assert compute_frequency_score(0) == pytest.approx(0.0)

    def test_capped_at_one(self):
        from signalagent.memory.scoring import compute_frequency_score
        assert compute_frequency_score(1_000_000) <= 1.0
