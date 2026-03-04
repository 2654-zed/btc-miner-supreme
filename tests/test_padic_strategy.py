"""
tests/test_padic_strategy.py
─────────────────────────────
Unit tests for PadicLadderStrategy and its NumPy fallback scorer.

Covers:
  • Output shape and dtype
  • Determinism (same input → same output)
  • Score range (non-negative)
  • NumPy fallback ``_numpy_score_array()`` directly
  • Custom PadicLadderConfig
  • Hardware target string
  • Diagnostics dict structure
  • Call count / timing accumulation

Run:  pytest tests/test_padic_strategy.py -v
"""

from __future__ import annotations

import numpy as np
import pytest

from infrastructure.strategies.padic_ladder_strategy import (
    PadicLadderConfig,
    PadicLadderStrategy,
    _numpy_score_array,
)


# ═════════════════════════════════════════════════════════════════════════
# _numpy_score_array (pure NumPy fallback)
# ═════════════════════════════════════════════════════════════════════════

class TestNumpyScoreArray:
    """Direct tests on the vectorised NumPy scorer."""

    def setup_method(self):
        self.hi_primes = np.array([11, 13, 17], dtype=np.int64)
        self.hi_ks = np.array([4, 4, 4], dtype=np.int64)
        self.entropy_weight = 0.35

    def test_output_shape(self):
        cands = np.arange(100, dtype=np.uint32)
        scores = _numpy_score_array(cands, self.hi_primes, self.hi_ks, self.entropy_weight)
        assert scores.shape == (100,)

    def test_output_dtype(self):
        cands = np.arange(100, dtype=np.uint32)
        scores = _numpy_score_array(cands, self.hi_primes, self.hi_ks, self.entropy_weight)
        assert scores.dtype == np.float64

    def test_deterministic(self):
        cands = np.arange(500, dtype=np.uint32)
        a = _numpy_score_array(cands, self.hi_primes, self.hi_ks, self.entropy_weight)
        b = _numpy_score_array(cands, self.hi_primes, self.hi_ks, self.entropy_weight)
        np.testing.assert_array_equal(a, b)

    def test_scores_non_negative(self):
        cands = np.arange(1000, dtype=np.uint32)
        scores = _numpy_score_array(cands, self.hi_primes, self.hi_ks, self.entropy_weight)
        assert np.all(scores >= 0.0)

    def test_no_nans(self):
        cands = np.arange(1000, dtype=np.uint32)
        scores = _numpy_score_array(cands, self.hi_primes, self.hi_ks, self.entropy_weight)
        assert not np.any(np.isnan(scores))

    def test_no_infinities(self):
        cands = np.arange(1000, dtype=np.uint32)
        scores = _numpy_score_array(cands, self.hi_primes, self.hi_ks, self.entropy_weight)
        assert not np.any(np.isinf(scores))

    def test_zero_entropy_weight(self):
        """With entropy_weight=0, scores should be purely residue-based."""
        cands = np.arange(100, dtype=np.uint32)
        scores_with = _numpy_score_array(cands, self.hi_primes, self.hi_ks, 0.35)
        scores_without = _numpy_score_array(cands, self.hi_primes, self.hi_ks, 0.0)
        # Scores without entropy should be different (lower)
        assert not np.array_equal(scores_with, scores_without)
        # Without entropy weight, scores should be smaller on average
        assert np.mean(scores_without) < np.mean(scores_with)

    def test_large_batch(self):
        cands = np.arange(100_000, dtype=np.uint32)
        scores = _numpy_score_array(cands, self.hi_primes, self.hi_ks, self.entropy_weight)
        assert scores.shape == (100_000,)
        assert np.all(np.isfinite(scores))


# ═════════════════════════════════════════════════════════════════════════
# PadicLadderConfig
# ═════════════════════════════════════════════════════════════════════════

class TestPadicLadderConfig:

    def test_default_stages(self):
        cfg = PadicLadderConfig()
        assert len(cfg.stages) == 4
        assert cfg.stages[0] == (2, 12, 0.30)

    def test_default_hi_primes(self):
        cfg = PadicLadderConfig()
        assert cfg.hi_primes == [11, 13, 17]

    def test_default_entropy_weight(self):
        cfg = PadicLadderConfig()
        assert cfg.entropy_weight == 0.35

    def test_custom_config(self):
        cfg = PadicLadderConfig(
            stages=[(2, 8, 0.5), (3, 6, 0.5)],
            hi_primes=[7, 11],
            hi_powers=[3, 3],
            entropy_weight=0.5,
        )
        assert len(cfg.stages) == 2
        assert cfg.entropy_weight == 0.5


# ═════════════════════════════════════════════════════════════════════════
# PadicLadderStrategy
# ═════════════════════════════════════════════════════════════════════════

class TestPadicLadderStrategy:

    def setup_method(self):
        self.strategy = PadicLadderStrategy()

    def test_output_shape(self):
        nonces = np.arange(500, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.shape == (500,)

    def test_output_dtype(self):
        nonces = np.arange(500, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.dtype == np.float64

    def test_deterministic(self):
        nonces = np.arange(200, dtype=np.uint32)
        a = self.strategy.execute(nonces)
        b = self.strategy.execute(nonces)
        np.testing.assert_array_equal(a, b)

    def test_scores_non_negative(self):
        nonces = np.arange(1000, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert np.all(scores >= 0.0)

    def test_no_anomalies(self):
        nonces = np.arange(1000, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert np.all(np.isfinite(scores))

    def test_hardware_target(self):
        assert self.strategy.get_hardware_target() == "CPU_PADIC_LADDER"

    def test_diagnostics_structure(self):
        nonces = np.arange(100, dtype=np.uint32)
        self.strategy.execute(nonces)

        diag = self.strategy.get_diagnostics()
        assert diag["target"] == "CPU_PADIC_LADDER"
        assert isinstance(diag["numba_available"], bool)
        assert isinstance(diag["stages"], list)
        assert diag["hi_primes"] == [11, 13, 17]
        assert diag["hi_powers"] == [4, 4, 4]
        assert diag["entropy_weight"] == 0.35
        assert diag["call_count"] == 1
        assert diag["avg_ms"] >= 0

    def test_call_count_increments(self):
        nonces = np.arange(10, dtype=np.uint32)
        self.strategy.execute(nonces)
        self.strategy.execute(nonces)
        self.strategy.execute(nonces)
        assert self.strategy.get_diagnostics()["call_count"] == 3

    def test_custom_config_applied(self):
        cfg = PadicLadderConfig(
            hi_primes=[7, 11],
            hi_powers=[3, 3],
            entropy_weight=0.5,
        )
        strat = PadicLadderStrategy(cfg)
        diag = strat.get_diagnostics()
        assert diag["hi_primes"] == [7, 11]
        assert diag["entropy_weight"] == 0.5

    def test_large_batch(self):
        nonces = np.arange(50_000, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.shape == (50_000,)
        assert np.all(np.isfinite(scores))
