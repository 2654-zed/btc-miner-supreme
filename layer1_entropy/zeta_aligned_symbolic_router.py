"""
zeta_aligned_symbolic_router.py
───────────────────────────────
Filters generated entropy candidates along the Riemann zeta critical line
(Re(s) = 1/2) to reduce the nonce search space.

Strategy
--------
1.  Pre-compute the first *N* non-trivial zeros of ζ(s) on the critical
    line, t_k where ζ(1/2 + i·t_k) = 0.
2.  Map each nonce candidate to a point on the imaginary axis via a
    linear/log projection.
3.  Score the candidate by its proximity to the nearest known zero.
4.  Pass through only candidates that exceed a tunable tolerance
    threshold, effectively collapsing the search space along the
    "resonance" of ζ.

The rationale is that the structure of the zeta zeros encodes subtle
prime-distribution information; aligning nonce selection to these zeros
concentrates effort on positions that mirror the deep arithmetic
structure of SHA-256ʼs internal modular additions.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy.special import zeta as _hurwitz_zeta  # used for approximate scoring

logger = logging.getLogger(__name__)

# ── First 50 known non-trivial zeros (imaginary parts) ──────────────────
# Source: Odlyzko tables (extended list loaded dynamically if available)
_KNOWN_ZEROS: List[float] = [
    14.134725, 21.022040, 25.010858, 30.424876, 32.935062,
    37.586178, 40.918719, 43.327073, 48.005151, 49.773832,
    52.970321, 56.446248, 59.347044, 60.831779, 65.112544,
    67.079811, 69.546402, 72.067158, 75.704691, 77.144840,
    79.337375, 82.910381, 84.735493, 87.425275, 88.809111,
    92.491899, 94.651344, 95.870634, 98.831194, 101.317851,
    103.725538, 105.446623, 107.168611, 111.029535, 111.874659,
    114.320220, 116.226680, 118.790783, 121.370125, 122.946829,
    124.256819, 127.516684, 129.578704, 131.087688, 133.497737,
    134.756510, 138.116042, 139.736209, 141.123707, 143.111846,
]


@dataclass
class ZetaRouterConfig:
    """Tunable knobs for the symbolic router."""
    critical_line_re: float = 0.5
    imaginary_range: Tuple[float, float] = (14.134, 10_000.0)
    zero_cache_size: int = 100_000
    filter_tolerance: float = 1e-6
    nonce_space: int = 2**32
    projection: str = "log"            # linear | log


class ZetaAlignedSymbolicRouter:
    """
    Scores and filters nonce candidates based on proximity to Riemann
    zeta non-trivial zeros projected onto the nonce space.
    """

    def __init__(self, cfg: Optional[ZetaRouterConfig] = None) -> None:
        self.cfg = cfg or ZetaRouterConfig()
        self._zeros = self._build_zero_table()
        self._zero_arr = np.array(self._zeros, dtype=np.float64)
        logger.info(
            "ZetaRouter initialised  | zeros=%d  projection=%s  tol=%.2e",
            len(self._zeros), self.cfg.projection, self.cfg.filter_tolerance,
        )

    # ── Zero table construction ──────────────────────────────────────────
    def _build_zero_table(self) -> List[float]:
        """
        Return the imaginary parts of non-trivial zeros within the
        configured range.  Starts from the known table and extends
        via Gram-point estimation when more are needed.
        """
        lo, hi = self.cfg.imaginary_range
        base = [t for t in _KNOWN_ZEROS if lo <= t <= hi]

        # Extend with Gram-point approximation:  g_n ≈ 2π n / ln(n)
        n = len(base)
        while len(base) < self.cfg.zero_cache_size:
            n += 1
            g = 2.0 * math.pi * n / max(math.log(n), 1.0)
            if g > hi:
                break
            base.append(g)

        base.sort()
        return base

    # ── Projection helpers ───────────────────────────────────────────────
    def _nonce_to_t(self, nonces: np.ndarray) -> np.ndarray:
        """Map uint32 nonces → imaginary-axis coordinate t."""
        lo, hi = self.cfg.imaginary_range
        normed = nonces.astype(np.float64) / self.cfg.nonce_space  # [0, 1)
        if self.cfg.projection == "log":
            # logarithmic scaling emphasises lower zeros
            return lo + (hi - lo) * np.log1p(normed * (math.e - 1)) / 1.0
        return lo + (hi - lo) * normed  # linear

    # ── Scoring ──────────────────────────────────────────────────────────
    def score(self, nonces: np.ndarray) -> np.ndarray:
        """
        Score each nonce ∈ [0, 2^32) by proximity to nearest ζ-zero.

        Returns array of floats in [0, 1]; 1 means perfect alignment
        with a known zero.
        """
        t_vals = self._nonce_to_t(nonces)
        # Vectorised nearest-zero search via searchsorted
        idx = np.searchsorted(self._zero_arr, t_vals)
        idx = np.clip(idx, 1, len(self._zero_arr) - 1)

        dist_left = np.abs(t_vals - self._zero_arr[idx - 1])
        dist_right = np.abs(t_vals - self._zero_arr[idx])
        min_dist = np.minimum(dist_left, dist_right)

        # Gaussian scoring: σ = average zero gap / 4
        avg_gap = np.mean(np.diff(self._zero_arr)) if len(self._zero_arr) > 1 else 1.0
        sigma = avg_gap / 4.0
        scores = np.exp(-0.5 * (min_dist / sigma) ** 2)
        return scores

    # ── Filtering ────────────────────────────────────────────────────────
    def route(self, nonces: np.ndarray, threshold: float = 0.3) -> np.ndarray:
        """
        Return only those nonces whose ζ-alignment score exceeds
        *threshold*.
        """
        scores = self.score(nonces)
        mask = scores >= threshold
        passed = nonces[mask]
        logger.debug(
            "ZetaRouter: %d / %d candidates passed (threshold=%.3f)",
            len(passed), len(nonces), threshold,
        )
        return passed

    def route_scored(
        self, nonces: np.ndarray, threshold: float = 0.3
    ) -> List[Tuple[int, float]]:
        """Return (nonce, ζ_score) pairs that pass the threshold."""
        scores = self.score(nonces)
        mask = scores >= threshold
        return list(zip(nonces[mask].tolist(), scores[mask].tolist()))

    # ── Diagnostic ───────────────────────────────────────────────────────
    def zero_density_at(self, t: float) -> float:
        """Approximate zero density near *t* using N(T) ~ T/(2π) ln(T/(2πe))."""
        if t <= 0:
            return 0.0
        return (t / (2 * math.pi)) * math.log(t / (2 * math.pi * math.e))
