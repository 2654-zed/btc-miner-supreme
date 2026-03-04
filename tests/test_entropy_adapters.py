"""
tests/test_entropy_adapters.py
──────────────────────────────
Unit tests for the Strategy Lab entropy adapter strategies.

Each adapter wraps a Layer 1 scoring module as a ``HeuristicStrategy``.
Tests verify:
  • Output shape and dtype (float64 scores)
  • No NaN / Inf anomalies
  • Hardware target strings
  • Diagnostics dict structure
  • Call count / timing tracking

Run:  pytest tests/test_entropy_adapters.py -v
"""

from __future__ import annotations

import numpy as np
import pytest

from infrastructure.strategies.entropy_adapter import (
    GriffinScoringStrategy,
    ObserverScoringStrategy,
    ZetaScoringStrategy,
)


# ═════════════════════════════════════════════════════════════════════════
# GriffinScoringStrategy
# ═════════════════════════════════════════════════════════════════════════

class TestGriffinScoringStrategy:

    def setup_method(self):
        self.strategy = GriffinScoringStrategy()

    def test_output_shape(self):
        nonces = np.arange(500, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.shape == (500,)

    def test_output_dtype(self):
        nonces = np.arange(500, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.dtype == np.float64

    def test_no_anomalies(self):
        nonces = np.arange(1000, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert np.all(np.isfinite(scores))

    def test_hardware_target(self):
        assert self.strategy.get_hardware_target() == "CPU_GRIFFIN_962"

    def test_diagnostics_structure(self):
        nonces = np.arange(100, dtype=np.uint32)
        self.strategy.execute(nonces)

        diag = self.strategy.get_diagnostics()
        assert diag["target"] == "CPU_GRIFFIN_962"
        assert "attractor_constant" in diag
        assert "basin_width" in diag
        assert "harmonic_depth" in diag
        assert diag["call_count"] == 1
        assert diag["avg_ms"] >= 0

    def test_call_count_increments(self):
        nonces = np.arange(10, dtype=np.uint32)
        self.strategy.execute(nonces)
        self.strategy.execute(nonces)
        assert self.strategy.get_diagnostics()["call_count"] == 2

    def test_custom_params(self):
        strat = GriffinScoringStrategy(
            attractor_constant=0.01,
            basin_width=0.001,
            harmonic_depth=4,
        )
        diag = strat.get_diagnostics()
        assert diag["attractor_constant"] == 0.01
        assert diag["basin_width"] == 0.001
        assert diag["harmonic_depth"] == 4


# ═════════════════════════════════════════════════════════════════════════
# ZetaScoringStrategy
# ═════════════════════════════════════════════════════════════════════════

class TestZetaScoringStrategy:

    def setup_method(self):
        self.strategy = ZetaScoringStrategy()

    def test_output_shape(self):
        nonces = np.arange(500, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.shape == (500,)

    def test_output_dtype(self):
        nonces = np.arange(500, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.dtype == np.float64

    def test_no_anomalies(self):
        nonces = np.arange(1000, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert np.all(np.isfinite(scores))

    def test_hardware_target(self):
        assert self.strategy.get_hardware_target() == "CPU_ZETA_CRITICAL"

    def test_diagnostics_structure(self):
        nonces = np.arange(100, dtype=np.uint32)
        self.strategy.execute(nonces)

        diag = self.strategy.get_diagnostics()
        assert diag["target"] == "CPU_ZETA_CRITICAL"
        assert "filter_tolerance" in diag
        assert diag["call_count"] == 1
        assert diag["avg_ms"] >= 0

    def test_call_count_increments(self):
        nonces = np.arange(10, dtype=np.uint32)
        self.strategy.execute(nonces)
        self.strategy.execute(nonces)
        self.strategy.execute(nonces)
        assert self.strategy.get_diagnostics()["call_count"] == 3

    def test_custom_tolerance(self):
        strat = ZetaScoringStrategy(filter_tolerance=1e-3)
        diag = strat.get_diagnostics()
        assert diag["filter_tolerance"] == 1e-3


# ═════════════════════════════════════════════════════════════════════════
# ObserverScoringStrategy
# ═════════════════════════════════════════════════════════════════════════

class TestObserverScoringStrategy:

    def setup_method(self):
        self.strategy = ObserverScoringStrategy()

    def test_output_shape(self):
        nonces = np.arange(500, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.shape == (500,)

    def test_output_dtype(self):
        nonces = np.arange(500, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert scores.dtype == np.float64

    def test_no_anomalies(self):
        nonces = np.arange(1000, dtype=np.uint32)
        scores = self.strategy.execute(nonces)
        assert np.all(np.isfinite(scores))

    def test_hardware_target(self):
        assert self.strategy.get_hardware_target() == "CPU_OBSERVER_LADDER"

    def test_diagnostics_structure(self):
        nonces = np.arange(100, dtype=np.uint32)
        self.strategy.execute(nonces)

        diag = self.strategy.get_diagnostics()
        assert diag["target"] == "CPU_OBSERVER_LADDER"
        assert "recursion_depth" in diag
        assert "convergence_threshold" in diag
        assert diag["call_count"] == 1
        assert diag["avg_ms"] >= 0

    def test_call_count_increments(self):
        nonces = np.arange(10, dtype=np.uint32)
        self.strategy.execute(nonces)
        self.strategy.execute(nonces)
        assert self.strategy.get_diagnostics()["call_count"] == 2

    def test_custom_params(self):
        strat = ObserverScoringStrategy(
            recursion_depth=3,
            convergence_threshold=0.5,
        )
        diag = strat.get_diagnostics()
        assert diag["recursion_depth"] == 3
        assert diag["convergence_threshold"] == 0.5
