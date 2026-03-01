"""
entropy_core_balancer.py
────────────────────────
Dynamically scales the entropy batch allocation based on the number of
available CPU cores on the host.

The balancer ensures that the Layer-1 entropy pipeline saturates all
available cores without over-subscribing, and automatically adjusts
when cores become available or are taken by other workloads.

It also manages the balance between CPU-bound entropy generation and
GPU/FPGA-bound hashing to maximise pipeline throughput.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import psutil

logger = logging.getLogger(__name__)


@dataclass
class BalancerConfig:
    min_entropy_workers: int = 2
    max_entropy_workers: Optional[int] = None   # None → auto
    rebalance_interval_sec: int = 30
    target_cpu_util: float = 0.80                # aim for 80% utilisation
    batch_size_per_worker: int = 2**22           # nonces per worker batch
    headroom_cores: int = 2                      # reserve for OS / networking


class EntropyWorkerPool:
    """Lightweight abstraction over a pool of entropy generator threads."""

    def __init__(self, num_workers: int, batch_size: int) -> None:
        self.num_workers = num_workers
        self.batch_size = batch_size
        self._active = 0

    def scale_to(self, new_count: int) -> None:
        old = self.num_workers
        self.num_workers = new_count
        if old != new_count:
            logger.info("Worker pool scaled: %d → %d", old, new_count)

    @property
    def total_batch(self) -> int:
        return self.num_workers * self.batch_size


class EntropyCoreBalancer:
    """
    Monitors system load and dynamically adjusts the number of entropy
    weaver workers and their batch sizes to keep the pipeline at peak
    throughput.
    """

    def __init__(self, cfg: Optional[BalancerConfig] = None) -> None:
        self.cfg = cfg or BalancerConfig()

        self._total_cores = psutil.cpu_count(logical=True) or 4
        self._physical_cores = psutil.cpu_count(logical=False) or 2

        max_w = self.cfg.max_entropy_workers or max(
            self.cfg.min_entropy_workers,
            self._physical_cores - self.cfg.headroom_cores,
        )
        self.cfg.max_entropy_workers = max_w

        initial_workers = min(max_w, max(self.cfg.min_entropy_workers, self._physical_cores // 2))
        self.pool = EntropyWorkerPool(initial_workers, self.cfg.batch_size_per_worker)

        self._running = False
        self._thread: Optional[threading.Thread] = None

        logger.info(
            "EntropyCoreBalancer  | cores=%d/%d  workers=%d  range=[%d,%d]  interval=%ds",
            self._physical_cores, self._total_cores,
            self.pool.num_workers,
            self.cfg.min_entropy_workers, self.cfg.max_entropy_workers,
            self.cfg.rebalance_interval_sec,
        )

    # ── Auto-tuning loop ─────────────────────────────────────────────────
    def start(self) -> None:
        """Start the background rebalancing loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="core-balancer")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while self._running:
            try:
                self._rebalance()
            except Exception as exc:
                logger.warning("Rebalance error: %s", exc)
            time.sleep(self.cfg.rebalance_interval_sec)

    def _rebalance(self) -> None:
        """Adjust worker count based on current CPU utilisation."""
        cpu_pct = psutil.cpu_percent(interval=1.0) / 100.0
        current = self.pool.num_workers

        if cpu_pct < self.cfg.target_cpu_util * 0.8:
            # Under-utilised → scale up
            new_count = min(current + 1, self.cfg.max_entropy_workers)
        elif cpu_pct > self.cfg.target_cpu_util * 1.1:
            # Over-utilised → scale down
            new_count = max(current - 1, self.cfg.min_entropy_workers)
        else:
            new_count = current

        if new_count != current:
            self.pool.scale_to(new_count)
            logger.info(
                "Rebalanced: cpu=%.1f%%  workers %d → %d  total_batch=%d",
                cpu_pct * 100, current, new_count, self.pool.total_batch,
            )

    # ── Manual API ───────────────────────────────────────────────────────
    def recommended_batch_size(self) -> int:
        """Return the current total batch size for the entropy pipeline."""
        return self.pool.total_batch

    def set_workers(self, count: int) -> None:
        """Manually override worker count (clamped to config range)."""
        count = max(self.cfg.min_entropy_workers, min(count, self.cfg.max_entropy_workers))
        self.pool.scale_to(count)

    def snapshot(self) -> dict:
        """Return current balancer state for telemetry."""
        return {
            "workers": self.pool.num_workers,
            "batch_per_worker": self.pool.batch_size,
            "total_batch": self.pool.total_batch,
            "physical_cores": self._physical_cores,
            "logical_cores": self._total_cores,
            "cpu_percent": psutil.cpu_percent(interval=0),
            "memory_percent": psutil.virtual_memory().percent,
        }
