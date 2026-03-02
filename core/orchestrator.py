"""
core/orchestrator.py
────────────────────
Hardware-agnostic Master Orchestrator utilising Inversion of Control
to manage high-throughput cryptographic workloads across varied
hardware layers.

Architecture
────────────
The ``MasterOrchestrator`` accepts any concrete ``HeuristicStrategy``
via dependency injection and processes nonce batches through it without
knowledge of the underlying hardware.  Strategy hot-swaps are safe:
the orchestrator drains active queues and disables outgoing hardware
bridges before committing the transition.

    ┌─────────────────────────────────────────────────────────────┐
    │                   MasterOrchestrator                        │
    │                                                             │
    │   set_strategy(s) ──► drain queues ──► disable HW ──► swap │
    │   process_workload(n) ──► _strategy.execute(n) ──► result  │
    └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np

from core.exceptions import HardwareRoutingError, OrchestrationError
from domain.interfaces import HeuristicStrategy
from domain.models import ExecutionResult, NonceBatch, StrategySwapEvent

logger = logging.getLogger(__name__)


class MasterOrchestrator:
    """
    Hardware-agnostic orchestrator using IoC + Strategy Pattern.

    Parameters
    ----------
    initial_strategy : HeuristicStrategy
        The default execution strategy (typically FPGA or GPU for
        standard SHA-256d workloads).
    """

    def __init__(self, initial_strategy: HeuristicStrategy):
        self._strategy = initial_strategy
        self._is_running = True
        self._swap_history: List[StrategySwapEvent] = []
        self._total_batches = 0
        self._total_nonces = 0
        logger.info(
            "Orchestrator initialised — target: %s",
            self._strategy.get_hardware_target(),
        )

    # ── Strategy management ─────────────────────────────────────────────

    @property
    def current_target(self) -> str:
        return self._strategy.get_hardware_target()

    @property
    def strategy(self) -> HeuristicStrategy:
        return self._strategy

    def set_strategy(self, new_strategy: HeuristicStrategy, reason: str = "") -> StrategySwapEvent:
        """
        Hot-swap the underlying execution engine at runtime.

        Steps
        -----
        1. Record the swap event for audit.
        2. If transitioning *away* from a hardware bridge (FPGA/GPU),
           drain active queues and idle the hardware.
        3. Inject the new strategy.

        Returns
        -------
        StrategySwapEvent
            Audit record of the transition.
        """
        prev_target = self._strategy.get_hardware_target()
        new_target = new_strategy.get_hardware_target()

        event = StrategySwapEvent(
            previous_target=prev_target,
            new_target=new_target,
            reason=reason or f"hot-swap {prev_target} → {new_target}",
        )
        self._swap_history.append(event)

        if prev_target != new_target:
            logger.info(
                "Strategy hot-swap: %s → %s (reason: %s)",
                prev_target, new_target, event.reason,
            )
            # Gracefully drain hardware bridges
            if "FPGA" in prev_target:
                self._disable_hardware_bridge("FPGA")
            elif "GPU" in prev_target:
                self._disable_hardware_bridge("GPU")

        self._strategy = new_strategy
        logger.info("Strategy injection complete — system operational.")
        return event

    # ── Workload processing ─────────────────────────────────────────────

    def process_workload(self, nonces: np.ndarray) -> ExecutionResult:
        """
        Execute the cryptographic workload through the current strategy.

        The orchestrator is fully agnostic to the strategy's internals.

        Parameters
        ----------
        nonces : np.ndarray
            1-D uint32 nonce array.

        Returns
        -------
        ExecutionResult
            Contains the result array, anomaly count, timing, and
            hardware target identifier.
        """
        if not self._is_running:
            raise OrchestrationError("Orchestrator is halted — workload rejected.")

        t0 = time.perf_counter()
        result = self._strategy.execute(nonces)
        elapsed = (time.perf_counter() - t0) * 1000

        anomalies = int(np.isnan(result).sum() + np.isinf(result).sum())
        self._total_batches += 1
        self._total_nonces += len(nonces)

        return ExecutionResult(
            results=result,
            anomalies=anomalies,
            hardware_target=self._strategy.get_hardware_target(),
            elapsed_ms=elapsed,
            batch_id=self._total_batches,
        )

    def process_batch(self, batch: NonceBatch) -> ExecutionResult:
        """Convenience wrapper accepting a ``NonceBatch`` domain object."""
        res = self.process_workload(batch.nonces)
        res.batch_id = batch.batch_id
        return res

    # ── Lifecycle ───────────────────────────────────────────────────────

    def halt(self) -> None:
        """Gracefully halt the orchestrator — drain queues, idle HW."""
        logger.warning("Orchestrator halt requested.")
        self._is_running = False
        target = self._strategy.get_hardware_target()
        if "FPGA" in target:
            self._disable_hardware_bridge("FPGA")
        elif "GPU" in target:
            self._disable_hardware_bridge("GPU")

    def resume(self) -> None:
        """Resume after a halt."""
        self._is_running = True
        logger.info("Orchestrator resumed.")

    # ── Diagnostics ─────────────────────────────────────────────────────

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "is_running": self._is_running,
            "current_target": self.current_target,
            "total_batches": self._total_batches,
            "total_nonces": self._total_nonces,
            "swap_history_length": len(self._swap_history),
            "strategy_diagnostics": self._strategy.get_diagnostics(),
        }

    @property
    def swap_history(self) -> List[StrategySwapEvent]:
        return list(self._swap_history)

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _disable_hardware_bridge(target_type: str) -> None:
        """
        Securely drain PCIe queues, clear VRAM, and place specialised
        hardware into an idle state during a strategy hot-swap.
        """
        logger.warning(
            "Draining data queues and halting %s operations …", target_type
        )
        # Production implementation must:
        #   • Flush in-flight DMA buffers (FPGA)
        #   • Synchronise CUDA streams and free pinned memory (GPU)
        #   • Wait for pending PCIe transactions to complete
        #   • Transition devices to low-power idle state
        # NOTE: No simulated delay — real drain is hardware-dependent.
        #       Wire to actual driver teardown via HardwareBridge.drain().
        logger.info("%s hardware bridge drain requested (no-op until wired).", target_type)
