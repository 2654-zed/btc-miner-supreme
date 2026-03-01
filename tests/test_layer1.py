"""
test_layer1.py
──────────────
Unit tests for the Layer-1 entropy shaping modules.
"""

import hashlib
import numpy as np
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════
# Griffin Entropy Weaver
# ═══════════════════════════════════════════════════════════════════════════
from layer1_entropy.griffin962_entropy_weaver import GriffinEntropyWeaver, GriffinConfig


class TestGriffinWeaver:
    def setup_method(self):
        self.cfg = GriffinConfig(
            seed_mode="deterministic",
            deterministic_seed=42,
            harmonic_depth=8,
        )
        self.weaver = GriffinEntropyWeaver(self.cfg)

    def test_basins_count(self):
        assert len(self.weaver.basins) == self.cfg.harmonic_depth

    def test_basin_weights_normalised(self):
        total = sum(b.weight for b in self.weaver.basins)
        assert abs(total - 1.0) < 1e-9

    def test_weave_shape(self):
        candidates = self.weaver.weave(1000)
        assert candidates.shape == (1000,)
        assert candidates.dtype == np.uint32

    def test_weave_deterministic(self):
        a = GriffinEntropyWeaver(self.cfg).weave(100)
        b = GriffinEntropyWeaver(self.cfg).weave(100)
        np.testing.assert_array_equal(a, b)

    def test_weave_scored_length(self):
        scored = self.weaver.weave_scored(500)
        assert len(scored) == 500
        for nonce, score in scored:
            assert 0 <= score <= 1.0

    def test_reseed_changes_output(self):
        before = self.weaver.weave(100)
        self.weaver.reseed(b"\x00" * 32)
        after = self.weaver.weave(100)
        # After reseed, output should differ (overwhelmingly likely)
        assert not np.array_equal(before, after)


# ═══════════════════════════════════════════════════════════════════════════
# Zeta-Aligned Symbolic Router
# ═══════════════════════════════════════════════════════════════════════════
from layer1_entropy.zeta_aligned_symbolic_router import (
    ZetaAlignedSymbolicRouter, ZetaRouterConfig,
)


class TestZetaRouter:
    def setup_method(self):
        self.router = ZetaAlignedSymbolicRouter(ZetaRouterConfig(zero_cache_size=500))

    def test_zeros_populated(self):
        assert len(self.router._zeros) > 0

    def test_score_shape(self):
        nonces = np.random.randint(0, 2**32, size=1000, dtype=np.uint32)
        scores = self.router.score(nonces)
        assert scores.shape == (1000,)

    def test_score_range(self):
        nonces = np.random.randint(0, 2**32, size=500, dtype=np.uint32)
        scores = self.router.score(nonces)
        assert np.all(scores >= 0)
        assert np.all(scores <= 1.0)

    def test_route_filters(self):
        nonces = np.random.randint(0, 2**32, size=10_000, dtype=np.uint32)
        passed = self.router.route(nonces, threshold=0.5)
        assert len(passed) <= len(nonces)

    def test_zero_density(self):
        d = self.router.zero_density_at(1000.0)
        assert d > 0


# ═══════════════════════════════════════════════════════════════════════════
# Observer Ladder
# ═══════════════════════════════════════════════════════════════════════════
from layer1_entropy.observer_ladder_replay import ObserverLadder, ObserverConfig


class TestObserverLadder:
    def setup_method(self):
        self.obs = ObserverLadder(ObserverConfig(recursion_depth=3, ladder_width=16))

    def test_initial_score_uniform(self):
        nonces = np.arange(100, dtype=np.uint32)
        scores = self.obs.score(nonces)
        # Before any recording, all scores should be identical
        assert len(np.unique(scores)) <= 2  # might have tiny FP diffs

    def test_record_block_updates_scores(self):
        self.obs.record_block(12345)
        self.obs.record_block(12345)
        nonces = np.array([12345, 99999], dtype=np.uint32)
        scores = self.obs.score(nonces)
        # The winning nonce bin should score higher
        assert scores[0] >= scores[1]

    def test_rank_ordering(self):
        for _ in range(10):
            self.obs.record_block(42)
        nonces = np.array([42, 100, 200, 300], dtype=np.uint32)
        ranked = self.obs.rank(nonces)
        assert ranked[0] == 42

    def test_layer_summary(self):
        summary = self.obs.layer_summary()
        assert len(summary) == 3
        for s in summary:
            assert "entropy" in s
            assert "max_rate" in s


# ═══════════════════════════════════════════════════════════════════════════
# Collapse Cone Optimizer (integration)
# ═══════════════════════════════════════════════════════════════════════════
from layer1_entropy.collapse_cone_optimizer import CollapseConeOptimizer, CollapseConeConfig


class TestCollapseCone:
    def test_optimise_returns_candidates(self):
        cfg = CollapseConeConfig(max_candidates=1000)
        cone = CollapseConeOptimizer(cfg=cfg)
        result = cone.optimise(raw_count=2000)
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint32
        assert len(result) <= cfg.max_candidates

    def test_merge_strategies(self):
        for strategy in ("weighted_vote", "union"):
            cfg = CollapseConeConfig(max_candidates=500, merge_strategy=strategy)
            cone = CollapseConeOptimizer(cfg=cfg)
            result = cone.optimise(raw_count=1000)
            assert len(result) > 0

    def test_diagnostics(self):
        cone = CollapseConeOptimizer()
        diag = cone.source_diagnostics()
        assert "griffin" in diag
        assert "zeta" in diag
        assert "observer" in diag
