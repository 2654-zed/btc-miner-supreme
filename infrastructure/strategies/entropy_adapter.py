"""
infrastructure/strategies/entropy_adapter.py
────────────────────────────────────────────
Lightweight adapters wrapping Layer 1 entropy scoring modules as
``HeuristicStrategy`` implementations so they can be used inside the
Strategy Lab benchmark harness.

Each adapter's ``execute(nonces)`` method returns a **score array**
(float64) rather than a filtered subset — the benchmark engine needs
scores for every input nonce to compute statistical metrics.

Exported Classes
────────────────
    GriffinScoringStrategy(HeuristicStrategy)
    ZetaScoringStrategy(HeuristicStrategy)
    ObserverScoringStrategy(HeuristicStrategy)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import numpy as np

from domain.interfaces import HeuristicStrategy

logger = logging.getLogger(__name__)


# ─── Griffin-962 Adapter ────────────────────────────────────────────────

class GriffinScoringStrategy(HeuristicStrategy):
    """Wraps ``GriffinEntropyWeaver._score()`` as a HeuristicStrategy."""

    def __init__(
        self,
        attractor_constant: float = 1 / 962,
        basin_width: float = 0.0005,
        harmonic_depth: int = 8,
    ) -> None:
        from layer1_entropy.griffin962_entropy_weaver import (
            GriffinConfig,
            GriffinEntropyWeaver,
        )

        self._cfg = GriffinConfig(
            attractor_constant=attractor_constant,
            basin_width=basin_width,
            harmonic_depth=harmonic_depth,
        )
        self._weaver = GriffinEntropyWeaver(self._cfg)
        self._call_count = 0
        self._total_ms = 0.0

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        scores = self._weaver._score(nonces)
        self._total_ms += (time.perf_counter() - t0) * 1000
        self._call_count += 1
        return scores

    def get_hardware_target(self) -> str:
        return "CPU_GRIFFIN_962"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "target": self.get_hardware_target(),
            "attractor_constant": self._cfg.attractor_constant,
            "basin_width": self._cfg.basin_width,
            "harmonic_depth": self._cfg.harmonic_depth,
            "call_count": self._call_count,
            "avg_ms": round(self._total_ms / max(1, self._call_count), 2),
        }


# ─── Zeta-Critical Adapter ─────────────────────────────────────────────

class ZetaScoringStrategy(HeuristicStrategy):
    """Wraps ``ZetaAlignedSymbolicRouter.score()`` as a HeuristicStrategy."""

    def __init__(self, filter_tolerance: float = 1e-6) -> None:
        from layer1_entropy.zeta_aligned_symbolic_router import (
            ZetaAlignedSymbolicRouter,
            ZetaRouterConfig,
        )

        self._cfg = ZetaRouterConfig(filter_tolerance=filter_tolerance)
        self._router = ZetaAlignedSymbolicRouter(self._cfg)
        self._call_count = 0
        self._total_ms = 0.0

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        scores = self._router.score(nonces)
        self._total_ms += (time.perf_counter() - t0) * 1000
        self._call_count += 1
        return scores

    def get_hardware_target(self) -> str:
        return "CPU_ZETA_CRITICAL"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "target": self.get_hardware_target(),
            "filter_tolerance": self._cfg.filter_tolerance,
            "call_count": self._call_count,
            "avg_ms": round(self._total_ms / max(1, self._call_count), 2),
        }


# ─── Observer Ladder Adapter ────────────────────────────────────────────

class ObserverScoringStrategy(HeuristicStrategy):
    """Wraps ``ObserverLadder.score()`` as a HeuristicStrategy."""

    def __init__(
        self,
        recursion_depth: int = 5,
        convergence_threshold: float = 0.85,
    ) -> None:
        from layer1_entropy.observer_ladder_replay import (
            ObserverConfig,
            ObserverLadder,
        )

        self._cfg = ObserverConfig(
            recursion_depth=recursion_depth,
            convergence_threshold=convergence_threshold,
        )
        self._ladder = ObserverLadder(self._cfg)
        self._call_count = 0
        self._total_ms = 0.0

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        scores = self._ladder.score(nonces)
        self._total_ms += (time.perf_counter() - t0) * 1000
        self._call_count += 1
        return scores

    def get_hardware_target(self) -> str:
        return "CPU_OBSERVER_LADDER"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "target": self.get_hardware_target(),
            "recursion_depth": self._cfg.recursion_depth,
            "convergence_threshold": self._cfg.convergence_threshold,
            "call_count": self._call_count,
            "avg_ms": round(self._total_ms / max(1, self._call_count), 2),
        }
