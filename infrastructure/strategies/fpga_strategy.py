"""
infrastructure/strategies/fpga_strategy.py
──────────────────────────────────────────
HeuristicStrategy adapter wrapping the existing FPGASHABridge for
standard AOT-compiled SHA-256d workloads.

This strategy does **not** support dynamic formula injection; it
delegates directly to the pre-compiled .xclbin bitstream.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

import numpy as np

from domain.interfaces import HeuristicStrategy
from core.exceptions import HardwareRoutingError

logger = logging.getLogger(__name__)

# Lazy import of the legacy bridge
_FPGABridge = None


def _ensure_bridge():
    global _FPGABridge
    if _FPGABridge is None:
        from layer2_execution.fpga_sha_bridge import FPGASHABridge
        _FPGABridge = FPGASHABridge


class HardwareFPGAStrategy(HeuristicStrategy):
    """
    Interfaces with the AOT-compiled .xclbin SHA-256d pipeline over
    PCIe DMA on Alveo UL3524 devices.

    Construction requires a live ``FPGASHABridge`` instance or the
    parameters needed to build one.  If XRT is unavailable, the bridge
    automatically falls back to CPU emulation — but the Strategy still
    reports itself as ``FPGA_BRIDGE``.
    """

    def __init__(
        self,
        bridge_instance=None,
        *,
        header_bytes: bytes = b"",
        target: int = 2**256 - 1,
        difficulty_bits: int = 0x1d00ffff,
    ):
        _ensure_bridge()
        self._bridge = bridge_instance
        self._header = header_bytes
        self._target = target
        self._difficulty_bits = difficulty_bits
        self._total_processed = 0
        logger.info("HardwareFPGAStrategy initialised (bridge=%s)", type(self._bridge).__name__ if self._bridge else "deferred")

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        """
        Dispatch nonces to the FPGA pipeline.  Returns SHA-256d
        hash results as a uint8 byte array.
        """
        if self._bridge is None:
            raise HardwareRoutingError(
                "FPGA bridge not initialised.  Supply a live "
                "FPGASHABridge instance or call initialise() first."
            )
        t0 = time.perf_counter()

        # The legacy bridge expects (header, start_nonce, count, target)
        start = int(nonces[0])
        count = len(nonces)
        result = self._bridge.dispatch(
            self._header, start, count, self._target
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._total_processed += count
        logger.debug(
            "FPGA dispatch: %d nonces in %.1f ms", count, elapsed_ms
        )
        return np.asarray(result, dtype=np.uint32)

    def get_hardware_target(self) -> str:
        return "FPGA_BRIDGE"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "target": self.get_hardware_target(),
            "total_processed": self._total_processed,
            "bridge_active": self._bridge is not None,
        }
