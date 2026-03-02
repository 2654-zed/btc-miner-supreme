"""
infrastructure/strategies/cpu_dynamic.py
────────────────────────────────────────
HeuristicStrategy implementation that routes dynamically injected
mathematical formulas through the secure MathSandbox (AST + NumExpr).

This strategy is the only execution path that supports runtime formula
changes without recompilation.  It runs on all available CPU cores via
NumExpr's built-in thread pool, bypassing the GIL entirely.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

import numpy as np

from domain.interfaces import HeuristicStrategy
from infrastructure.math_sandbox import MathSandbox

logger = logging.getLogger(__name__)


class DynamicCPUStrategy(HeuristicStrategy):
    """
    Evaluates a user-supplied formula against nonce arrays using the
    secure AST-sanitised NumExpr sandbox.

    Parameters
    ----------
    formula : str
        Pure arithmetic expression referencing ``nonce`` and optional
        constants (``pi``, ``e``, ``phi``, ``gamma``).
    num_threads : int, optional
        NumExpr thread count.  ``None`` = all available cores.
    """

    def __init__(self, formula: str, num_threads: int | None = None):
        self._formula = formula
        self._sandbox = MathSandbox(num_threads=num_threads)
        # Eagerly validate so construction fails fast on bad formulas
        self._sandbox.sanitize(formula)
        self._total_processed = 0
        self._total_anomalies = 0
        logger.info(
            "DynamicCPUStrategy initialised — formula: '%s'", formula
        )

    # ── HeuristicStrategy contract ──────────────────────────────────────

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        result = self._sandbox.execute(self._formula, nonces)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Count mathematical anomalies (NaN / Inf)
        anomalies = int(np.isnan(result).sum() + np.isinf(result).sum())
        self._total_processed += len(nonces)
        self._total_anomalies += anomalies

        logger.debug(
            "CPU sandbox evaluated %d nonces in %.1f ms — %d anomalies",
            len(nonces), elapsed_ms, anomalies,
        )
        return result

    def get_hardware_target(self) -> str:
        return "CPU_SANDBOX"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "target": self.get_hardware_target(),
            "formula": self._formula,
            "total_processed": self._total_processed,
            "total_anomalies": self._total_anomalies,
        }

    # ── Dynamic update ──────────────────────────────────────────────────

    @property
    def formula(self) -> str:
        return self._formula

    def update_formula(self, new_formula: str) -> None:
        """Hot-update the formula.  Validates before committing."""
        self._sandbox.sanitize(new_formula)
        old = self._formula
        self._formula = new_formula
        logger.info("Formula updated: '%s' → '%s'", old, new_formula)
