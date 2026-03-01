"""
observer_ladder_replay.py
─────────────────────────
Applies symbolic observer recursion to rank and prioritise nonce candidates
based on historical convergence data.

Concept
-------
An "observer ladder" is a stack of N recursive scoring layers.  Each layer
*observes* the output of the layer below, accumulating a Bayesian-like
belief about which nonce sub-ranges converge fastest toward valid hashes.

Layer 0 : raw nonce candidates
Layer 1 : score by SHA-256d leading-zero density in last K blocks
Layer 2 : score by agreement with the GAN replay distribution
…
Layer D : final composite ranking

Higher-ladder scores represent stronger "collapse evidence" — candidates
that multiple independent heuristics agree upon are promoted.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ObserverConfig:
    recursion_depth: int = 5
    convergence_threshold: float = 0.85
    ladder_width: int = 32           # how many sub-ranges per layer
    history_window: int = 500        # blocks of history to consider
    nonce_space: int = 2**32
    ema_alpha: float = 0.1           # exponential-moving-average weight


class ConvergenceHistory:
    """
    Stores per-sub-range convergence statistics accumulated over
    a sliding window of recent blocks.
    """

    def __init__(self, num_bins: int, alpha: float = 0.1) -> None:
        self.num_bins = num_bins
        self.alpha = alpha
        self._hits = np.zeros(num_bins, dtype=np.float64)
        self._attempts = np.ones(num_bins, dtype=np.float64)  # Laplace smooth
        self._ema = np.full(num_bins, 1.0 / num_bins, dtype=np.float64)

    def record_attempt(self, bin_idx: int) -> None:
        self._attempts[bin_idx] += 1

    def record_hit(self, bin_idx: int) -> None:
        self._hits[bin_idx] += 1
        rate = self._hits[bin_idx] / self._attempts[bin_idx]
        self._ema[bin_idx] = self.alpha * rate + (1 - self.alpha) * self._ema[bin_idx]

    @property
    def rates(self) -> np.ndarray:
        return self._ema / (self._ema.sum() + 1e-30)

    def decay(self, factor: float = 0.99) -> None:
        """Decay old statistics to prevent stale dominance."""
        self._hits *= factor
        self._attempts = np.maximum(self._attempts * factor, 1.0)


class ObserverLadder:
    """
    Multi-layer recursive observer that ranks nonce candidates
    by accumulated convergence evidence across *recursion_depth*
    layers.
    """

    def __init__(self, cfg: Optional[ObserverConfig] = None) -> None:
        self.cfg = cfg or ObserverConfig()
        # Each layer divides the nonce space into `ladder_width` bins
        self.layers: List[ConvergenceHistory] = [
            ConvergenceHistory(self.cfg.ladder_width, self.cfg.ema_alpha)
            for _ in range(self.cfg.recursion_depth)
        ]
        self._block_count = 0
        logger.info(
            "ObserverLadder initialised  | depth=%d  width=%d",
            self.cfg.recursion_depth, self.cfg.ladder_width,
        )

    # ── Bin mapping ──────────────────────────────────────────────────────
    def _nonce_to_bin(self, nonce: int, layer: int) -> int:
        """
        Map a nonce to a bin index.  Higher layers use a rotated
        partition so that each layer observes from a different
        "symbolic angle".
        """
        N = self.cfg.nonce_space
        W = self.cfg.ladder_width
        # Rotate partition by layer index to decorrelate layers
        shifted = (nonce + layer * (N // (self.cfg.recursion_depth + 1))) % N
        return int(shifted / (N / W)) % W

    # ── Recording results ────────────────────────────────────────────────
    def record_block(self, winning_nonce: int, tested_nonces: Optional[np.ndarray] = None) -> None:
        """
        Record a newly solved block.  The winning nonce gets a 'hit'
        in every layer; tested (non-winning) nonces get 'attempt' marks
        in layer 0 only (to avoid exponential cost).
        """
        for layer_idx, layer in enumerate(self.layers):
            b = self._nonce_to_bin(winning_nonce, layer_idx)
            layer.record_hit(b)

        if tested_nonces is not None:
            for n in tested_nonces[:10_000]:   # cap to avoid overload
                b = self._nonce_to_bin(int(n), 0)
                self.layers[0].record_attempt(b)

        self._block_count += 1
        if self._block_count % self.cfg.history_window == 0:
            for layer in self.layers:
                layer.decay(0.95)

    # ── Scoring ──────────────────────────────────────────────────────────
    def score(self, nonces: np.ndarray) -> np.ndarray:
        """
        Score nonce candidates through the full observer ladder.

        Returns an array of composite scores ∈ (0, 1].  A score near 1
        means all layers agree the candidate sits in a historically
        convergent sub-range.
        """
        composite = np.ones(len(nonces), dtype=np.float64)

        for layer_idx, layer in enumerate(self.layers):
            rates = layer.rates  # (ladder_width,)
            bins = np.array(
                [self._nonce_to_bin(int(n), layer_idx) for n in nonces],
                dtype=np.int64,
            )
            layer_scores = rates[bins]
            # Multiplicative fusion across layers
            composite *= layer_scores

        # Normalise to [0, 1]
        mx = composite.max()
        if mx > 0:
            composite /= mx

        return composite

    def rank(self, nonces: np.ndarray, top_k: Optional[int] = None) -> np.ndarray:
        """Return nonces sorted by descending composite score, optionally truncated."""
        scores = self.score(nonces)
        order = np.argsort(-scores)
        ranked = nonces[order]
        if top_k is not None:
            ranked = ranked[:top_k]
        return ranked

    def passes_threshold(self, nonces: np.ndarray) -> np.ndarray:
        """Return only nonces whose composite score ≥ convergence_threshold."""
        scores = self.score(nonces)
        mask = scores >= self.cfg.convergence_threshold
        return nonces[mask]

    # ── Diagnostics ──────────────────────────────────────────────────────
    def layer_summary(self) -> List[Dict[str, float]]:
        """Return per-layer statistics for telemetry."""
        summaries = []
        for i, layer in enumerate(self.layers):
            r = layer.rates
            summaries.append({
                "layer": i,
                "entropy": float(-np.sum(r * np.log(r + 1e-30))),
                "max_rate": float(r.max()),
                "min_rate": float(r.min()),
            })
        return summaries
