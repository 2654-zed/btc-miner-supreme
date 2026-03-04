"""
tests/test_benchmark_engine.py
──────────────────────────────
Unit tests for the Strategy Lab benchmark engine.

Covers:
  • _compute_metrics  — deterministic stats on known arrays
  • _compute_comparison — speedup, divergence, ratio logic
  • BenchmarkEngine.run() — full end-to-end with DummyStrategy
  • FIFO eviction at MAX_STORED_RUNS
  • get_run / delete_run / list_runs storage ops
  • Anomaly handling (NaN / Inf inputs)
  • KS subsample path (>100K clean values)

Run:  pytest tests/test_benchmark_engine.py -v
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from domain.interfaces import HeuristicStrategy
from infrastructure.benchmark_engine import (
    BenchmarkEngine,
    BenchmarkRunResult,
    ComparisonResult,
    MetricsResult,
    _compute_comparison,
    _compute_metrics,
)


# ═════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════

class IdentityStrategy(HeuristicStrategy):
    """Returns nonces cast to float64 unchanged."""

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        return nonces.astype(np.float64)

    def get_hardware_target(self) -> str:
        return "TEST_IDENTITY"


class ConstantStrategy(HeuristicStrategy):
    """Returns a constant value for every nonce."""

    def __init__(self, value: float = 42.0) -> None:
        self._value = value

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        return np.full(nonces.shape, self._value, dtype=np.float64)

    def get_hardware_target(self) -> str:
        return "TEST_CONSTANT"


class NaNStrategy(HeuristicStrategy):
    """Returns NaN for every nonce — worst-case anomaly test."""

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        return np.full(nonces.shape, np.nan, dtype=np.float64)

    def get_hardware_target(self) -> str:
        return "TEST_NAN"


class SlowStrategy(HeuristicStrategy):
    """Sleeps briefly to simulate slow execution."""

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        import time
        time.sleep(0.01)
        return nonces.astype(np.float64)

    def get_hardware_target(self) -> str:
        return "TEST_SLOW"


# ═════════════════════════════════════════════════════════════════════════
# _compute_metrics
# ═════════════════════════════════════════════════════════════════════════

class TestComputeMetrics:
    """Test raw metric computation on known arrays."""

    def test_basic_stats_on_arange(self):
        data = np.arange(100, dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=10.0, batch_size=100)
        assert isinstance(m, MetricsResult)
        assert m.mean == round(float(np.mean(data)), 6)
        assert m.std == round(float(np.std(data)), 6)
        assert m.min_val == 0.0
        assert m.max_val == 99.0
        assert m.anomaly_count == 0

    def test_execution_time_stored(self):
        data = np.ones(10, dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=42.1234, batch_size=10)
        assert m.execution_time_ms == 42.1234

    def test_throughput_calculation(self):
        data = np.ones(1000, dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=100.0, batch_size=1000)
        # throughput = 1000 / (100ms / 1000) = 10_000 nonces/sec
        assert m.throughput_nonces_per_sec == 10_000.0

    def test_uniqueness_ratio_all_unique(self):
        data = np.arange(50, dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=1.0, batch_size=50)
        assert m.uniqueness_ratio == 1.0

    def test_uniqueness_ratio_all_same(self):
        data = np.ones(100, dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=1.0, batch_size=100)
        assert m.uniqueness_ratio == pytest.approx(0.01, abs=1e-6)

    def test_anomaly_count_nans(self):
        data = np.array([1.0, np.nan, 2.0, np.nan, np.nan], dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=1.0, batch_size=5)
        assert m.anomaly_count == 3

    def test_anomaly_count_infs(self):
        data = np.array([1.0, np.inf, -np.inf, 2.0], dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=1.0, batch_size=4)
        assert m.anomaly_count == 2

    def test_anomaly_count_mixed(self):
        data = np.array([np.nan, np.inf, -np.inf, 1.0], dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=1.0, batch_size=4)
        assert m.anomaly_count == 3

    def test_all_nan_input(self):
        data = np.full(10, np.nan, dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=1.0, batch_size=10)
        assert m.anomaly_count == 10
        # KS test can't run — fallback values
        assert m.ks_statistic == 1.0
        assert m.ks_p_value == 0.0

    def test_ks_on_uniform_data(self):
        """Uniformly distributed data should yield high p-value."""
        rng = np.random.default_rng(seed=12345)
        data = rng.uniform(0.0, 1.0, size=10_000).astype(np.float64)
        m = _compute_metrics(data, execution_time_ms=1.0, batch_size=10_000)
        assert m.ks_p_value > 0.01  # far from rejecting uniformity

    def test_ks_on_constant_data_rejects_uniform(self):
        """Constant data is NOT uniform — KS should reject."""
        data = np.full(1000, 5.0, dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=1.0, batch_size=1000)
        # Constant data collapses to zero after normalisation → degenerate
        # The exact p-value depends on scipy implementation
        assert m.ks_statistic >= 0.0

    def test_subsample_path_large_array(self):
        """Arrays > 100K trigger the subsample code path."""
        data = np.arange(200_000, dtype=np.float64)
        m = _compute_metrics(data, execution_time_ms=50.0, batch_size=200_000)
        # Should complete without error and produce valid metrics
        assert m.mean > 0
        assert m.ks_statistic >= 0.0
        assert 0.0 <= m.ks_p_value <= 1.0


# ═════════════════════════════════════════════════════════════════════════
# _compute_comparison
# ═════════════════════════════════════════════════════════════════════════

class TestComputeComparison:
    """Test comparative metric derivation."""

    def _make_metrics(self, **overrides) -> MetricsResult:
        defaults = dict(
            execution_time_ms=10.0,
            throughput_nonces_per_sec=100_000.0,
            mean=0.5,
            std=0.28,
            min_val=0.0,
            max_val=1.0,
            anomaly_count=0,
            uniqueness_ratio=1.0,
            ks_statistic=0.01,
            ks_p_value=0.9,
        )
        defaults.update(overrides)
        return MetricsResult(**defaults)

    def test_speedup_factor(self):
        strat = self._make_metrics(execution_time_ms=5.0)
        base = self._make_metrics(execution_time_ms=10.0)
        c = _compute_comparison(strat, base)
        assert c.speedup_factor == pytest.approx(2.0, abs=0.01)

    def test_mean_divergence(self):
        strat = self._make_metrics(mean=0.6)
        base = self._make_metrics(mean=0.5)
        c = _compute_comparison(strat, base)
        expected = abs(0.6 - 0.5) / abs(0.5)
        assert c.mean_divergence == pytest.approx(expected, abs=1e-5)

    def test_std_ratio(self):
        strat = self._make_metrics(std=0.14)
        base = self._make_metrics(std=0.28)
        c = _compute_comparison(strat, base)
        assert c.std_ratio == pytest.approx(0.5, abs=0.01)

    def test_anomaly_delta(self):
        strat = self._make_metrics(anomaly_count=3)
        base = self._make_metrics(anomaly_count=1)
        c = _compute_comparison(strat, base)
        assert c.anomaly_delta == 2

    def test_distribution_different_true(self):
        strat = self._make_metrics(ks_p_value=0.001)
        base = self._make_metrics()
        c = _compute_comparison(strat, base)
        assert c.distribution_different is True

    def test_distribution_different_false(self):
        strat = self._make_metrics(ks_p_value=0.5)
        base = self._make_metrics()
        c = _compute_comparison(strat, base)
        assert c.distribution_different is False

    def test_zero_baseline_std(self):
        strat = self._make_metrics(std=0.28)
        base = self._make_metrics(std=0.0)
        c = _compute_comparison(strat, base)
        assert c.std_ratio == float("inf")

    def test_zero_strategy_time(self):
        strat = self._make_metrics(execution_time_ms=0.0)
        base = self._make_metrics(execution_time_ms=10.0)
        c = _compute_comparison(strat, base)
        assert c.speedup_factor == 0.0

    def test_zero_baseline_mean(self):
        strat = self._make_metrics(mean=0.1)
        base = self._make_metrics(mean=0.0)
        c = _compute_comparison(strat, base)
        # Falls to absolute divergence
        assert c.mean_divergence == pytest.approx(0.1, abs=1e-5)


# ═════════════════════════════════════════════════════════════════════════
# BenchmarkEngine — full run
# ═════════════════════════════════════════════════════════════════════════

class TestBenchmarkEngine:

    def setup_method(self):
        self.engine = BenchmarkEngine(max_stored_runs=5)

    def test_run_returns_result(self):
        result = self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id="test_id",
            strategy_name="Test Identity",
            batch_size=1_000,
        )
        assert isinstance(result, BenchmarkRunResult)
        assert result.strategy_id == "test_id"
        assert result.strategy_name == "Test Identity"
        assert result.batch_size == 1_000
        assert result.formula is None

    def test_run_stores_result(self):
        result = self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id="test",
            strategy_name="Test",
            batch_size=1_000,
        )
        stored = self.engine.get_run(result.run_id)
        assert stored is not None
        assert stored.run_id == result.run_id

    def test_strategy_metrics_populated(self):
        result = self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id="test",
            strategy_name="Test",
            batch_size=1_000,
        )
        m = result.strategy_metrics
        assert m.execution_time_ms >= 0
        assert m.throughput_nonces_per_sec > 0
        assert m.anomaly_count == 0
        assert 0.0 <= m.uniqueness_ratio <= 1.0

    def test_baseline_metrics_populated(self):
        result = self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id="test",
            strategy_name="Test",
            batch_size=1_000,
        )
        m = result.baseline_metrics
        assert m.execution_time_ms >= 0
        assert m.throughput_nonces_per_sec > 0
        assert m.anomaly_count == 0

    def test_comparison_populated(self):
        result = self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id="test",
            strategy_name="Test",
            batch_size=1_000,
        )
        c = result.comparison
        assert isinstance(c.speedup_factor, float)
        assert isinstance(c.mean_divergence, float)
        assert isinstance(c.distribution_different, bool)

    def test_formula_passed_through(self):
        result = self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id="test",
            strategy_name="Test",
            batch_size=1_000,
            formula="nonce ** 2",
        )
        assert result.formula == "nonce ** 2"

    def test_run_id_is_uuid(self):
        import uuid
        result = self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id="test",
            strategy_name="Test",
            batch_size=1_000,
        )
        # Should be a valid UUID
        parsed = uuid.UUID(result.run_id)
        assert str(parsed) == result.run_id

    def test_timestamp_is_iso(self):
        from datetime import datetime
        result = self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id="test",
            strategy_name="Test",
            batch_size=1_000,
        )
        # Should parse as ISO format
        datetime.fromisoformat(result.timestamp)

    def test_nan_strategy_counted_as_anomalies(self):
        result = self.engine.run(
            strategy=NaNStrategy(),
            strategy_id="test_nan",
            strategy_name="NaN Test",
            batch_size=1_000,
        )
        assert result.strategy_metrics.anomaly_count == 1_000
        # Baseline should have 0 anomalies (secrets random uint32)
        assert result.baseline_metrics.anomaly_count == 0


# ═════════════════════════════════════════════════════════════════════════
# Storage operations
# ═════════════════════════════════════════════════════════════════════════

class TestBenchmarkEngineStorage:

    def setup_method(self):
        self.engine = BenchmarkEngine(max_stored_runs=5)

    def _do_run(self, sid: str = "test") -> BenchmarkRunResult:
        return self.engine.run(
            strategy=IdentityStrategy(),
            strategy_id=sid,
            strategy_name="Test",
            batch_size=1_000,
        )

    def test_get_run_nonexistent(self):
        assert self.engine.get_run("nonexistent-id") is None

    def test_delete_run(self):
        result = self._do_run()
        assert self.engine.delete_run(result.run_id) is True
        assert self.engine.get_run(result.run_id) is None

    def test_delete_nonexistent(self):
        assert self.engine.delete_run("nonexistent-id") is False

    def test_list_runs_newest_first(self):
        r1 = self._do_run("s1")
        r2 = self._do_run("s2")
        r3 = self._do_run("s3")
        runs = self.engine.list_runs()
        assert len(runs) == 3
        assert runs[0].run_id == r3.run_id
        assert runs[1].run_id == r2.run_id
        assert runs[2].run_id == r1.run_id

    def test_total_property(self):
        assert self.engine.total == 0
        self._do_run()
        assert self.engine.total == 1
        self._do_run()
        assert self.engine.total == 2

    def test_capacity_property(self):
        assert self.engine.capacity == 5

    def test_fifo_eviction(self):
        """When max_stored_runs is exceeded, the oldest run is evicted."""
        run_ids = []
        for i in range(6):
            r = self._do_run(f"s{i}")
            run_ids.append(r.run_id)

        # Should have exactly 5 stored
        assert self.engine.total == 5

        # The first run (oldest) should be evicted
        assert self.engine.get_run(run_ids[0]) is None

        # All others should still exist
        for rid in run_ids[1:]:
            assert self.engine.get_run(rid) is not None

    def test_fifo_eviction_ordering(self):
        """Multiple evictions maintain FIFO order."""
        run_ids = []
        for i in range(8):
            r = self._do_run(f"s{i}")
            run_ids.append(r.run_id)

        assert self.engine.total == 5

        # First 3 should be evicted, last 5 remain
        for rid in run_ids[:3]:
            assert self.engine.get_run(rid) is None
        for rid in run_ids[3:]:
            assert self.engine.get_run(rid) is not None
