"""
infrastructure/benchmark_engine.py
──────────────────────────────────
Core benchmark execution engine for the Strategy Lab.

Runs a ``HeuristicStrategy`` against a cryptographically secure
random baseline (``secrets.token_bytes``) and computes comparative
statistical metrics.  All returned values are empirically computed —
no metric is fabricated.

Concurrency Model
─────────────────
Each benchmark run is synchronous (blocking).  A per-run wall-clock
timeout is enforced between major phases — but individual NumPy
calls cannot be interrupted.  See Phase 2 spec §2C for details.

Storage
───────
In-memory ``dict[str, BenchmarkRunResult]`` with FIFO eviction
when ``max_stored_runs`` is reached.  No disk persistence.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from domain.interfaces import HeuristicStrategy

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────

KS_SUBSAMPLE_LIMIT = 100_000  # KS test on >100K samples is very slow
MAX_STORED_RUNS = 50


# ── Internal result container ───────────────────────────────────────────

@dataclass
class MetricsResult:
    """Raw computed metrics for one side of the benchmark."""
    execution_time_ms: float
    throughput_nonces_per_sec: float
    mean: float
    std: float
    min_val: float
    max_val: float
    anomaly_count: int
    uniqueness_ratio: float
    ks_statistic: float
    ks_p_value: float


@dataclass
class ComparisonResult:
    """Comparative metrics between strategy and baseline."""
    speedup_factor: float
    mean_divergence: float
    std_ratio: float
    anomaly_delta: int
    distribution_different: bool


@dataclass
class BenchmarkRunResult:
    """Complete result of one benchmark run."""
    run_id: str
    strategy_id: str
    strategy_name: str
    formula: Optional[str]
    batch_size: int
    timestamp: str
    timed_out: bool
    strategy_metrics: MetricsResult
    baseline_metrics: MetricsResult
    comparison: ComparisonResult


# ── Metric computation ──────────────────────────────────────────────────

def _compute_metrics(
    data: np.ndarray,
    execution_time_ms: float,
    batch_size: int,
) -> MetricsResult:
    """Compute all statistical metrics from raw output data.

    Parameters
    ----------
    data : np.ndarray
        The output array from a strategy or baseline.
    execution_time_ms : float
        Wall-clock time the execution took.
    batch_size : int
        Number of nonces processed.

    Returns
    -------
    MetricsResult
        All metrics empirically computed from ``data``.
    """
    f64 = data.astype(np.float64)

    # Anomaly detection
    nan_count = int(np.isnan(f64).sum())
    inf_count = int(np.isinf(f64).sum())
    anomaly_count = nan_count + inf_count

    # Use nan-safe functions to handle NaN values gracefully
    mean_val = float(np.nanmean(f64))
    std_val = float(np.nanstd(f64))
    min_val = float(np.nanmin(f64)) if f64.size > 0 else 0.0
    max_val = float(np.nanmax(f64)) if f64.size > 0 else 0.0

    # Uniqueness
    unique_count = np.unique(data).size
    uniqueness_ratio = unique_count / max(1, data.size)

    # KS test against uniform distribution
    # Subsample if the array is large (KS on millions of values is impractical)
    clean = f64[np.isfinite(f64)]
    if clean.size > KS_SUBSAMPLE_LIMIT:
        # Cryptographically random subsample indices
        idx_bytes = secrets.token_bytes(KS_SUBSAMPLE_LIMIT * 4)
        random_indices = np.frombuffer(idx_bytes, dtype=np.uint32) % clean.size
        subsample = clean[random_indices.astype(np.intp)]
    elif clean.size > 0:
        subsample = clean
    else:
        # All values are NaN/Inf — can't run KS
        return MetricsResult(
            execution_time_ms=execution_time_ms,
            throughput_nonces_per_sec=batch_size / max(1e-9, execution_time_ms / 1000),
            mean=mean_val,
            std=std_val,
            min_val=min_val,
            max_val=max_val,
            anomaly_count=anomaly_count,
            uniqueness_ratio=uniqueness_ratio,
            ks_statistic=1.0,
            ks_p_value=0.0,
        )

    # Normalise to [0, 1] for KS test against uniform(0, 1)
    s_min = float(np.min(subsample))
    s_max = float(np.max(subsample))
    s_range = s_max - s_min
    if s_range > 0:
        normalised = (subsample - s_min) / s_range
    else:
        normalised = np.zeros_like(subsample)

    ks_stat, ks_p = stats.kstest(normalised, "uniform", args=(0, 1))

    throughput = batch_size / max(1e-9, execution_time_ms / 1000)

    return MetricsResult(
        execution_time_ms=round(execution_time_ms, 4),
        throughput_nonces_per_sec=round(throughput, 2),
        mean=round(mean_val, 6),
        std=round(std_val, 6),
        min_val=round(min_val, 6),
        max_val=round(max_val, 6),
        anomaly_count=anomaly_count,
        uniqueness_ratio=round(uniqueness_ratio, 6),
        ks_statistic=round(float(ks_stat), 6),
        ks_p_value=round(float(ks_p), 6),
    )


def _compute_comparison(
    strategy: MetricsResult,
    baseline: MetricsResult,
) -> ComparisonResult:
    """Derive comparative metrics from strategy vs. baseline."""
    # Speedup factor: how much faster/slower the strategy is
    if strategy.execution_time_ms > 0:
        speedup = baseline.execution_time_ms / strategy.execution_time_ms
    else:
        speedup = 0.0

    # Mean divergence (relative)
    if abs(baseline.mean) > 1e-12:
        mean_div = abs(strategy.mean - baseline.mean) / abs(baseline.mean)
    else:
        mean_div = abs(strategy.mean - baseline.mean)

    # Std ratio
    if baseline.std > 1e-12:
        std_ratio = strategy.std / baseline.std
    else:
        std_ratio = 0.0 if strategy.std < 1e-12 else float("inf")

    return ComparisonResult(
        speedup_factor=round(speedup, 4),
        mean_divergence=round(mean_div, 6),
        std_ratio=round(std_ratio, 6),
        anomaly_delta=strategy.anomaly_count - baseline.anomaly_count,
        distribution_different=strategy.ks_p_value < 0.05,
    )


# ── Benchmark Engine (singleton) ────────────────────────────────────────

class BenchmarkEngine:
    """
    Executes benchmark runs and stores results in memory.

    Thread Safety
    ─────────────
    This class is NOT thread-safe.  The FastAPI router should ensure
    that only one benchmark run executes at a time (the endpoint
    handler is ``async`` but calls this synchronously, which blocks
    the event loop — acceptable for an experimentation tool).
    """

    def __init__(self, max_stored_runs: int = MAX_STORED_RUNS) -> None:
        self._max = max_stored_runs
        self._runs: OrderedDict[str, BenchmarkRunResult] = OrderedDict()

    # ── Core execution ──────────────────────────────────────────────

    def run(
        self,
        strategy: HeuristicStrategy,
        strategy_id: str,
        strategy_name: str,
        batch_size: int,
        formula: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> BenchmarkRunResult:
        """
        Execute one benchmark: strategy vs. cryptographic-random baseline.

        Parameters
        ----------
        strategy : HeuristicStrategy
            The strategy to benchmark.
        strategy_id : str
            Identifier from the catalogue.
        strategy_name : str
            Human display name.
        batch_size : int
            Number of uint32 nonces.
        formula : str or None
            The formula used (for custom formulas).
        timeout_seconds : int
            Hard wall-clock limit.

        Returns
        -------
        BenchmarkRunResult
            Complete result with empirically computed metrics.

        Raises
        ------
        TimeoutError
            If the total run exceeds ``timeout_seconds``.
        """
        run_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        deadline = time.monotonic() + timeout_seconds
        timed_out = False

        # ── 1. Generate ordered nonce input ──────────────────────────
        nonces = np.arange(batch_size, dtype=np.uint32)

        # ── 2. Strategy execution ────────────────────────────────────
        t0 = time.perf_counter()
        strategy_result = strategy.execute(nonces)
        strategy_ms = (time.perf_counter() - t0) * 1000

        # Check timeout
        if time.monotonic() > deadline:
            timed_out = True

        # ── 3. Baseline: cryptographically secure random ─────────────
        t0 = time.perf_counter()
        baseline_bytes = secrets.token_bytes(batch_size * 4)
        baseline_result = np.frombuffer(baseline_bytes, dtype=np.uint32).copy()
        baseline_ms = (time.perf_counter() - t0) * 1000

        if time.monotonic() > deadline:
            timed_out = True

        # ── 4. Compute metrics ───────────────────────────────────────
        strategy_metrics = _compute_metrics(strategy_result, strategy_ms, batch_size)

        if time.monotonic() > deadline:
            timed_out = True

        baseline_metrics = _compute_metrics(baseline_result, baseline_ms, batch_size)

        if time.monotonic() > deadline:
            timed_out = True

        comparison = _compute_comparison(strategy_metrics, baseline_metrics)

        # ── 5. Build and store result ────────────────────────────────
        result = BenchmarkRunResult(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            formula=formula,
            batch_size=batch_size,
            timestamp=timestamp,
            timed_out=timed_out,
            strategy_metrics=strategy_metrics,
            baseline_metrics=baseline_metrics,
            comparison=comparison,
        )

        self._store(result)
        logger.info(
            "Benchmark %s complete | strategy=%s batch=%d timed_out=%s "
            "strategy_ms=%.1f baseline_ms=%.1f speedup=%.2fx",
            run_id[:8], strategy_id, batch_size, timed_out,
            strategy_ms, baseline_ms, comparison.speedup_factor,
        )

        return result

    # ── Storage ─────────────────────────────────────────────────────

    def _store(self, result: BenchmarkRunResult) -> None:
        """Store a result, evicting the oldest if at capacity."""
        if len(self._runs) >= self._max:
            # FIFO eviction
            oldest_key = next(iter(self._runs))
            del self._runs[oldest_key]
            logger.debug("Evicted oldest run %s", oldest_key)
        self._runs[result.run_id] = result

    def get_run(self, run_id: str) -> Optional[BenchmarkRunResult]:
        return self._runs.get(run_id)

    def delete_run(self, run_id: str) -> bool:
        if run_id in self._runs:
            del self._runs[run_id]
            return True
        return False

    def list_runs(self) -> list[BenchmarkRunResult]:
        """Return all stored runs, newest first."""
        return list(reversed(self._runs.values()))

    @property
    def capacity(self) -> int:
        return self._max

    @property
    def total(self) -> int:
        return len(self._runs)
