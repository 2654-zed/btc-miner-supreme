"""
infrastructure/strategies/padic_ladder_strategy.py
──────────────────────────────────────────────────
HeuristicStrategy implementation wrapping a multi-prime p-adic
modular ladder filter.

The ladder scores nonces by their distance to mid-residue classes
across a configurable stack of (prime, power) stages, with an
entropy overlay term.  Nonces whose composite score falls below
the threshold survive the ladder — producing a biased candidate
pool that concentrates near p-adic "attractors".

Numba Acceleration
──────────────────
If ``numba`` is importable, tight ``@njit`` kernels handle the
inner loops.  If not, a pure-NumPy vectorised fallback computes
the identical result.  The strategy never fails due to a missing
optional dependency — it just runs slower.

Exported Class
──────────────
    PadicLadderStrategy(HeuristicStrategy)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import numpy as np

from domain.interfaces import HeuristicStrategy

logger = logging.getLogger(__name__)

# ── Lazy numba import ───────────────────────────────────────────────────
_numba = None
_HAS_NUMBA = False


def _try_load_numba() -> None:
    global _numba, _HAS_NUMBA
    if _numba is not None or _HAS_NUMBA:
        return
    try:
        import numba as nb  # type: ignore[import-untyped]
        _numba = nb
        _HAS_NUMBA = True
        logger.info("Numba %s available — p-adic kernels will be JIT-compiled", nb.__version__)
    except ImportError:
        logger.info("Numba not installed — p-adic ladder will use NumPy fallback (slower)")


# ── Configuration ───────────────────────────────────────────────────────

@dataclass
class PadicLadderConfig:
    """Configuration for the multi-prime p-adic ladder filter.

    Each stage is a ``(prime, power, weight)`` tuple:
      - prime: the base prime for the residue class
      - power: the exponent (modulus = prime ** power)
      - weight: contribution weight in the composite score
    """
    stages: List[Tuple[int, int, float]] = field(default_factory=lambda: [
        (2, 12, 0.30),
        (3, 8, 0.30),
        (5, 6, 0.30),
        (7, 5, 0.30),
    ])
    hi_primes: List[int] = field(default_factory=lambda: [11, 13, 17])
    hi_powers: List[int] = field(default_factory=lambda: [4, 4, 4])
    entropy_weight: float = 0.35


# ── Numba kernels (compiled lazily on first call) ───────────────────────

_jit_score_fn = None


def _get_jit_scorer():
    """Build and cache the JIT-compiled scoring function."""
    global _jit_score_fn
    if _jit_score_fn is not None:
        return _jit_score_fn

    _try_load_numba()
    if not _HAS_NUMBA:
        return None

    @_numba.njit
    def _distance_to_mid_residue(x_u32, p, k):  # type: ignore[misc]
        mod = 1
        for _ in range(k):
            mod *= p
        r = int(x_u32 % np.uint32(mod))
        mid = mod // 2
        d = r - mid
        if d < 0:
            d = -d
        return float(d) / float(mod)

    @_numba.njit
    def _entropy_overlay(x_u32):  # type: ignore[misc]
        xf = float(x_u32)
        s = 0.0
        s += np.sin(xf * 1.0e-3) ** 2
        s += np.cos(xf * 1.3e-3) ** 2
        s += np.sin(xf * 2.1e-3) ** 2
        return s

    @_numba.njit
    def _score_array(cands, hi_primes, hi_ks, entropy_weight):  # type: ignore[misc]
        n = cands.shape[0]
        scores = np.empty(n, dtype=np.float64)
        for i in range(n):
            x = cands[i]
            d = 0.0
            for j in range(hi_primes.shape[0]):
                d += _distance_to_mid_residue(x, int(hi_primes[j]), int(hi_ks[j]))
            scores[i] = d + entropy_weight * _entropy_overlay(x)
        return scores

    _jit_score_fn = _score_array
    return _jit_score_fn


# ── Pure-NumPy fallback ─────────────────────────────────────────────────

def _numpy_score_array(
    cands: np.ndarray,
    hi_primes: np.ndarray,
    hi_ks: np.ndarray,
    entropy_weight: float,
) -> np.ndarray:
    """Vectorised NumPy equivalent of the Numba scorer."""
    scores = np.zeros(len(cands), dtype=np.float64)

    for j in range(len(hi_primes)):
        p = int(hi_primes[j])
        k = int(hi_ks[j])
        mod = p ** k
        mid = mod // 2
        r = (cands.astype(np.int64) % mod).astype(np.float64)
        d = np.abs(r - mid) / float(mod)
        scores += d

    # Entropy overlay (vectorised)
    xf = cands.astype(np.float64)
    entropy = (
        np.sin(xf * 1.0e-3) ** 2
        + np.cos(xf * 1.3e-3) ** 2
        + np.sin(xf * 2.1e-3) ** 2
    )
    scores += entropy_weight * entropy

    return scores


# ── Strategy ────────────────────────────────────────────────────────────

class PadicLadderStrategy(HeuristicStrategy):
    """
    HeuristicStrategy that scores nonces via multi-prime p-adic
    distance-to-mid-residue plus a trigonometric entropy overlay.

    ``execute(nonces)`` returns a float64 score array (lower = more
    concentrated near p-adic attractors).
    """

    def __init__(self, cfg: PadicLadderConfig | None = None) -> None:
        self._cfg = cfg or PadicLadderConfig()
        self._hi_primes = np.array(self._cfg.hi_primes, dtype=np.int64)
        self._hi_ks = np.array(self._cfg.hi_powers, dtype=np.int64)
        self._entropy_weight = self._cfg.entropy_weight
        self._call_count = 0
        self._total_ms = 0.0

        # Trigger lazy load (but don't fail if missing)
        _try_load_numba()

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        """Score every nonce in the array.

        Parameters
        ----------
        nonces : np.ndarray
            1-D uint32 nonce candidates.

        Returns
        -------
        np.ndarray
            float64 composite scores (lower = closer to p-adic attractors).
        """
        t0 = time.perf_counter()

        jit_fn = _get_jit_scorer()
        if jit_fn is not None:
            scores = jit_fn(nonces, self._hi_primes, self._hi_ks, self._entropy_weight)
        else:
            scores = _numpy_score_array(nonces, self._hi_primes, self._hi_ks, self._entropy_weight)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._call_count += 1
        self._total_ms += elapsed_ms

        return scores

    def get_hardware_target(self) -> str:
        return "CPU_PADIC_LADDER"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "target": self.get_hardware_target(),
            "numba_available": _HAS_NUMBA,
            "stages": self._cfg.stages,
            "hi_primes": self._cfg.hi_primes,
            "hi_powers": self._cfg.hi_powers,
            "entropy_weight": self._cfg.entropy_weight,
            "call_count": self._call_count,
            "avg_ms": round(self._total_ms / max(1, self._call_count), 2),
        }
