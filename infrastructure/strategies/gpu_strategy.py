"""
infrastructure/strategies/gpu_strategy.py
─────────────────────────────────────────
HeuristicStrategy adapter wrapping the existing GPUParallelSplitter
for Numba CUDA kernel dispatch.

Like the FPGA strategy, this is an AOT-compiled path and does **not**
support runtime formula injection.  Dynamic strings must be routed to
DynamicCPUStrategy.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

import numpy as np

from domain.interfaces import HeuristicStrategy

logger = logging.getLogger(__name__)

# Lazy import
_GPUSplitter = None


def _ensure_splitter():
    global _GPUSplitter
    if _GPUSplitter is None:
        from layer2_execution.gpu_parallel_splitter import GPUParallelSplitter
        _GPUSplitter = GPUParallelSplitter


class HardwareGPUStrategy(HeuristicStrategy):
    """
    Interfaces with the Numba CUDA SHA-256d kernel across 10× H100 SXM
    devices.  Falls back to CPU batch processing if CUDA is unavailable.

    Construction accepts an optional pre-built ``GPUParallelSplitter``
    instance; otherwise one is created lazily.
    """

    def __init__(
        self,
        splitter_instance=None,
        *,
        header_bytes: bytes = b"",
        target: int = 2**256 - 1,
    ):
        _ensure_splitter()
        self._splitter = splitter_instance
        self._header = header_bytes
        self._target = target
        self._total_processed = 0
        logger.info(
            "HardwareGPUStrategy initialised (splitter=%s)",
            type(self._splitter).__name__ if self._splitter else "deferred",
        )

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        if self._splitter is None:
            raise RuntimeError(
                "GPUParallelSplitter not initialised.  Supply a live "
                "instance or call initialise() first."
            )
        t0 = time.perf_counter()

        start = int(nonces[0])
        count = len(nonces)
        result = self._splitter.dispatch(
            self._header, start, count, self._target
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._total_processed += count
        logger.debug(
            "GPU dispatch: %d nonces in %.1f ms", count, elapsed_ms
        )
        return np.asarray(result, dtype=np.uint32)

    def get_hardware_target(self) -> str:
        return "GPU_CUDA"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "target": self.get_hardware_target(),
            "total_processed": self._total_processed,
            "splitter_active": self._splitter is not None,
        }
